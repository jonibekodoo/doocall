"""Admin portal API — /api/admin/v1 (JWT + role guards).

platform_admin: dashboard, companies, payment approval, integrators (no
override editing), audit. superadmin additionally: cashback settings,
platform-admin CRUD, payouts, impersonation, integrator override,
company reassignment.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import OperatorProfile, User
from apps.api.errors import ApiError, ErrorCode
from apps.billing import services as billing
from apps.billing.models import Payment, Subscription
from apps.companies.models import Company
from apps.core.models import AuditLog

from . import services
from .models import (
    ROLE_PLATFORM_ADMIN,
    CashbackAccrual,
    Integrator,
    PayoutRequest,
    get_platform_settings,
)
from .permissions import IsPlatformStaff, IsSuperadmin

IMPERSONATION_MINUTES = 15


class StaffView(APIView):
    permission_classes = [IsPlatformStaff]


class SuperadminView(APIView):
    permission_classes = [IsSuperadmin]


def _company_body(company: Company) -> dict[str, Any]:
    subscription = Subscription.all_objects.filter(company=company).first()
    return {
        "id": company.pk,
        "name": company.name,
        "slug": company.slug,
        "status": company.status,
        "trial_ends_at": company.trial_ends_at.isoformat() if company.trial_ends_at else None,
        "trial_expired": (
            company.status == Company.Status.TRIAL
            and company.trial_ends_at is not None
            and company.trial_ends_at < timezone.now()
        ),
        "created_at": company.created_at.isoformat(),
        "acquired_via": company.acquired_via,
        "integrator_id": company.integrator_id,
        "audio_retention_days": company.audio_retention_days,
        "seats": billing.seat_count(company),
        "subscription_status": subscription.status if subscription else None,
        "period_end": subscription.current_period_end.isoformat()
        if subscription and subscription.current_period_end
        else None,
    }


class AdminDashboardView(StaffView):
    @extend_schema(summary="Platform KPIs")
    def get(self, request: Request) -> Response:
        now = timezone.now()
        companies = Company.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(status=Company.Status.ACTIVE)),
            trial=Count("id", filter=Q(status=Company.Status.TRIAL)),
            suspended=Count("id", filter=Q(status=Company.Status.SUSPENDED)),
        )
        mrr = 0
        for sub in Subscription.all_objects.filter(status=Subscription.Status.ACTIVE):
            mrr += billing.seat_count(sub.company) * sub.price_per_operator_uzs
        payments_30d = (
            Payment.all_objects.filter(
                status=Payment.Status.APPROVED, approved_at__gte=now - timedelta(days=30)
            ).aggregate(s=Sum("amount_uzs"))["s"]
            or 0
        )
        from django.db.models.functions import TruncDate

        from apps.calls.models import CallRecord

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        calls_today = CallRecord.all_objects.filter(start_time__gte=today_start).count()

        since = now - timedelta(days=30)
        pay_rows = dict(
            Payment.all_objects.filter(status=Payment.Status.APPROVED, approved_at__gte=since)
            .annotate(day=TruncDate("approved_at"))
            .values("day")
            .annotate(total=Sum("amount_uzs"))
            .values_list("day", "total")
        )
        call_rows = dict(
            CallRecord.all_objects.filter(start_time__gte=since)
            .annotate(day=TruncDate("start_time"))
            .values("day")
            .annotate(n=Count("id"))
            .values_list("day", "n")
        )
        payments_series, calls_series = [], []
        for offset in range(29, -1, -1):
            day = (now - timedelta(days=offset)).date()
            payments_series.append(int(pay_rows.get(day, 0) or 0))
            calls_series.append(int(call_rows.get(day, 0)))

        return Response(
            {
                "success": True,
                "companies": companies,
                "mrr_uzs": mrr,
                "payments_30d_uzs": int(payments_30d),
                "calls_today": calls_today,
                "integrators": Integrator.objects.filter(status=Integrator.Status.ACTIVE).count(),
                "pending_payouts": PayoutRequest.objects.filter(
                    status=PayoutRequest.Status.PENDING
                ).count(),
                "payments_series": payments_series,
                "calls_series": calls_series,
            }
        )


class AdminCompaniesView(StaffView):
    @extend_schema(summary="Companies list (status/q filters; status=expired → lapsed trials)")
    def get(self, request: Request) -> Response:
        qs = Company.objects.all().order_by("-created_at")
        if status_f := request.query_params.get("status"):
            if status_f == "expired":
                qs = qs.filter(status=Company.Status.TRIAL, trial_ends_at__lt=timezone.now())
            else:
                qs = qs.filter(status=status_f)
        if q := request.query_params.get("q", "").strip():
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
        return Response({"success": True, "companies": [_company_body(c) for c in qs[:200]]})


class AdminCompanyDetailView(StaffView):
    @extend_schema(summary="Company detail")
    def get(self, request: Request, company_id: int) -> Response:
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company not found", 404)
        body = _company_body(company)
        body["operators"] = list(
            OperatorProfile.all_objects.filter(company=company).values(
                "id", "user_name", "full_name", "is_active"
            )
        )
        body["payments"] = [
            {
                "id": p.pk,
                "provider": p.provider,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
            }
            for p in Payment.all_objects.filter(company=company)[:20]
        ]
        return Response({"success": True, "company": body})

    @extend_schema(summary="Edit company (name, trial end, retention)")
    def patch(self, request: Request, company_id: int) -> Response:
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company not found", 404)

        fields: list[str] = []
        if "name" in request.data:
            name = (request.data["name"] or "").strip()
            if not name:
                raise ApiError(ErrorCode.MISSING_FIELD, "name required", 400)
            if Company.objects.exclude(pk=company.pk).filter(name__iexact=name).exists():
                raise ApiError(ErrorCode.MISSING_FIELD, "name already taken", 400)
            company.name = name
            fields.append("name")
        if "audio_retention_days" in request.data:
            raw = request.data["audio_retention_days"]
            if raw in (None, ""):
                company.audio_retention_days = None
            else:
                try:
                    days = int(raw)
                except (TypeError, ValueError):
                    raise ApiError(
                        ErrorCode.MISSING_FIELD, "audio_retention_days invalid", 400
                    ) from None
                if days < 1:
                    raise ApiError(ErrorCode.MISSING_FIELD, "audio_retention_days invalid", 400)
                company.audio_retention_days = days
            fields.append("audio_retention_days")
        if not fields:
            raise ApiError(ErrorCode.MISSING_FIELD, "nothing to update", 400)

        company.save(update_fields=[*fields, "updated_at"])
        AuditLog.objects.create(
            company=company,
            actor=cast(User, request.user),
            action="admin.company_updated",
            target_model="companies.Company",
            target_id=str(company.pk),
            changes={f: str(getattr(company, f)) for f in fields},
        )
        return Response({"success": True, "company": _company_body(company)})


class AdminCompanyActionView(StaffView):
    @extend_schema(summary="suspend | activate | extend-trial")
    def post(self, request: Request, company_id: int, action: str) -> Response:
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company not found", 404)
        actor = cast(User, request.user)
        subscription = Subscription.all_objects.filter(company=company).first()

        if action == "suspend":
            if subscription and subscription.status in ("trial", "active"):
                billing.suspend(subscription, reason="admin_action", actor=actor)
            else:
                company.status = Company.Status.SUSPENDED
                company.save(update_fields=["status", "updated_at"])
        elif action == "activate":
            if subscription and subscription.status in ("trial", "suspended"):
                billing.activate(subscription, actor=actor)
            else:
                company.status = Company.Status.ACTIVE
                company.save(update_fields=["status", "updated_at"])
        elif action == "extend-trial":
            days = int(request.data.get("days", 7))
            base = company.trial_ends_at or timezone.now()
            company.status = Company.Status.TRIAL
            company.trial_ends_at = max(base, timezone.now()) + timedelta(days=days)
            company.save(update_fields=["status", "trial_ends_at", "updated_at"])
        else:
            raise ApiError(ErrorCode.MISSING_FIELD, f"unknown action {action}", 400)

        AuditLog.objects.create(
            company=company,
            actor=actor,
            action=f"admin.company_{action.replace('-', '_')}",
            target_model="companies.Company",
            target_id=str(company.pk),
        )
        company.refresh_from_db()
        return Response({"success": True, "company": _company_body(company)})


class AdminCompanyReassignView(SuperadminView):
    @extend_schema(summary="Reassign integrator binding (superadmin)")
    def post(self, request: Request, company_id: int) -> Response:
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company not found", 404)
        integrator = None
        if integrator_id := request.data.get("integrator_id"):
            integrator = Integrator.objects.filter(pk=integrator_id).first()
            if integrator is None:
                raise ApiError(ErrorCode.MISSING_FIELD, "integrator not found", 400)
        services.reassign_integrator(company, integrator, actor=cast(User, request.user))
        return Response({"success": True, "integrator_id": company.integrator_id})


class AdminPaymentApproveView(StaffView):
    @extend_schema(summary="Approve a pending manual payment (fires cashback)")
    def post(self, request: Request, payment_id: int) -> Response:
        payment = Payment.all_objects.filter(pk=payment_id).first()
        if payment is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "payment not found", 404)
        billing.apply_payment(payment, actor=cast(User, request.user))
        accrual = CashbackAccrual.objects.filter(payment=payment).first()
        return Response(
            {
                "success": True,
                "payment_status": payment.status,
                "cashback_accrued_uzs": accrual.amount_uzs if accrual else 0,
            }
        )


class AdminPaymentsView(StaffView):
    @extend_schema(summary="Payments list (provider/status filters)")
    def get(self, request: Request) -> Response:
        qs = Payment.all_objects.select_related("company").order_by("-created_at")
        if provider := request.query_params.get("provider"):
            qs = qs.filter(provider=provider)
        if status_f := request.query_params.get("status"):
            qs = qs.filter(status=status_f)
        rows = [
            {
                "id": p.pk,
                "company": p.company.name,
                "company_id": p.company_id,
                "provider": p.provider,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
                "cashback_uzs": getattr(getattr(p, "cashback_accrual", None), "amount_uzs", None),
            }
            for p in qs[:200]
        ]
        return Response({"success": True, "payments": rows})


class AdminPaymentRefundView(StaffView):
    @extend_schema(summary="Mark a payment refunded (reverses cashback)")
    def post(self, request: Request, payment_id: int) -> Response:
        payment = Payment.all_objects.filter(pk=payment_id).first()
        if payment is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "payment not found", 404)
        if payment.status != Payment.Status.APPROVED:
            raise ApiError(ErrorCode.MISSING_FIELD, "only approved payments can be refunded", 400)
        payment.status = Payment.Status.REJECTED  # refund marker (no new enum)
        payment.save(update_fields=["status"])
        services.reverse_cashback(payment)
        AuditLog.objects.create(
            company=payment.company,
            actor=cast(User, request.user),
            action="admin.payment_refunded",
            target_model="billing.Payment",
            target_id=str(payment.pk),
            changes={"amount_uzs": payment.amount_uzs},
        )
        return Response({"success": True})


class AdminPricingView(SuperadminView):
    @extend_schema(summary="Platform pricing editor (superadmin)")
    def get(self, request: Request) -> Response:
        from apps.billing.models import PricingSetting

        row = PricingSetting.objects.filter(company=None).first()
        history = [
            {
                "price_per_operator_uzs": h.price_per_operator_uzs,
                "trial_days": h.trial_days,
                "changed_at": h.changed_at.isoformat(),
                "changed_by": h.changed_by.email if h.changed_by else None,
            }
            for h in (row.history.all()[:20] if row else [])
        ]
        return Response(
            {
                "success": True,
                "price_per_operator_uzs": row.price_per_operator_uzs if row else 0,
                "trial_days": row.trial_days if row else 0,
                "history": history,
            }
        )

    @extend_schema(summary="Update pricing (applies next period)")
    def put(self, request: Request) -> Response:
        from apps.billing.models import PricingSetting

        row = PricingSetting.objects.filter(company=None).first()
        if row is None:
            row = PricingSetting(price_per_operator_uzs=50000, trial_days=14)
        if "price_per_operator_uzs" in request.data:
            row.price_per_operator_uzs = int(request.data["price_per_operator_uzs"])
        if "trial_days" in request.data:
            row.trial_days = int(request.data["trial_days"])
        row.updated_by = cast(User, request.user)
        row.save()
        return Response({"success": True})


class AdminIntegratorsView(StaffView):
    @extend_schema(summary="List integrators")
    def get(self, request: Request) -> Response:
        rows = [
            {
                "id": i.pk,
                "name": i.name,
                "status": i.status,
                "referral_code": i.referral_code,
                "companies": i.companies.count(),
                "override_percent": str(i.cashback_percent_override)
                if i.cashback_percent_override is not None
                else None,
                "balance_uzs": i.balance_uzs,
            }
            for i in Integrator.objects.all()
        ]
        return Response({"success": True, "integrators": rows})

    @extend_schema(summary="Create integrator (user + profile)")
    def post(self, request: Request) -> Response:
        email = (request.data.get("email") or "").strip().lower()
        name = (request.data.get("name") or "").strip()
        password = request.data.get("password") or ""
        if not email or not name or len(password) < 8:
            raise ApiError(ErrorCode.MISSING_FIELD, "email, name, password(≥8) required", 400)
        if User.objects.filter(username=email).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "email already registered", 400)
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            role=services.get_platform_role("integrator"),
        )
        integrator = Integrator.objects.create(
            user=user, name=name, phone=request.data.get("phone") or ""
        )
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.integrator_created",
            target_model="partners.Integrator",
            target_id=str(integrator.pk),
        )
        return Response(
            {
                "success": True,
                "integrator": {
                    "id": integrator.pk,
                    "referral_code": integrator.referral_code,
                },
            },
            status=http.HTTP_201_CREATED,
        )


class AdminIntegratorDetailView(StaffView):
    @extend_schema(summary="Integrator detail")
    def get(self, request: Request, integrator_id: int) -> Response:
        integrator = Integrator.objects.filter(pk=integrator_id).first()
        if integrator is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "integrator not found", 404)
        from .models import get_platform_settings

        lifetime = (
            CashbackAccrual.objects.filter(integrator=integrator)
            .exclude(status=CashbackAccrual.Status.REVERSED)
            .aggregate(s=Sum("amount_uzs"))["s"]
            or 0
        )
        companies = [
            {
                "id": c.pk,
                "name": c.name,
                "status": c.status,
                "acquired_via": c.acquired_via,
                "cashback_uzs": int(
                    CashbackAccrual.objects.filter(integrator=integrator, company=c)
                    .exclude(status=CashbackAccrual.Status.REVERSED)
                    .aggregate(s=Sum("amount_uzs"))["s"]
                    or 0
                ),
            }
            for c in integrator.companies.all()
        ]
        accruals = [
            {
                "id": a.pk,
                "company": a.company.name,
                "amount_uzs": a.amount_uzs,
                "percent": str(a.percent),
                "status": a.status,
                "created_at": a.created_at.isoformat(),
            }
            for a in CashbackAccrual.objects.filter(integrator=integrator).select_related(
                "company"
            )[:100]
        ]
        payouts = [
            {
                "id": p.pk,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "requested_at": p.requested_at.isoformat(),
            }
            for p in integrator.payout_requests.all()[:50]
        ]
        return Response(
            {
                "success": True,
                "integrator": {
                    "id": integrator.pk,
                    "name": integrator.name,
                    "email": integrator.user.email,
                    "phone": integrator.phone,
                    "status": integrator.status,
                    "referral_code": integrator.referral_code,
                    "override_percent": str(integrator.cashback_percent_override)
                    if integrator.cashback_percent_override is not None
                    else None,
                    "default_percent": str(get_platform_settings().default_cashback_percent),
                    "effective_percent": str(integrator.effective_percent),
                    "lifetime_cashback_uzs": int(lifetime),
                    "balance_uzs": integrator.balance_uzs,
                    "payout_details": integrator.payout_details,
                },
                "companies": companies,
                "accruals": accruals,
                "payouts": payouts,
            }
        )

    @extend_schema(summary="Integrator update (override = superadmin)")
    def patch(self, request: Request, integrator_id: int) -> Response:
        integrator = Integrator.objects.filter(pk=integrator_id).first()
        if integrator is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "integrator not found", 404)

        if "cashback_percent_override" in request.data:
            # A.1: overrides are OFF-LIMITS for platform_admin.
            if services.role_name(request.user) == ROLE_PLATFORM_ADMIN:
                raise ApiError("FORBIDDEN", "cashback override requires superadmin", 403)
            value = request.data["cashback_percent_override"]
            integrator.cashback_percent_override = value if value is not None else None
        if "name" in request.data:
            integrator.name = request.data["name"]
        if "phone" in request.data:
            integrator.phone = (request.data["phone"] or "").strip()
        if "payout_details" in request.data:
            details = request.data["payout_details"]
            if not isinstance(details, dict):
                raise ApiError(ErrorCode.MISSING_FIELD, "payout_details must be an object", 400)
            integrator.payout_details = details
        if "email" in request.data:
            email = (request.data["email"] or "").strip().lower()
            if not email:
                raise ApiError(ErrorCode.MISSING_FIELD, "email required", 400)
            if User.objects.exclude(pk=integrator.user_id).filter(username=email).exists():
                raise ApiError(ErrorCode.MISSING_FIELD, "email already registered", 400)
            integrator.user.username = email
            integrator.user.email = email
            integrator.user.save(update_fields=["username", "email"])
        if "status" in request.data and request.data["status"] in ("active", "suspended"):
            integrator.status = request.data["status"]
        integrator.save()
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.integrator_updated",
            target_model="partners.Integrator",
            target_id=str(integrator.pk),
            changes={k: str(v) for k, v in request.data.items()},
        )
        return Response({"success": True})


class AdminCashbackSettingsView(SuperadminView):
    @extend_schema(summary="Platform cashback settings (superadmin)")
    def get(self, request: Request) -> Response:
        row = get_platform_settings()
        return Response(
            {
                "success": True,
                "default_cashback_percent": str(row.default_cashback_percent),
                "cashback_months_limit": row.cashback_months_limit,
            }
        )

    @extend_schema(summary="Update cashback settings (history-tracked)")
    def put(self, request: Request) -> Response:
        row = get_platform_settings()
        if "default_cashback_percent" in request.data:
            row.default_cashback_percent = request.data["default_cashback_percent"]
        if "cashback_months_limit" in request.data:
            row.cashback_months_limit = int(request.data["cashback_months_limit"])
        row.updated_by = cast(User, request.user)
        row.save()
        return Response({"success": True})


class AdminPlatformAdminsView(SuperadminView):
    @extend_schema(summary="Platform-admin users CRUD (superadmin)")
    def get(self, request: Request) -> Response:
        role = services.get_platform_role(ROLE_PLATFORM_ADMIN)
        rows = list(User.objects.filter(role=role).values("id", "email", "is_active"))
        return Response({"success": True, "admins": rows})

    def post(self, request: Request) -> Response:
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""
        if not email or len(password) < 8:
            raise ApiError(ErrorCode.MISSING_FIELD, "email + password(≥8) required", 400)
        if User.objects.filter(username=email).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "email already registered", 400)
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            role=services.get_platform_role(ROLE_PLATFORM_ADMIN),
        )
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.platform_admin_created",
            target_id=str(user.pk),
        )
        return Response({"success": True, "id": user.pk}, status=http.HTTP_201_CREATED)


class AdminPlatformAdminDetailView(SuperadminView):
    def patch(self, request: Request, user_id: int) -> Response:
        role = services.get_platform_role(ROLE_PLATFORM_ADMIN)
        user = User.objects.filter(pk=user_id, role=role).first()
        if user is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "admin not found", 404)
        if "is_active" in request.data:
            user.is_active = bool(request.data["is_active"])
            user.save(update_fields=["is_active"])
        return Response({"success": True})


class AdminPayoutsView(SuperadminView):
    @extend_schema(summary="Payout queue (superadmin)")
    def get(self, request: Request) -> Response:
        qs = PayoutRequest.objects.select_related("integrator")
        if status_f := request.query_params.get("status"):
            qs = qs.filter(status=status_f)
        rows = [
            {
                "id": p.pk,
                "integrator": p.integrator.name,
                "integrator_id": p.integrator_id,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "requested_at": p.requested_at.isoformat(),
                "payout_details": p.integrator.payout_details,
            }
            for p in qs[:200]
        ]
        return Response({"success": True, "payouts": rows})


class AdminPayoutActionView(SuperadminView):
    @extend_schema(summary="approve | reject | mark-paid")
    def post(self, request: Request, payout_id: int, action: str) -> Response:
        payout = PayoutRequest.objects.filter(pk=payout_id).first()
        if payout is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "payout not found", 404)
        mapping = {
            "approve": PayoutRequest.Status.APPROVED,
            "reject": PayoutRequest.Status.REJECTED,
            "mark-paid": PayoutRequest.Status.PAID,
        }
        if action not in mapping:
            raise ApiError(ErrorCode.MISSING_FIELD, f"unknown action {action}", 400)
        try:
            services.process_payout(
                payout,
                mapping[action],
                actor=cast(User, request.user),
                note=request.data.get("note", ""),
            )
        except services.PayoutError as exc:
            raise ApiError(ErrorCode.MISSING_FIELD, str(exc), 400) from None
        return Response({"success": True, "status": payout.status})


class AdminAppReleasesView(StaffView):
    """Mobile APK builds: list + multipart upload (platform staff)."""

    parser_classes = [MultiPartParser, FormParser]

    MAX_APK_BYTES = 300 * 1024 * 1024

    @extend_schema(summary="List app releases")
    def get(self, request: Request) -> Response:
        from apps.core.models import AppRelease

        rows = [
            {
                "id": r.pk,
                "version": r.version,
                "size_bytes": r.size_bytes,
                "notes": r.notes,
                "uploaded_by": r.uploaded_by.email if r.uploaded_by else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in AppRelease.objects.all()[:50]
        ]
        return Response({"success": True, "releases": rows})

    @extend_schema(summary="Upload a new APK build")
    def post(self, request: Request) -> Response:
        from apps.api import storage
        from apps.core.models import AppRelease

        version = str(request.data.get("version") or "").strip()
        notes = str(request.data.get("notes") or "").strip()
        upload = request.FILES.get("file")
        if not version or upload is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "version and file required", 400)
        if AppRelease.objects.filter(version__iexact=version).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "version already uploaded", 400)
        if not upload.name.lower().endswith(".apk"):
            raise ApiError(ErrorCode.MISSING_FIELD, "file must be an .apk", 400)
        if upload.size > self.MAX_APK_BYTES:
            raise ApiError(ErrorCode.MISSING_FIELD, "file too large", 400)

        object_key = f"app-releases/doocall-{version}.apk"
        payload = upload.read()
        storage.ensure_bucket()
        import io

        storage.client().put_object(
            settings.MINIO_BUCKET,
            object_key,
            io.BytesIO(payload),
            length=len(payload),
            content_type="application/vnd.android.package-archive",
        )
        release = AppRelease.objects.create(
            version=version,
            object_key=object_key,
            size_bytes=len(payload),
            notes=notes,
            uploaded_by=cast(User, request.user),
        )
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.app_release_uploaded",
            target_model="core.AppRelease",
            target_id=str(release.pk),
            changes={"version": version, "size_bytes": str(len(payload))},
        )
        return Response(
            {"success": True, "release": {"id": release.pk, "version": release.version}},
            status=http.HTTP_201_CREATED,
        )


class AdminAppReleaseDeleteView(SuperadminView):
    @extend_schema(summary="Delete an app release (superadmin)")
    def delete(self, request: Request, release_id: int) -> Response:
        from apps.core.models import AppRelease

        release = AppRelease.objects.filter(pk=release_id).first()
        if release is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "release not found", 404)
        release.delete()
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.app_release_deleted",
            target_model="core.AppRelease",
            target_id=str(release_id),
            changes={"version": release.version},
        )
        return Response({"success": True})


class AdminAuditView(StaffView):
    @extend_schema(summary="Audit log query")
    def get(self, request: Request) -> Response:
        qs = AuditLog.objects.select_related("company", "actor")
        if action := request.query_params.get("action"):
            qs = qs.filter(action__icontains=action)
        if company_id := request.query_params.get("company"):
            qs = qs.filter(company_id=company_id)
        if date_from := request.query_params.get("date_from"):
            qs = qs.filter(created_at__date__gte=date_from)
        rows = [
            {
                "id": a.pk,
                "action": a.action,
                "company": a.company.slug if a.company else None,
                "actor": a.actor.email or a.actor.username if a.actor else None,
                "changes": a.changes,
                "created_at": a.created_at.isoformat(),
            }
            for a in qs[:200]
        ]
        return Response({"success": True, "entries": rows})


class AdminImpersonateView(SuperadminView):
    @extend_schema(summary="Start impersonation (superadmin) — 15-min token")
    def post(self, request: Request, company_id: int) -> Response:
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company not found", 404)
        target = (
            User.objects.filter(company=company, is_company_admin=True).first()
            or User.objects.filter(company=company).first()
        )
        if target is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company has no users", 400)

        token = AccessToken.for_user(target)
        token.set_exp(lifetime=timedelta(minutes=IMPERSONATION_MINUTES))
        token["impersonated"] = True  # frontend renders the banner from this
        token["impersonator_id"] = request.user.pk

        AuditLog.objects.create(
            company=company,
            actor=cast(User, request.user),
            action="admin.impersonation_started",
            target_model="accounts.User",
            target_id=str(target.pk),
            changes={"expires_minutes": IMPERSONATION_MINUTES},
        )
        return Response(
            {
                "success": True,
                "access": str(token),
                "impersonated_user": target.email or target.username,
                "company": company.slug,
                "expires_in_minutes": IMPERSONATION_MINUTES,
            }
        )


class AdminImpersonateStopView(SuperadminView):
    @extend_schema(summary="Stop impersonation (audit trail)")
    def post(self, request: Request) -> Response:
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.impersonation_stopped",
            changes={"company": request.data.get("company", "")},
        )
        return Response({"success": True})
