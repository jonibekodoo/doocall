"""Admin portal API — /api/admin/v1 (JWT + role guards).

platform_admin: dashboard, companies, payment approval, integrators (no
override editing), audit. superadmin additionally: cashback settings,
platform-admin CRUD, payouts, impersonation, integrator override,
company reassignment.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
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
from apps.billing.models import (
    Payment,
    PaylovLog,
    PaymentProviderConfig,
    Subscription,
    ensure_provider_configs,
)
from apps.companies.models import Company
from apps.core.models import AuditLog

from . import services
from . import crm as crm_helpers
from .models import (
    ROLE_PLATFORM_ADMIN,
    CashbackAccrual,
    CrmTask,
    Integrator,
    IntegratorApplication,
    Lead,
    PayoutRequest,
    Pipeline,
    PipelineStage,
    SalesCommission,
    SalesManager,
    SalesPayoutRequest,
    ensure_global_pipelines,
    get_offer_document,
    get_platform_settings,
)
from .permissions import IsPlatformStaff, IsSuperadmin

IMPERSONATION_MINUTES = 15


class StaffView(APIView):
    permission_classes = [IsPlatformStaff]


class SuperadminView(APIView):
    permission_classes = [IsSuperadmin]


def _company_phone(company: Company) -> str:
    """Company contact phone = the company-admin user's phone (set at
    registration), falling back to any user of the company that has one."""
    admin = (
        User.objects.filter(company=company, is_company_admin=True)
        .exclude(phone="")
        .values_list("phone", flat=True)
        .first()
    )
    if admin:
        return admin
    return (
        User.objects.filter(company=company)
        .exclude(phone="")
        .values_list("phone", flat=True)
        .first()
        or ""
    )


def _integrations_count(company: Company) -> int:
    """Enabled CRM integrations (amoCRM / Bitrix24 / …) connected to the company."""
    from apps.integrations.models import CrmIntegration

    return CrmIntegration.all_objects.filter(company=company, is_enabled=True).count()


def _integrations_detail(company: Company) -> list[dict[str, Any]]:
    """Every connector configured for the company, for the admin detail page.

    Ready-made CRM connectors (amoCRM / Bitrix24 / Odoo) come from
    ``CrmIntegration``; the company-level "custom" webhook and public API key
    are reported too so staff see the full picture. Secrets never leave here.
    """
    from apps.integrations.models import CrmIntegration

    rows: list[dict[str, Any]] = [
        {
            "kind": "crm",
            "provider": i.provider,
            "label": i.get_provider_display(),
            "is_enabled": i.is_enabled,
            "last_status": i.last_status,
            "last_error": i.last_error,
            "last_delivery_at": i.last_delivery_at.isoformat() if i.last_delivery_at else None,
            "updated_at": i.updated_at.isoformat(),
        }
        for i in CrmIntegration.all_objects.filter(company=company).order_by("provider")
    ]
    if company.webhook_url:
        rows.append(
            {
                "kind": "webhook",
                "provider": "webhook",
                "label": "Webhook",
                "is_enabled": True,
                "last_status": "",
                "last_error": "",
                "last_delivery_at": None,
                "updated_at": None,
                "target": company.webhook_url,
            }
        )
    if company.api_key:
        rows.append(
            {
                "kind": "api",
                "provider": "api",
                "label": "Public API",
                "is_enabled": True,
                "last_status": "",
                "last_error": "",
                "last_delivery_at": None,
                "updated_at": None,
            }
        )
    return rows


def _company_body(company: Company) -> dict[str, Any]:
    subscription = Subscription.all_objects.filter(company=company).first()
    return {
        "id": company.pk,
        "name": company.name,
        "slug": company.slug,
        "phone": _company_phone(company),
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
        "integrator_name": company.integrator.name if company.integrator_id else None,
        "integrator_company": company.integrator.company_name if company.integrator_id else None,
        "integrations_count": _integrations_count(company),
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
        call_totals = CallRecord.all_objects.aggregate(n=Count("id"), s=Sum("duration"))
        total_calls = int(call_totals["n"] or 0)
        total_call_seconds = int(call_totals["s"] or 0)

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
                "total_calls": total_calls,
                "total_call_seconds": total_call_seconds,
                "integrators": Integrator.objects.filter(status=Integrator.Status.ACTIVE).count(),
                "pending_payments": Payment.all_objects.filter(
                    status=Payment.Status.PENDING
                ).count(),
                "pending_payouts": PayoutRequest.objects.filter(
                    status=PayoutRequest.Status.PENDING
                ).count(),
                "payments_series": payments_series,
                "calls_series": calls_series,
            }
        )


class AdminCallsTodayView(StaffView):
    """Today's calls broken down by company and operator (dashboard report)."""

    @extend_schema(summary="Today's calls per company / operator")
    def get(self, request: Request) -> Response:
        from apps.calls.models import CallRecord

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = (
            CallRecord.all_objects.filter(start_time__gte=today_start)
            .values(
                "company_id",
                "company__name",
                "operator_id",
                "operator__full_name",
                "operator__user_name",
                "call_status",
            )
            .annotate(n=Count("id"))
            .order_by("company__name")
        )
        companies: dict[int, dict[str, Any]] = {}
        for r in rows:
            c = companies.setdefault(
                r["company_id"],
                {"id": r["company_id"], "name": r["company__name"], "total": 0,
                 "answered": 0, "missed": 0, "operators": {}},
            )
            n = int(r["n"])
            c["total"] += n
            if r["call_status"] == "answered":
                c["answered"] += n
            else:
                c["missed"] += n
            op_key = r["operator_id"] or 0
            op = c["operators"].setdefault(
                op_key,
                {"id": r["operator_id"],
                 "name": r["operator__full_name"] or r["operator__user_name"] or "—",
                 "total": 0, "answered": 0},
            )
            op["total"] += n
            if r["call_status"] == "answered":
                op["answered"] += n
        out = []
        for c in companies.values():
            c["operators"] = sorted(c["operators"].values(), key=lambda o: -o["total"])
            out.append(c)
        out.sort(key=lambda c: -c["total"])
        return Response(
            {
                "success": True,
                "date": today_start.date().isoformat(),
                "total": sum(c["total"] for c in out),
                "companies": out,
            }
        )


class AdminDashboardSeriesView(StaffView):
    """Time series for the dashboard charts at a chosen granularity.

    ?metric=payments|calls & ?period=daily|weekly|monthly|yearly
    Payments = sum of APPROVED payment amounts; calls = call count.
    """

    @extend_schema(summary="Dashboard time series (metric, period)")
    def get(self, request: Request) -> Response:
        from datetime import date

        from django.db.models.functions import TruncDate, TruncMonth, TruncWeek, TruncYear

        from apps.calls.models import CallRecord

        metric = request.query_params.get("metric", "calls")
        period = request.query_params.get("period", "daily")
        # Local time so the buckets line up with the DB-side Trunc*, which uses
        # the active TIME_ZONE (Asia/Tashkent), not UTC.
        now = timezone.localtime()

        # Build the ordered list of (bucket_key_date, label) for the period.
        buckets: list[tuple[date, str]] = []
        if period == "weekly":
            trunc = TruncWeek
            monday = now.date() - timedelta(days=now.weekday())
            for off in range(11, -1, -1):
                d = monday - timedelta(weeks=off)
                buckets.append((d, f"{d.month}/{d.day}"))
        elif period == "monthly":
            trunc = TruncMonth
            for off in range(11, -1, -1):
                mm, yy = now.month - off, now.year
                while mm <= 0:
                    mm += 12
                    yy -= 1
                d = date(yy, mm, 1)
                buckets.append((d, f"{yy}-{mm:02d}"))
        elif period == "yearly":
            trunc = TruncYear
            for off in range(4, -1, -1):
                yy = now.year - off
                buckets.append((date(yy, 1, 1), str(yy)))
        else:  # daily
            trunc = TruncDate
            for off in range(29, -1, -1):
                d = (now - timedelta(days=off)).date()
                buckets.append((d, f"{d.month}/{d.day}"))

        floor = buckets[0][0]
        if metric == "payments":
            base = Payment.all_objects.filter(
                status=Payment.Status.APPROVED, approved_at__isnull=False, approved_at__date__gte=floor
            )
            rows = (
                base.annotate(b=trunc("approved_at"))
                .values("b")
                .annotate(v=Sum("amount_uzs"))
                .values_list("b", "v")
            )
        else:  # calls
            base = CallRecord.all_objects.filter(start_time__date__gte=floor)
            rows = (
                base.annotate(b=trunc("start_time"))
                .values("b")
                .annotate(v=Count("id"))
                .values_list("b", "v")
            )

        by_bucket: dict[date, int] = {}
        for key, value in rows:
            d = key.date() if hasattr(key, "date") else key
            by_bucket[d] = int(value or 0)

        series = [{"label": label, "value": by_bucket.get(key, 0)} for key, label in buckets]
        return Response({"success": True, "metric": metric, "period": period, "series": series})


class AdminCompaniesView(StaffView):
    @extend_schema(summary="Companies list (status/q filters; status=expired → lapsed trials)")
    def get(self, request: Request) -> Response:
        qs = Company.objects.select_related("integrator").order_by("-created_at")
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
        body["users"] = [
            {
                "id": u.pk,
                "email": u.email or u.username,
                "is_company_admin": u.is_company_admin,
                "is_active": u.is_active,
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in User.objects.filter(company=company).order_by("-is_company_admin", "id")
        ]
        body["integrations"] = _integrations_detail(company)
        from apps.calls.stats import company_call_stats

        body["stats"] = company_call_stats(company, include_operators=True)
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

        # Phone lives on the company-admin user (set at registration).
        phone_changed = False
        if "phone" in request.data:
            phone = (request.data["phone"] or "").strip()
            admin_user = (
                User.objects.filter(company=company, is_company_admin=True)
                .order_by("id")
                .first()
                or User.objects.filter(company=company).order_by("id").first()
            )
            if admin_user is not None:
                admin_user.phone = phone
                admin_user.save(update_fields=["phone"])
                phone_changed = True

        if not fields and not phone_changed:
            raise ApiError(ErrorCode.MISSING_FIELD, "nothing to update", 400)

        if fields:
            company.save(update_fields=[*fields, "updated_at"])
        AuditLog.objects.create(
            company=company,
            actor=cast(User, request.user),
            action="admin.company_updated",
            target_model="companies.Company",
            target_id=str(company.pk),
            changes={
                **{f: str(getattr(company, f)) for f in fields},
                **({"phone": _company_phone(company)} if phone_changed else {}),
            },
        )
        return Response({"success": True, "company": _company_body(company)})

    @extend_schema(summary="Delete company PERMANENTLY (superadmin; ?confirm=<slug>)")
    def delete(self, request: Request, company_id: int) -> Response:
        if not IsSuperadmin().has_permission(request, self):
            raise ApiError(ErrorCode.MISSING_FIELD, "superadmin role required", 403)
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company not found", 404)
        confirm = request.query_params.get("confirm") or request.data.get("confirm")
        if confirm != company.slug:
            raise ApiError(
                ErrorCode.MISSING_FIELD,
                "confirm must match the company slug",
                400,
            )

        from apps.billing.tasks import purge_company_storage
        from apps.calls.models import CallRecord

        pk = company.pk
        stats = {
            "name": company.name,
            "slug": company.slug,
            "operators": OperatorProfile.all_objects.filter(company=company).count(),
            "calls": CallRecord.all_objects.filter(company=company).count(),
        }
        # Log first: AuditLog.company is SET_NULL, so the row survives the
        # cascade with the identifying details preserved in ``changes``.
        AuditLog.objects.create(
            company=company,
            actor=cast(User, request.user),
            action="admin.company_deleted",
            target_model="companies.Company",
            target_id=str(pk),
            changes=stats,
        )
        company.delete()
        purge_company_storage.delay(pk)
        return Response({"success": True, "deleted": stats})


class AdminCompanyUserPasswordView(SuperadminView):
    @extend_schema(summary="Set a new cabinet password for a company user (superadmin)")
    def post(self, request: Request, company_id: int, user_id: int) -> Response:
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company not found", 404)
        user = User.objects.filter(pk=user_id, company=company).first()
        if user is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "user not found", 404)
        password = request.data.get("password") or ""
        if len(password) < 8:
            raise ApiError(ErrorCode.MISSING_FIELD, "password(≥8) required", 400)
        user.set_password(password)
        user.save(update_fields=["password"])
        # Never write the password itself to the audit trail.
        AuditLog.objects.create(
            company=company,
            actor=cast(User, request.user),
            action="admin.user_password_reset",
            target_model="accounts.User",
            target_id=str(user.pk),
            changes={"email": user.email or user.username},
        )
        return Response({"success": True})


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
        # Manual approval is ONLY for bank/cash requests. Gateway payments
        # (Paylov/Payme/Click) are credited solely by the gateway's own
        # confirmation — never by an admin click.
        if payment.provider != Payment.Provider.MANUAL:
            raise ApiError(
                ErrorCode.MISSING_FIELD,
                "only bank/cash payments can be approved manually",
                400,
            )
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


class AdminPaymentStatsView(StaffView):
    @extend_schema(summary="Payment statistics: totals, by provider, by status")
    def get(self, request: Request) -> Response:
        approved = Payment.all_objects.filter(status=Payment.Status.APPROVED)
        total_uzs = approved.aggregate(s=Sum("amount_uzs"))["s"] or 0
        total_count = approved.count()

        # Approved revenue split by provider.
        by_provider = [
            {
                "provider": row["provider"],
                "count": row["c"],
                "amount_uzs": int(row["s"] or 0),
            }
            for row in approved.values("provider")
            .annotate(c=Count("id"), s=Sum("amount_uzs"))
            .order_by("-s")
        ]

        # Every payment split by status (count + summed amount).
        by_status = [
            {
                "status": row["status"],
                "count": row["c"],
                "amount_uzs": int(row["s"] or 0),
            }
            for row in Payment.all_objects.values("status")
            .annotate(c=Count("id"), s=Sum("amount_uzs"))
            .order_by("-c")
        ]

        # Approved revenue over the last 30 days (daily buckets, company tz-agnostic UTC).
        from django.db.models.functions import TruncDate

        since = timezone.now() - timedelta(days=30)
        day_rows = dict(
            approved.filter(approved_at__gte=since)
            .annotate(day=TruncDate("approved_at"))
            .values("day")
            .annotate(s=Sum("amount_uzs"))
            .values_list("day", "s")
        )
        series = []
        for offset in range(29, -1, -1):
            day = (timezone.now() - timedelta(days=offset)).date()
            series.append(int(day_rows.get(day, 0) or 0))

        pending = Payment.all_objects.filter(status=Payment.Status.PENDING).aggregate(
            c=Count("id"), s=Sum("amount_uzs")
        )
        return Response(
            {
                "success": True,
                "total_uzs": int(total_uzs),
                "total_count": total_count,
                "pending_count": pending["c"] or 0,
                "pending_uzs": int(pending["s"] or 0),
                "by_provider": by_provider,
                "by_status": by_status,
                "revenue_series": series,
            }
        )


class AdminPaymentRefundView(StaffView):
    @extend_schema(summary="Refund a payment (debits balance, notifies client, reverses cashback)")
    def post(self, request: Request, payment_id: int) -> Response:
        payment = Payment.all_objects.filter(pk=payment_id).first()
        if payment is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "payment not found", 404)
        if payment.status != Payment.Status.APPROVED:
            raise ApiError(ErrorCode.MISSING_FIELD, "only approved payments can be refunded", 400)
        billing.refund_payment(payment, actor=cast(User, request.user))
        services.reverse_cashback(payment)
        services.reverse_sales_commission(payment)
        AuditLog.objects.create(
            company=payment.company,
            actor=cast(User, request.user),
            action="admin.payment_refunded",
            target_model="billing.Payment",
            target_id=str(payment.pk),
            changes={"amount_uzs": payment.amount_uzs},
        )
        return Response({"success": True})


class AdminPaymentRejectView(StaffView):
    @extend_schema(summary="Reject a pending payment (bank/cash request or unconfirmed gateway txn)")
    def post(self, request: Request, payment_id: int) -> Response:
        payment = Payment.all_objects.filter(pk=payment_id).first()
        if payment is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "payment not found", 404)
        if payment.status != Payment.Status.PENDING:
            raise ApiError(ErrorCode.MISSING_FIELD, "only pending payments can be rejected", 400)
        payment.status = Payment.Status.REJECTED
        payment.save(update_fields=["status"])
        AuditLog.objects.create(
            company=payment.company,
            actor=cast(User, request.user),
            action="admin.payment_rejected",
            target_model="billing.Payment",
            target_id=str(payment.pk),
            changes={"amount_uzs": payment.amount_uzs, "provider": payment.provider},
        )
        return Response({"success": True, "status": payment.status})


class AdminPaymentDeleteView(StaffView):
    @extend_schema(summary="Delete a payment record (approved ones must be refunded first)")
    def delete(self, request: Request, payment_id: int) -> Response:
        payment = Payment.all_objects.filter(pk=payment_id).first()
        if payment is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "payment not found", 404)
        # An approved payment has credited the balance (+ cashback/commission):
        # it must be refunded first so money never silently disappears.
        if payment.status == Payment.Status.APPROVED:
            raise ApiError(
                ErrorCode.MISSING_FIELD, "refund the approved payment before deleting it", 400
            )
        AuditLog.objects.create(
            company=payment.company,
            actor=cast(User, request.user),
            action="admin.payment_deleted",
            target_model="billing.Payment",
            target_id=str(payment.pk),
            changes={
                "amount_uzs": payment.amount_uzs,
                "provider": payment.provider,
                "status": payment.status,
                "external_id": payment.external_id,
            },
        )
        payment.delete()
        return Response({"success": True})


# ── Payment providers (admin on/off + logo) ─────────────────────────────────
def _provider_logo_url(cfg: PaymentProviderConfig) -> str | None:
    return f"/api/public/provider-logo/{cfg.provider}" if cfg.logo_key else None


def _provider_row(cfg: PaymentProviderConfig) -> dict[str, Any]:
    try:
        label = Payment.Provider(cfg.provider).label
    except ValueError:
        label = cfg.provider
    return {
        "provider": cfg.provider,
        "label": label,
        "is_enabled": cfg.is_enabled,
        "sort_order": cfg.sort_order,
        "logo_url": _provider_logo_url(cfg),
        "updated_at": cfg.updated_at.isoformat(),
    }


class AdminPaymentProvidersView(StaffView):
    @extend_schema(summary="Payment providers: list on/off + logo")
    def get(self, request: Request) -> Response:
        ensure_provider_configs()
        rows = [_provider_row(c) for c in PaymentProviderConfig.objects.all()]
        return Response({"success": True, "providers": rows})

    @extend_schema(summary="Toggle / reorder a payment provider")
    def patch(self, request: Request) -> Response:
        provider = str(request.data.get("provider") or "")
        cfg = PaymentProviderConfig.objects.filter(provider=provider).first()
        if cfg is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "provider not found", 404)
        fields: list[str] = []
        if "is_enabled" in request.data:
            cfg.is_enabled = bool(request.data.get("is_enabled"))
            fields.append("is_enabled")
        if "sort_order" in request.data:
            try:
                cfg.sort_order = max(0, int(request.data.get("sort_order")))
                fields.append("sort_order")
            except (TypeError, ValueError):
                pass
        if fields:
            cfg.save(update_fields=[*fields, "updated_at"])
            AuditLog.objects.create(
                actor=cast(User, request.user),
                action="admin.payment_provider_updated",
                target_model="billing.PaymentProviderConfig",
                target_id=cfg.provider,
                changes={f: getattr(cfg, f) for f in fields},
            )
        return Response({"success": True, "provider": _provider_row(cfg)})


class AdminPaymentProviderLogoView(StaffView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary="Upload a payment provider's logo")
    def post(self, request: Request, provider: str) -> Response:
        import io
        import uuid

        from apps.api import storage

        cfg = PaymentProviderConfig.objects.filter(provider=provider).first()
        if cfg is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "provider not found", 404)
        upload = request.FILES.get("logo")
        if upload is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo file required", 400)
        if upload.size > 2 * 1024 * 1024:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo too large (max 2MB)", 400)
        types = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/svg+xml": "svg",
            "image/webp": "webp",
        }
        content_type = getattr(upload, "content_type", "") or ""
        if content_type not in types:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo must be png/jpeg/svg/webp", 400)
        key = f"provider-logos/{provider}-{uuid.uuid4().hex}.{types[content_type]}"
        payload = upload.read()
        storage.ensure_bucket()
        storage.client().put_object(
            settings.MINIO_BUCKET, key, io.BytesIO(payload),
            length=len(payload), content_type=content_type,
        )
        cfg.logo_key = key
        cfg.save(update_fields=["logo_key", "updated_at"])
        return Response({"success": True, "logo_url": f"/api/public/provider-logo/{provider}"})


# ── Paylov transactions + logs ───────────────────────────────────────────────
class AdminPaylovTransactionsView(StaffView):
    @extend_schema(summary="Paylov transactions (payments) with filters")
    def get(self, request: Request) -> Response:
        qs = (
            Payment.all_objects.select_related("company")
            .filter(provider=Payment.Provider.PAYLOV)
            .order_by("-created_at")
        )
        if status_f := request.query_params.get("status"):
            qs = qs.filter(status=status_f)
        if q := (request.query_params.get("q") or "").strip():
            qs = qs.filter(Q(company__name__icontains=q) | Q(external_id__icontains=q))
        if d_from := request.query_params.get("from"):
            qs = qs.filter(created_at__date__gte=d_from)
        if d_to := request.query_params.get("to"):
            qs = qs.filter(created_at__date__lte=d_to)
        rows = [
            {
                "id": p.pk,
                "company": p.company.name,
                "company_id": p.company_id,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "external_id": p.external_id,
                "created_at": p.created_at.isoformat(),
                "approved_at": p.approved_at.isoformat() if p.approved_at else None,
                "logs_count": p.paylov_logs.count(),
            }
            for p in qs[:300]
        ]
        totals = qs.aggregate(c=Count("id"), s=Sum("amount_uzs"))
        approved = qs.filter(status=Payment.Status.APPROVED).aggregate(
            c=Count("id"), s=Sum("amount_uzs")
        )
        return Response(
            {
                "success": True,
                "transactions": rows,
                "total_count": totals["c"] or 0,
                "total_uzs": int(totals["s"] or 0),
                "approved_count": approved["c"] or 0,
                "approved_uzs": int(approved["s"] or 0),
            }
        )


class AdminPaylovTransactionActionView(StaffView):
    @extend_schema(summary="Act on a Paylov transaction (apply/refund/cancel)")
    def post(self, request: Request, payment_id: int) -> Response:
        payment = Payment.all_objects.filter(
            pk=payment_id, provider=Payment.Provider.PAYLOV
        ).first()
        if payment is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "transaction not found", 404)
        action = str(request.data.get("action") or "")
        # NOTE: there is intentionally NO manual "apply" for Paylov — balance is
        # credited only when Paylov confirms the OTP (BillingPaylovConfirmView).
        if action == "refund":
            if payment.status != Payment.Status.APPROVED:
                raise ApiError(ErrorCode.MISSING_FIELD, "only approved can be refunded", 400)
            billing.refund_payment(payment, actor=cast(User, request.user))
            services.reverse_cashback(payment)
            services.reverse_sales_commission(payment)
        elif action == "cancel":
            if payment.status != Payment.Status.PENDING:
                raise ApiError(ErrorCode.MISSING_FIELD, "only pending can be cancelled", 400)
            payment.status = Payment.Status.REJECTED
            payment.save(update_fields=["status"])
        else:
            raise ApiError(ErrorCode.MISSING_FIELD, "unknown action", 400)
        AuditLog.objects.create(
            company=payment.company,
            actor=cast(User, request.user),
            action=f"admin.paylov_{action}",
            target_model="billing.Payment",
            target_id=str(payment.pk),
            changes={"amount_uzs": payment.amount_uzs},
        )
        payment.refresh_from_db()
        return Response({"success": True, "status": payment.status})


class AdminPaylovLogsView(StaffView):
    @extend_schema(summary="Paylov exchange log (inbound/outbound, timestamped)")
    def get(self, request: Request) -> Response:
        qs = PaylovLog.objects.select_related("payment").all()
        if direction := request.query_params.get("direction"):
            qs = qs.filter(direction=direction)
        if event := request.query_params.get("event"):
            qs = qs.filter(event__icontains=event)
        if pid := request.query_params.get("payment_id"):
            qs = qs.filter(payment_id=pid)
        if request.query_params.get("errors") == "1":
            qs = qs.filter(ok=False)
        rows = [
            {
                "id": r.pk,
                "direction": r.direction,
                "event": r.event,
                "ok": r.ok,
                "http_status": r.http_status,
                "payment_id": r.payment_id,
                "request_body": r.request_body,
                "response_body": r.response_body,
                "note": r.note,
                "created_at": r.created_at.isoformat(),
            }
            for r in qs[:300]
        ]
        return Response({"success": True, "logs": rows})


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
                "company_name": i.company_name,
                "logo_url": f"/api/public/integrator-logo/{i.pk}" if i.logo_key else None,
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


class AdminIntegratorStatsView(StaffView):
    """Leaderboard metrics per integrator: companies onboarded, revenue their
    companies paid, commission they earned, their companies' total call time."""

    @extend_schema(summary="Integrator statistics / leaderboard")
    def get(self, request: Request) -> Response:
        from apps.calls.models import CallRecord

        def grouped(qs, key: str, expr) -> dict[int, int]:
            return {
                row[key]: int(row["v"] or 0)
                for row in qs.values(key).annotate(v=expr)
                if row[key] is not None
            }

        companies = grouped(
            Company.objects.exclude(integrator=None), "integrator", Count("id")
        )
        active = grouped(
            Company.objects.filter(status=Company.Status.ACTIVE).exclude(integrator=None),
            "integrator",
            Count("id"),
        )
        suspended = grouped(
            Company.objects.filter(status=Company.Status.SUSPENDED).exclude(integrator=None),
            "integrator",
            Count("id"),
        )
        trial_all = grouped(
            Company.objects.filter(status=Company.Status.TRIAL).exclude(integrator=None),
            "integrator",
            Count("id"),
        )
        expired = grouped(
            Company.objects.filter(
                status=Company.Status.TRIAL, trial_ends_at__lt=timezone.now()
            ).exclude(integrator=None),
            "integrator",
            Count("id"),
        )
        revenue = grouped(
            Payment.all_objects.filter(
                status=Payment.Status.APPROVED, company__integrator__isnull=False
            ),
            "company__integrator",
            Sum("amount_uzs"),
        )
        cashback = grouped(
            CashbackAccrual.objects.exclude(status=CashbackAccrual.Status.REVERSED),
            "integrator",
            Sum("amount_uzs"),
        )
        call_seconds = grouped(
            CallRecord.all_objects.filter(company__integrator__isnull=False),
            "company__integrator",
            Sum("duration"),
        )

        rows = []
        for i in Integrator.objects.all():
            exp = expired.get(i.pk, 0)
            rows.append(
                {
                    "id": i.pk,
                    "name": i.name,
                    "company_name": i.company_name,
                    "logo_url": f"/api/public/integrator-logo/{i.pk}" if i.logo_key else None,
                    "referral_code": i.referral_code,
                    "status": i.status,
                    "companies": companies.get(i.pk, 0),
                    "company_status": {
                        "active": active.get(i.pk, 0),
                        "trial": max(trial_all.get(i.pk, 0) - exp, 0),
                        "expired": exp,
                        "suspended": suspended.get(i.pk, 0),
                    },
                    "revenue_uzs": revenue.get(i.pk, 0),
                    "cashback_uzs": cashback.get(i.pk, 0),
                    "balance_uzs": i.balance_uzs,
                    "call_seconds": call_seconds.get(i.pk, 0),
                }
            )
        rows.sort(key=lambda r: r["revenue_uzs"], reverse=True)

        totals = {
            "integrators": len(rows),
            "companies": sum(r["companies"] for r in rows),
            "revenue_uzs": sum(r["revenue_uzs"] for r in rows),
            "cashback_uzs": sum(r["cashback_uzs"] for r in rows),
            "call_seconds": sum(r["call_seconds"] for r in rows),
        }
        return Response({"success": True, "integrators": rows, "totals": totals})


def _application_body(app: "IntegratorApplication") -> dict[str, Any]:
    return {
        "id": app.pk,
        "full_name": app.full_name,
        "phone": app.phone,
        "email": app.email,
        "company": app.company,
        "message": app.message,
        "status": app.status,
        "sales_manager_id": app.sales_manager_id,
        "sales_manager_name": app.sales_manager.name if app.sales_manager else None,
        "created_at": app.created_at.isoformat(),
        "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
    }


class AdminIntegratorPasswordView(SuperadminView):
    @extend_schema(summary="Set a new login password for an integrator (superadmin)")
    def post(self, request: Request, integrator_id: int) -> Response:
        integrator = Integrator.objects.filter(pk=integrator_id).select_related("user").first()
        if integrator is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "integrator not found", 404)
        password = request.data.get("password") or ""
        if len(password) < 8:
            raise ApiError(ErrorCode.MISSING_FIELD, "password(≥8) required", 400)
        user = integrator.user
        user.set_password(password)
        user.save(update_fields=["password"])
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.integrator_password_reset",
            target_model="accounts.User",
            target_id=str(user.pk),
            changes={"integrator": integrator.name},
        )
        return Response({"success": True})


class AdminIntegratorLogoView(StaffView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary="Upload an integrator's company logo")
    def post(self, request: Request, integrator_id: int) -> Response:
        import io
        import uuid

        from apps.api import storage

        integrator = Integrator.objects.filter(pk=integrator_id).first()
        if integrator is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "integrator not found", 404)
        upload = request.FILES.get("logo")
        if upload is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo file required", 400)
        if upload.size > 2 * 1024 * 1024:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo too large (max 2MB)", 400)
        types = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/svg+xml": "svg",
            "image/webp": "webp",
        }
        content_type = getattr(upload, "content_type", "") or ""
        if content_type not in types:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo must be png/jpeg/svg/webp", 400)
        key = f"integrator-logos/{uuid.uuid4().hex}.{types[content_type]}"
        payload = upload.read()
        storage.ensure_bucket()
        storage.client().put_object(
            settings.MINIO_BUCKET,
            key,
            io.BytesIO(payload),
            length=len(payload),
            content_type=content_type,
        )
        integrator.logo_key = key
        integrator.save(update_fields=["logo_key", "updated_at"])
        return Response(
            {"success": True, "logo_url": f"/api/public/integrator-logo/{integrator.pk}"}
        )


class AdminIntegratorApplicationsView(StaffView):
    @extend_schema(summary="List integrator applications (public landing form)")
    def get(self, request: Request) -> Response:
        qs = IntegratorApplication.objects.all()
        if status_f := request.query_params.get("status"):
            qs = qs.filter(status=status_f)
        return Response(
            {
                "success": True,
                "applications": [_application_body(a) for a in qs[:300]],
                "new_count": IntegratorApplication.objects.filter(
                    status=IntegratorApplication.Status.NEW
                ).count(),
            }
        )


class AdminIntegratorApplicationDetailView(StaffView):
    @extend_schema(summary="Update application status / assign to a sales manager")
    def patch(self, request: Request, application_id: int) -> Response:
        app = IntegratorApplication.objects.filter(pk=application_id).first()
        if app is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "application not found", 404)
        fields = ["reviewed_at"]
        app.reviewed_at = timezone.now()

        if "status" in request.data:
            new_status = request.data.get("status")
            if new_status not in {s.value for s in IntegratorApplication.Status}:
                raise ApiError(ErrorCode.MISSING_FIELD, "invalid status", 400)
            app.status = new_status
            fields.append("status")

        # Assign to a sales manager → materialise a CRM lead in their funnel.
        if "sales_manager_id" in request.data:
            sm_id = request.data["sales_manager_id"]
            if sm_id in (None, "", 0):
                app.sales_manager = None
            else:
                manager = SalesManager.objects.filter(pk=sm_id).first()
                if manager is None:
                    raise ApiError(ErrorCode.MISSING_FIELD, "sales manager not found", 400)
                app.sales_manager = manager
                if not Lead.objects.filter(application=app, sales_manager=manager).exists():
                    crm_helpers.check_duplicates(phone=app.phone, company=app.company)
                    pipe = ensure_global_pipelines()
                    lead = Lead.objects.create(
                        sales_manager=manager,
                        pipeline=pipe,
                        stage=pipe.stages.first(),
                        application=app,
                        full_name=app.full_name,
                        phone=app.phone,
                        email=app.email,
                        company=app.company,
                        # `source` is a FK → look up the seeded "Ariza" source.
                        source=LeadSource.objects.filter(name="Ariza").first(),
                        note=app.message,
                    )
                    crm_helpers.log_event(
                        lead, "created", cast(User, request.user), text=app.full_name
                    )
                    services.notify_user(
                        manager.user,
                        "lead_assigned",
                        f"Yangi lid biriktirildi: {app.full_name}",
                    )
            fields.append("sales_manager")

        app.save(update_fields=fields)
        return Response({"success": True, "application": _application_body(app)})


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
                    "company_name": integrator.company_name,
                    "logo_url": f"/api/public/integrator-logo/{integrator.pk}"
                    if integrator.logo_key
                    else None,
                    "is_public": integrator.is_public,
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
                    "bank_card": integrator.bank_card,
                    "bank_mfo": integrator.bank_mfo,
                    "bank_inn": integrator.bank_inn,
                    "bank_transit": integrator.bank_transit,
                    "sales_manager_id": integrator.sales_manager_id,
                    "sales_manager_name": integrator.sales_manager.name
                    if integrator.sales_manager
                    else None,
                    "offer_accepted_at": integrator.offer_accepted_at.isoformat()
                    if integrator.offer_accepted_at
                    else None,
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
        if "company_name" in request.data:
            integrator.company_name = (request.data["company_name"] or "").strip()
        if "is_public" in request.data:
            integrator.is_public = bool(request.data["is_public"])
        for bank_field in ("bank_card", "bank_mfo", "bank_inn", "bank_transit"):
            if bank_field in request.data:
                setattr(integrator, bank_field, (request.data[bank_field] or "").strip())
        if "sales_manager_id" in request.data:
            sm_id = request.data["sales_manager_id"]
            if sm_id in (None, "", 0):
                integrator.sales_manager = None
            else:
                manager = SalesManager.objects.filter(pk=sm_id).first()
                if manager is None:
                    raise ApiError(ErrorCode.MISSING_FIELD, "sales manager not found", 400)
                integrator.sales_manager = manager
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


def _sales_manager_body(m: SalesManager) -> dict[str, Any]:
    return {
        "id": m.pk,
        "name": m.name,
        "company_name": m.company_name,
        "logo_url": f"/api/public/sales-logo/{m.pk}" if m.logo_key else None,
        "email": m.user.email,
        "phone": m.phone,
        "status": m.status,
        "commission_percent": str(m.commission_percent),
        "balance_uzs": m.balance_uzs,
        "integrators": m.integrators.count(),
        "bank_card": m.bank_card,
        "bank_mfo": m.bank_mfo,
        "bank_inn": m.bank_inn,
        "bank_transit": m.bank_transit,
        "offer_accepted_at": m.offer_accepted_at.isoformat() if m.offer_accepted_at else None,
    }


class AdminSalesManagersView(StaffView):
    @extend_schema(summary="List / create sales managers")
    def get(self, request: Request) -> Response:
        return Response(
            {"success": True, "managers": [_sales_manager_body(m) for m in SalesManager.objects.all()]}
        )

    @extend_schema(summary="Create sales manager (user + profile)")
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
            role=services.get_platform_role("sales_manager"),
        )
        try:
            percent = Decimal(str(request.data.get("commission_percent") or "0"))
        except (TypeError, ValueError, ArithmeticError):
            percent = Decimal("0")
        manager = SalesManager.objects.create(
            user=user, name=name, phone=request.data.get("phone") or "", commission_percent=percent
        )
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.sales_manager_created",
            target_model="partners.SalesManager",
            target_id=str(manager.pk),
        )
        return Response({"success": True, "manager": _sales_manager_body(manager)}, status=http.HTTP_201_CREATED)


class AdminSalesManagerStatsView(StaffView):
    @extend_schema(summary="Sales manager leaderboard")
    def get(self, request: Request) -> Response:
        from apps.calls.models import CallRecord

        def grouped(qs, key, expr) -> dict[int, int]:
            return {r[key]: int(r["v"] or 0) for r in qs.values(key).annotate(v=expr) if r[key] is not None}

        integ = grouped(Integrator.objects.exclude(sales_manager=None), "sales_manager", Count("id"))
        companies = grouped(
            Company.objects.exclude(integrator__sales_manager=None),
            "integrator__sales_manager",
            Count("id"),
        )
        revenue = grouped(
            Payment.all_objects.filter(
                status=Payment.Status.APPROVED, company__integrator__sales_manager__isnull=False
            ),
            "company__integrator__sales_manager",
            Sum("amount_uzs"),
        )
        commission = grouped(
            SalesCommission.objects.exclude(status=SalesCommission.Status.REVERSED),
            "sales_manager",
            Sum("amount_uzs"),
        )
        call_seconds = grouped(
            CallRecord.all_objects.filter(company__integrator__sales_manager__isnull=False),
            "company__integrator__sales_manager",
            Sum("duration"),
        )
        rows = []
        for m in SalesManager.objects.all():
            rows.append(
                {
                    "id": m.pk,
                    "name": m.name,
                    "company_name": m.company_name,
                    "logo_url": f"/api/public/sales-logo/{m.pk}" if m.logo_key else None,
                    "status": m.status,
                    "commission_percent": str(m.commission_percent),
                    "integrators": integ.get(m.pk, 0),
                    "companies": companies.get(m.pk, 0),
                    "revenue_uzs": revenue.get(m.pk, 0),
                    "commission_uzs": commission.get(m.pk, 0),
                    "balance_uzs": m.balance_uzs,
                    "call_seconds": call_seconds.get(m.pk, 0),
                }
            )
        rows.sort(key=lambda r: r["commission_uzs"], reverse=True)
        totals = {
            "managers": len(rows),
            "integrators": sum(r["integrators"] for r in rows),
            "companies": sum(r["companies"] for r in rows),
            "revenue_uzs": sum(r["revenue_uzs"] for r in rows),
            "commission_uzs": sum(r["commission_uzs"] for r in rows),
        }
        return Response({"success": True, "managers": rows, "totals": totals})


class AdminSalesManagerDetailView(StaffView):
    @extend_schema(summary="Sales manager detail")
    def get(self, request: Request, manager_id: int) -> Response:
        m = SalesManager.objects.filter(pk=manager_id).first()
        if m is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "sales manager not found", 404)
        body = _sales_manager_body(m)
        body["integrator_list"] = [
            {"id": i.pk, "name": i.name, "status": i.status, "companies": i.companies.count()}
            for i in m.integrators.all()
        ]
        body["commissions"] = [
            {
                "id": c.pk,
                "company": c.company.name,
                "amount_uzs": c.amount_uzs,
                "percent": str(c.percent),
                "status": c.status,
                "created_at": c.created_at.isoformat(),
            }
            for c in SalesCommission.objects.filter(sales_manager=m).select_related("company")[:100]
        ]
        body["payouts"] = [
            {
                "id": p.pk,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "requested_at": p.requested_at.isoformat(),
            }
            for p in m.payout_requests.all()[:50]
        ]
        lifetime = (
            SalesCommission.objects.filter(sales_manager=m)
            .exclude(status=SalesCommission.Status.REVERSED)
            .aggregate(s=Sum("amount_uzs"))["s"]
            or 0
        )
        body["lifetime_commission_uzs"] = int(lifetime)
        return Response({"success": True, "manager": body})

    @extend_schema(summary="Update sales manager")
    def patch(self, request: Request, manager_id: int) -> Response:
        m = SalesManager.objects.filter(pk=manager_id).first()
        if m is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "sales manager not found", 404)
        for field in ("name", "company_name", "phone", "bank_card", "bank_mfo", "bank_inn", "bank_transit"):
            if field in request.data:
                setattr(m, field, (request.data[field] or "").strip())
        if "commission_percent" in request.data:
            try:
                m.commission_percent = Decimal(str(request.data["commission_percent"] or "0"))
            except (TypeError, ValueError, ArithmeticError):
                raise ApiError(ErrorCode.MISSING_FIELD, "commission_percent invalid", 400) from None
        if "status" in request.data and request.data["status"] in ("active", "suspended"):
            m.status = request.data["status"]
        if "email" in request.data:
            email = (request.data["email"] or "").strip().lower()
            if not email:
                raise ApiError(ErrorCode.MISSING_FIELD, "email required", 400)
            if User.objects.exclude(pk=m.user_id).filter(username=email).exists():
                raise ApiError(ErrorCode.MISSING_FIELD, "email already registered", 400)
            m.user.username = email
            m.user.email = email
            m.user.save(update_fields=["username", "email"])
        m.save()
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.sales_manager_updated",
            target_model="partners.SalesManager",
            target_id=str(m.pk),
            changes={k: str(v) for k, v in request.data.items()},
        )
        return Response({"success": True, "manager": _sales_manager_body(m)})


class AdminSalesManagerPasswordView(SuperadminView):
    @extend_schema(summary="Set a sales manager login password (superadmin)")
    def post(self, request: Request, manager_id: int) -> Response:
        m = SalesManager.objects.filter(pk=manager_id).select_related("user").first()
        if m is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "sales manager not found", 404)
        password = request.data.get("password") or ""
        if len(password) < 8:
            raise ApiError(ErrorCode.MISSING_FIELD, "password(≥8) required", 400)
        m.user.set_password(password)
        m.user.save(update_fields=["password"])
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.sales_manager_password_reset",
            target_model="accounts.User",
            target_id=str(m.user_id),
            changes={"sales_manager": m.name},
        )
        return Response({"success": True})


class AdminSalesManagerLogoView(StaffView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary="Upload a sales manager logo")
    def post(self, request: Request, manager_id: int) -> Response:
        import io
        import uuid

        from apps.api import storage

        m = SalesManager.objects.filter(pk=manager_id).first()
        if m is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "sales manager not found", 404)
        upload = request.FILES.get("logo")
        if upload is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo file required", 400)
        if upload.size > 2 * 1024 * 1024:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo too large (max 2MB)", 400)
        types = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg", "image/webp": "webp"}
        content_type = getattr(upload, "content_type", "") or ""
        if content_type not in types:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo must be png/jpeg/svg/webp", 400)
        key = f"sales-logos/{uuid.uuid4().hex}.{types[content_type]}"
        payload = upload.read()
        storage.ensure_bucket()
        storage.client().put_object(
            settings.MINIO_BUCKET, key, io.BytesIO(payload), length=len(payload), content_type=content_type
        )
        m.logo_key = key
        m.save(update_fields=["logo_key", "updated_at"])
        return Response({"success": True, "logo_url": f"/api/public/sales-logo/{m.pk}"})


class AdminSalesPayoutsView(SuperadminView):
    @extend_schema(summary="Sales payout queue")
    def get(self, request: Request) -> Response:
        qs = SalesPayoutRequest.objects.select_related("sales_manager")
        if status_f := request.query_params.get("status"):
            qs = qs.filter(status=status_f)
        rows = [
            {
                "id": p.pk,
                "sales_manager": p.sales_manager.name,
                "sales_manager_id": p.sales_manager_id,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "requested_at": p.requested_at.isoformat(),
                "bank": {
                    "card": p.sales_manager.bank_card,
                    "mfo": p.sales_manager.bank_mfo,
                    "inn": p.sales_manager.bank_inn,
                    "transit": p.sales_manager.bank_transit,
                },
            }
            for p in qs[:200]
        ]
        return Response({"success": True, "payouts": rows})


class AdminSalesPayoutActionView(SuperadminView):
    @extend_schema(summary="Approve / reject / mark-paid a sales payout")
    def post(self, request: Request, payout_id: int, action: str) -> Response:
        payout = SalesPayoutRequest.objects.filter(pk=payout_id).first()
        if payout is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "payout not found", 404)
        mapping = {
            "approve": SalesPayoutRequest.Status.APPROVED,
            "reject": SalesPayoutRequest.Status.REJECTED,
            "mark-paid": SalesPayoutRequest.Status.PAID,
        }
        new_status = mapping.get(action)
        if new_status is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "invalid action", 400)
        try:
            services.process_sales_payout(payout, new_status, actor=cast(User, request.user))
        except services.PayoutError as exc:
            raise ApiError(ErrorCode.MISSING_FIELD, str(exc), 400) from None
        return Response({"success": True, "status": payout.status})


class AdminOfferView(SuperadminView):
    @extend_schema(summary="Public offer document (get/edit)")
    def get(self, request: Request) -> Response:
        offer = get_offer_document()
        return Response(
            {"success": True, "content": offer.content, "version": offer.version}
        )

    def put(self, request: Request) -> Response:
        from apps.core.sanitize import sanitize_html

        offer = get_offer_document()
        # Rich text from the editor: keep formatting, strip anything unsafe.
        content = sanitize_html(request.data.get("content", offer.content))
        if content != offer.content:
            offer.content = content
            offer.version += 1
            offer.updated_by = cast(User, request.user)
            offer.save()
        return Response({"success": True, "version": offer.version})


class AdminLegalView(SuperadminView):
    """Public legal pages (privacy / terms / refund) — get/edit per kind."""

    def _doc(self, kind: str):
        from .models import LEGAL_KINDS, get_legal_document

        if kind not in LEGAL_KINDS:
            raise ApiError(ErrorCode.MISSING_FIELD, "unknown document", 404)
        return get_legal_document(kind)

    @extend_schema(summary="Legal page (get)")
    def get(self, request: Request, kind: str) -> Response:
        d = self._doc(kind)
        return Response(
            {
                "success": True,
                "kind": d.kind,
                "content": d.content,
                "version": d.version,
                "updated_at": d.updated_at.isoformat(),
            }
        )

    @extend_schema(summary="Legal page (edit)")
    def put(self, request: Request, kind: str) -> Response:
        from apps.core.sanitize import sanitize_html

        d = self._doc(kind)
        # Rich text from the editor: keep formatting, strip anything unsafe.
        content = sanitize_html(request.data.get("content", d.content))
        if content != d.content:
            d.content = content
            d.version += 1
            d.updated_by = cast(User, request.user)
            d.save()
        return Response({"success": True, "version": d.version})


def _admin_pipeline_body(p: Pipeline) -> dict[str, Any]:
    return {
        "id": p.pk,
        "name": p.name,
        "order": p.order,
        "stages": [
            {"id": s.pk, "name": s.name, "order": s.order, "color": s.color}
            for s in p.stages.all()
        ],
    }


class AdminPipelinesView(StaffView):
    @extend_schema(summary="Global funnels (with stages)")
    def get(self, request: Request) -> Response:
        ensure_global_pipelines()
        pipes = Pipeline.objects.filter(sales_manager__isnull=True).prefetch_related("stages")
        return Response({"success": True, "pipelines": [_admin_pipeline_body(p) for p in pipes]})

    @extend_schema(summary="Create a global funnel (with default stages)")
    def post(self, request: Request) -> Response:
        from .models import DEFAULT_STAGES

        name = (request.data.get("name") or "").strip()
        if len(name) < 2:
            raise ApiError(ErrorCode.MISSING_FIELD, "name required", 400)
        order = Pipeline.objects.filter(sales_manager__isnull=True).count()
        pipe = Pipeline.objects.create(sales_manager=None, name=name, order=order)
        for idx, (label, color) in enumerate(DEFAULT_STAGES):
            PipelineStage.objects.create(pipeline=pipe, name=label, order=idx, color=color)
        return Response({"success": True, "pipeline": _admin_pipeline_body(pipe)}, status=http.HTTP_201_CREATED)


class AdminPipelineDetailView(StaffView):
    def _get(self, pipeline_id: int) -> Pipeline:
        pipe = Pipeline.objects.filter(pk=pipeline_id, sales_manager__isnull=True).first()
        if pipe is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "pipeline not found", 404)
        return pipe

    @extend_schema(summary="Rename a funnel")
    def patch(self, request: Request, pipeline_id: int) -> Response:
        pipe = self._get(pipeline_id)
        if "name" in request.data:
            pipe.name = (request.data["name"] or "").strip() or pipe.name
            pipe.save(update_fields=["name"])
        return Response({"success": True, "pipeline": _admin_pipeline_body(pipe)})

    @extend_schema(summary="Delete a funnel")
    def delete(self, request: Request, pipeline_id: int) -> Response:
        pipe = self._get(pipeline_id)
        if Pipeline.objects.filter(sales_manager__isnull=True).count() <= 1:
            raise ApiError(ErrorCode.MISSING_FIELD, "cannot delete the only funnel", 400)
        pipe.delete()
        return Response({"success": True})

    @extend_schema(summary="Add a stage")
    def post(self, request: Request, pipeline_id: int) -> Response:
        pipe = self._get(pipeline_id)
        name = (request.data.get("name") or "").strip()
        if len(name) < 1:
            raise ApiError(ErrorCode.MISSING_FIELD, "name required", 400)
        order = pipe.stages.count()
        stage = PipelineStage.objects.create(
            pipeline=pipe, name=name, order=order, color=request.data.get("color", "")
        )
        return Response(
            {"success": True, "stage": {"id": stage.pk, "name": stage.name, "order": stage.order, "color": stage.color}},
            status=http.HTTP_201_CREATED,
        )


class AdminStageDetailView(StaffView):
    def _get(self, stage_id: int) -> PipelineStage:
        stage = PipelineStage.objects.filter(pk=stage_id, pipeline__sales_manager__isnull=True).first()
        if stage is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "stage not found", 404)
        return stage

    @extend_schema(summary="Rename / recolor a stage")
    def patch(self, request: Request, stage_id: int) -> Response:
        stage = self._get(stage_id)
        if "name" in request.data:
            stage.name = (request.data["name"] or "").strip() or stage.name
        if "color" in request.data:
            stage.color = request.data["color"] or ""
        stage.save()
        return Response({"success": True})

    @extend_schema(summary="Delete a stage")
    def delete(self, request: Request, stage_id: int) -> Response:
        stage = self._get(stage_id)
        if stage.pipeline.stages.count() <= 1:
            raise ApiError(ErrorCode.MISSING_FIELD, "cannot delete the only stage", 400)
        stage.delete()
        return Response({"success": True})


class AdminLeadsView(StaffView):
    @extend_schema(summary="All CRM leads (filters: pipeline, sales_manager, source, tag, priority, q)")
    def get(self, request: Request) -> Response:
        qs = crm_helpers.apply_lead_filters(
            Lead.objects.select_related("sales_manager", "stage", "source"), request.query_params
        ).prefetch_related("tags", "tasks")
        if sm := request.query_params.get("sales_manager"):
            qs = qs.filter(sales_manager_id=sm)
        return Response({"success": True, "leads": [crm_helpers.lead_card(x) for x in qs[:1000]]})

    @extend_schema(summary="Create a lead (assigned to a sales manager)")
    def post(self, request: Request) -> Response:
        manager = SalesManager.objects.filter(pk=request.data.get("sales_manager_id")).first()
        if manager is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "sales_manager_id required", 400)
        name = (request.data.get("full_name") or "").strip()
        if len(name) < 2:
            raise ApiError(ErrorCode.MISSING_FIELD, "full_name required", 400)
        crm_helpers.check_duplicates(
            phone=request.data.get("phone"), company=request.data.get("company")
        )
        pipe = ensure_global_pipelines()
        lead = Lead.objects.create(
            sales_manager=manager,
            pipeline=pipe,
            stage=pipe.stages.first(),
            full_name=name,
            phone=(request.data.get("phone") or "").strip(),
            company=(request.data.get("company") or "").strip(),
        )
        crm_helpers.log_event(lead, "created", cast(User, request.user), text=name)
        return Response({"success": True, "lead": crm_helpers.lead_card(lead)}, status=http.HTTP_201_CREATED)


class AdminBoardStatsView(StaffView):
    @extend_schema(summary="CRM board metrics (optionally per manager)")
    def get(self, request: Request) -> Response:
        leads = Lead.objects.all()
        tasks = CrmTask.objects.all()
        if sm := request.query_params.get("sales_manager"):
            leads = leads.filter(sales_manager_id=sm)
            tasks = tasks.filter(sales_manager_id=sm)
        return Response({"success": True, **crm_helpers.board_stats(leads, tasks)})


class AdminLeadDetailView(StaffView):
    def _get(self, lead_id: int) -> Lead:
        lead = Lead.objects.filter(pk=lead_id).first()
        if lead is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "lead not found", 404)
        return lead

    @extend_schema(summary="Lead detail")
    def get(self, request: Request, lead_id: int) -> Response:
        return Response({"success": True, "lead": crm_helpers.lead_detail(self._get(lead_id))})

    @extend_schema(summary="Edit / move / reassign a lead")
    def patch(self, request: Request, lead_id: int) -> Response:
        lead = self._get(lead_id)
        actor = cast(User, request.user)
        if "stage_id" in request.data:
            stage = PipelineStage.objects.filter(pk=request.data["stage_id"], pipeline=lead.pipeline).first()
            if stage is None:
                raise ApiError(ErrorCode.MISSING_FIELD, "stage not found", 400)
            crm_helpers.move_to_stage(lead, stage, actor)
        if "sales_manager_id" in request.data:
            m = SalesManager.objects.filter(pk=request.data["sales_manager_id"]).first()
            if m is not None and m.pk != lead.sales_manager_id:
                lead.sales_manager = m
                lead.save(update_fields=["sales_manager", "updated_at"])
                crm_helpers.log_event(lead, "assigned", actor, text=m.name)
        crm_helpers.apply_fields(lead, request.data, actor)
        return Response({"success": True, "lead": crm_helpers.lead_detail(lead)})

    @extend_schema(summary="Delete a lead (admin only)")
    def delete(self, request: Request, lead_id: int) -> Response:
        self._get(lead_id).delete()
        return Response({"success": True})


class AdminLeadNoteView(StaffView):
    @extend_schema(summary="Add a note to a lead")
    def post(self, request: Request, lead_id: int) -> Response:
        lead = Lead.objects.filter(pk=lead_id).first()
        if lead is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "lead not found", 404)
        text = (request.data.get("text") or "").strip()
        if not text:
            raise ApiError(ErrorCode.MISSING_FIELD, "text required", 400)
        crm_helpers.add_note(lead, cast(User, request.user), text)
        return Response({"success": True, "lead": crm_helpers.lead_detail(lead)}, status=http.HTTP_201_CREATED)


class AdminLeadTaskView(StaffView):
    @extend_schema(summary="Add a task to a lead")
    def post(self, request: Request, lead_id: int) -> Response:
        lead = Lead.objects.filter(pk=lead_id).first()
        if lead is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "lead not found", 404)
        crm_helpers.add_task(
            lead,
            cast(User, request.user),
            request.data.get("title"),
            request.data.get("due_at"),
            request.data.get("type_id"),
        )
        return Response({"success": True, "lead": crm_helpers.lead_detail(lead)}, status=http.HTTP_201_CREATED)


class AdminCrmTasksView(StaffView):
    @extend_schema(summary="All CRM tasks (Kanban buckets)")
    def get(self, request: Request) -> Response:
        qs = CrmTask.objects.select_related("sales_manager", "lead", "type")
        if sm := request.query_params.get("sales_manager"):
            qs = qs.filter(sales_manager_id=sm)
        rows = []
        for tk in qs[:1000]:
            rows.append(
                {
                    "id": tk.pk,
                    "title": tk.title,
                    "is_done": tk.is_done,
                    "is_cancelled": tk.is_cancelled,
                    "auto": tk.auto,
                    "due_at": tk.due_at.isoformat() if tk.due_at else None,
                    "sales_manager": tk.sales_manager.name,
                    "lead_id": tk.lead_id,
                    "lead_name": tk.lead.full_name if tk.lead else None,
                    "type": {"name": tk.type.name, "icon": tk.type.icon} if tk.type_id else None,
                    "bucket": crm_helpers.task_bucket(tk),
                }
            )
        return Response({"success": True, "tasks": rows})


class AdminCrmTaskDetailView(StaffView):
    @extend_schema(summary="Complete / cancel / edit / delete a task")
    def patch(self, request: Request, task_id: int) -> Response:
        task = CrmTask.objects.filter(pk=task_id).first()
        if task is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "task not found", 404)
        actor = cast(User, request.user)
        action = request.data.get("action")
        if action == "complete" or request.data.get("is_done"):
            crm_helpers.complete_task(task, actor)
        elif action == "cancel":
            crm_helpers.cancel_task(task, actor, (request.data.get("reason") or "").strip())
        else:
            crm_helpers.edit_task(task, request.data)
        return Response({"success": True})

    @extend_schema(summary="Delete a task")
    def delete(self, request: Request, task_id: int) -> Response:
        task = CrmTask.objects.filter(pk=task_id).first()
        if task is not None:
            task.delete()
        return Response({"success": True})


class AdminCrmMetaView(StaffView):
    @extend_schema(summary="CRM tags / sources / task types (with management)")
    def get(self, request: Request) -> Response:
        from .models import CrmTaskType, LeadSource, LeadTag, seed_lead_sources, seed_task_types

        seed_lead_sources()
        seed_task_types()
        return Response(
            {
                "success": True,
                "tags": [{"id": t.pk, "name": t.name, "color": t.color} for t in LeadTag.objects.all()],
                "sources": [{"id": s.pk, "name": s.name} for s in LeadSource.objects.all()],
                "task_types": [{"id": t.pk, "name": t.name, "icon": t.icon} for t in CrmTaskType.objects.all()],
            }
        )

    @extend_schema(summary="Create a tag / source / task type (kind in body)")
    def post(self, request: Request) -> Response:
        from .models import CrmTaskType, LeadSource, LeadTag

        kind = request.data.get("kind")
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ApiError(ErrorCode.MISSING_FIELD, "name required", 400)
        if kind == "tag":
            obj, _ = LeadTag.objects.get_or_create(name=name, defaults={"color": request.data.get("color", "")})
        elif kind == "source":
            obj, _ = LeadSource.objects.get_or_create(name=name)
        elif kind == "task_type":
            obj, _ = CrmTaskType.objects.get_or_create(name=name, defaults={"icon": request.data.get("icon", "")})
        else:
            raise ApiError(ErrorCode.MISSING_FIELD, "invalid kind", 400)
        return Response({"success": True, "id": obj.pk}, status=http.HTTP_201_CREATED)


class AdminCrmMetaDeleteView(StaffView):
    @extend_schema(summary="Delete a tag / source / task type")
    def delete(self, request: Request, kind: str, item_id: int) -> Response:
        from .models import CrmTaskType, LeadSource, LeadTag

        model = {"tag": LeadTag, "source": LeadSource, "task_type": CrmTaskType}.get(kind)
        if model is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "invalid kind", 400)
        model.objects.filter(pk=item_id).delete()
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
