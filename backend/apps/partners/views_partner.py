"""Partner portal API — /api/partner/v1 (role=integrator).

Commercial data ONLY: an integrator can never see a company's CallRecords,
Contacts, Users or devices — no endpoint here exposes them.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.api.errors import ApiError, ErrorCode
from apps.billing import services as billing
from apps.billing.models import Subscription
from apps.companies.models import Company
from apps.core.models import AuditLog

from . import services
from .models import CashbackAccrual, Integrator, PayoutRequest
from .permissions import IsIntegrator


class PartnerView(APIView):
    permission_classes = [IsIntegrator]

    @property
    def integrator(self) -> Integrator:
        return cast(User, self.request.user).integrator_profile


def _partner_company_body(company: Company, integrator: Integrator) -> dict[str, Any]:
    """Commercial fields only — never operational data."""
    subscription = Subscription.all_objects.filter(company=company).first()
    accrued = (
        CashbackAccrual.objects.filter(company=company, integrator=integrator)
        .exclude(status=CashbackAccrual.Status.REVERSED)
        .aggregate(s=Sum("amount_uzs"))["s"]
        or 0
    )
    from django.utils import timezone as _tz

    trial_expired = (
        company.status == Company.Status.TRIAL
        and company.trial_ends_at is not None
        and company.trial_ends_at < _tz.now()
    )
    return {
        "id": company.pk,
        "name": company.name,
        "status": company.status,
        # Trial whose end date has passed (suspended by the hourly task; shown
        # as "trial expired" immediately so the partner sees the real state).
        "trial_expired": trial_expired,
        "trial_ends_at": company.trial_ends_at.isoformat() if company.trial_ends_at else None,
        "acquired_via": company.acquired_via,
        "created_at": company.created_at.isoformat(),
        "seats": billing.seat_count(company),
        "subscription_status": subscription.status if subscription else None,
        "my_cashback_uzs": int(accrued),
    }


EXPIRING_WITHIN_DAYS = 3


def expiring_companies(companies: Any, *, now: Any) -> list[dict[str, Any]]:
    """Companies that will go offline within the next few days — either a
    trial about to end or a prepaid balance about to run out — so the partner
    can chase the payment before the cabinet locks. Sorted soonest first."""
    rows: list[dict[str, Any]] = []
    horizon = now + timedelta(days=EXPIRING_WITHIN_DAYS)
    for c in companies.filter(
        status=Company.Status.TRIAL, trial_ends_at__gte=now, trial_ends_at__lte=horizon
    ):
        rows.append(
            {
                "id": c.pk,
                "name": c.name,
                "reason": "trial",
                "days_left": (c.trial_ends_at - now).days,
                "ends_on": c.trial_ends_at.date().isoformat(),
            }
        )
    for c in companies.filter(status=Company.Status.ACTIVE):
        left = billing.days_of_balance_left(c)
        if left is not None and left <= EXPIRING_WITHIN_DAYS:
            rows.append(
                {
                    "id": c.pk,
                    "name": c.name,
                    "reason": "balance",
                    "days_left": left,
                    "ends_on": (now + timedelta(days=left)).date().isoformat(),
                }
            )
    rows.sort(key=lambda r: (r["days_left"], r["name"]))
    return rows


class PartnerDashboardView(PartnerView):
    @extend_schema(summary="Partner KPIs + 12-month accrual series")
    def get(self, request: Request) -> Response:
        integrator = self.integrator
        companies = integrator.companies.all()
        totals = CashbackAccrual.objects.filter(integrator=integrator).aggregate(
            accrued=Sum("amount_uzs", filter=None),
        )
        paid = (
            PayoutRequest.objects.filter(
                integrator=integrator, status=PayoutRequest.Status.PAID
            ).aggregate(s=Sum("amount_uzs"))["s"]
            or 0
        )
        from django.utils import timezone as tz

        month_start = tz.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_sum = (
            CashbackAccrual.objects.filter(integrator=integrator, created_at__gte=month_start)
            .exclude(status=CashbackAccrual.Status.REVERSED)
            .aggregate(s=Sum("amount_uzs"))["s"]
            or 0
        )
        from .models import get_platform_settings

        return Response(
            {
                "success": True,
                "expiring": expiring_companies(companies, now=tz.now()),
                "month_cashback_uzs": int(month_sum),
                "min_payout_uzs": get_platform_settings().min_payout_uzs,
                "referral_code": integrator.referral_code,
                "effective_percent": str(integrator.effective_percent),
                "companies_total": companies.count(),
                "companies_active": companies.filter(status="active").count(),
                # Status breakdown (trial split into running / expired).
                "companies_by_status": {
                    "active": companies.filter(status=Company.Status.ACTIVE).count(),
                    "trial": companies.filter(
                        status=Company.Status.TRIAL, trial_ends_at__gte=tz.now()
                    ).count(),
                    "trial_expired": companies.filter(
                        status=Company.Status.TRIAL, trial_ends_at__lt=tz.now()
                    ).count(),
                    "suspended": companies.filter(status=Company.Status.SUSPENDED).count(),
                },
                "balance_uzs": integrator.balance_uzs,
                "paid_out_uzs": int(paid),
                "accrued_total_uzs": int(totals["accrued"] or 0),
                "monthly_series": services.monthly_accrual_series(integrator),
            }
        )


class PartnerCompaniesView(PartnerView):
    @extend_schema(summary="My companies (commercial fields only)")
    def get(self, request: Request) -> Response:
        rows = [
            _partner_company_body(c, self.integrator)
            for c in self.integrator.companies.all().order_by("-created_at")
        ]
        return Response({"success": True, "companies": rows})

    @extend_schema(summary="Register a company on behalf of a client")
    def post(self, request: Request) -> Response:
        name = (request.data.get("company_name") or "").strip()
        email = (request.data.get("admin_email") or "").strip().lower()
        phone = (request.data.get("phone") or "").strip()
        password = request.data.get("password") or ""
        if not name or not email or len(password) < 8:
            raise ApiError(
                ErrorCode.MISSING_FIELD, "company_name, admin_email, password(≥8) required", 400
            )
        slug = slugify(name)
        if not slug or Company.objects.filter(slug=slug).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "company name already taken", 400)
        if User.objects.filter(username=email).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "email already registered", 400)

        trial_days = billing.effective_trial_days()
        now = timezone.now()
        with transaction.atomic():
            company = Company(
                name=name,
                slug=slug,
                status=Company.Status.TRIAL,
                trial_ends_at=now + timedelta(days=trial_days),
                integrator=self.integrator,
                acquired_via=Company.AcquiredVia.INTEGRATOR_MANUAL,
            )
            company.save()
            User.objects.create_user(
                username=email,
                email=email,
                password=password,
                phone=phone,
                company=company,
                is_company_admin=True,
            )
            Subscription.all_objects.create(
                company=company,
                status=Subscription.Status.TRIAL,
                price_per_operator_uzs=billing.effective_price(company),
                trial_ends_at=company.trial_ends_at,
            )
            AuditLog.objects.create(
                company=company,
                actor=cast(User, request.user),
                action="partner.company_registered",
                target_model="companies.Company",
                target_id=str(company.pk),
            )
        return Response(
            {"success": True, "company": _partner_company_body(company, self.integrator)},
            status=http.HTTP_201_CREATED,
        )


class PartnerCompanyDetailView(PartnerView):
    @extend_schema(summary="My company detail (commercial only)")
    def get(self, request: Request, company_id: int) -> Response:
        company = self.integrator.companies.filter(pk=company_id).first()
        if company is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "company not found", 404)
        body = _partner_company_body(company, self.integrator)
        body["accruals"] = [
            {
                "id": a.pk,
                "amount_uzs": a.amount_uzs,
                "percent": str(a.percent),
                "status": a.status,
                "created_at": a.created_at.isoformat(),
            }
            for a in CashbackAccrual.objects.filter(company=company, integrator=self.integrator)[
                :50
            ]
        ]
        # Aggregate, non-PII activity stats only — never individual CallRecords,
        # contacts or operator identities (partner boundary, see module docstring).
        from apps.calls.stats import company_call_stats

        body["stats"] = company_call_stats(company, include_operators=False)
        return Response({"success": True, "company": body})


class PartnerAccrualsView(PartnerView):
    @extend_schema(summary="Accrual ledger (status/company/date filters)")
    def get(self, request: Request) -> Response:
        qs = CashbackAccrual.objects.filter(integrator=self.integrator).select_related("company")
        if status_f := request.query_params.get("status"):
            qs = qs.filter(status=status_f)
        if company_id := request.query_params.get("company"):
            qs = qs.filter(company_id=company_id)
        if date_from := request.query_params.get("date_from"):
            qs = qs.filter(created_at__date__gte=date_from)
        rows = [
            {
                "id": a.pk,
                "company": a.company.name,
                "company_id": a.company_id,
                "amount_uzs": a.amount_uzs,
                "percent": str(a.percent),
                "status": a.status,
                "created_at": a.created_at.isoformat(),
            }
            for a in qs[:200]
        ]
        return Response({"success": True, "accruals": rows})


class PartnerPayoutsView(PartnerView):
    @extend_schema(summary="My payout requests")
    def get(self, request: Request) -> Response:
        rows = [
            {
                "id": p.pk,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "note": p.note,
                "requested_at": p.requested_at.isoformat(),
                "processed_at": p.processed_at.isoformat() if p.processed_at else None,
            }
            for p in PayoutRequest.objects.filter(integrator=self.integrator)[:100]
        ]
        from .models import get_platform_settings

        return Response(
            {
                "success": True,
                "payouts": rows,
                "balance_uzs": self.integrator.balance_uzs,
                "min_payout_uzs": get_platform_settings().min_payout_uzs,
            }
        )

    @extend_schema(summary="Request a payout (≤ available balance)")
    def post(self, request: Request) -> Response:
        try:
            amount = int(request.data.get("amount_uzs", 0))
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.MISSING_FIELD, "amount_uzs must be an integer", 400) from None
        try:
            payout = services.request_payout(
                self.integrator, amount, note=request.data.get("note", "")
            )
        except services.PayoutError as exc:
            raise ApiError(ErrorCode.MISSING_FIELD, str(exc), 400) from None
        return Response(
            {"success": True, "payout_id": payout.pk, "balance_uzs": self.integrator.balance_uzs},
            status=http.HTTP_201_CREATED,
        )


class PartnerProfileView(PartnerView):
    @extend_schema(summary="Profile + payout details")
    def get(self, request: Request) -> Response:
        i = self.integrator
        return Response(
            {
                "success": True,
                "name": i.name,
                "company_name": i.company_name,
                "logo_url": f"/api/public/integrator-logo/{i.pk}" if i.logo_key else None,
                "is_public": i.is_public,
                "phone": i.phone,
                "email": cast(User, self.request.user).email,
                "referral_code": i.referral_code,
                "payout_details": i.payout_details,
                "bank_card": i.bank_card,
                "bank_mfo": i.bank_mfo,
                "bank_inn": i.bank_inn,
                "bank_transit": i.bank_transit,
                "offer": self._offer_body(i),
            }
        )

    @staticmethod
    def _offer_body(i: Integrator) -> dict[str, Any]:
        from .models import get_offer_document

        offer = get_offer_document()
        return {
            "content": offer.content,
            "version": offer.version,
            "accepted": i.offer_accepted_version >= offer.version and offer.version > 0,
            "accepted_at": i.offer_accepted_at.isoformat() if i.offer_accepted_at else None,
        }

    @extend_schema(summary="Update profile / payout details")
    def put(self, request: Request) -> Response:
        i = self.integrator
        if "name" in request.data:
            i.name = (request.data["name"] or "").strip() or i.name
        if "company_name" in request.data:
            i.company_name = (request.data["company_name"] or "").strip()
        if "phone" in request.data:
            i.phone = request.data["phone"] or ""
        if "payout_details" in request.data and isinstance(request.data["payout_details"], dict):
            i.payout_details = request.data["payout_details"]
        if "is_public" in request.data:
            i.is_public = bool(request.data["is_public"])
        for bank_field in ("bank_card", "bank_mfo", "bank_inn", "bank_transit"):
            if bank_field in request.data:
                setattr(i, bank_field, (request.data[bank_field] or "").strip())
        if request.data.get("accept_offer"):
            from .models import get_offer_document

            offer = get_offer_document()
            i.offer_accepted_version = offer.version
            i.offer_accepted_at = timezone.now()
        i.save()
        return Response({"success": True})


class PartnerLogoView(PartnerView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary="Upload own company logo")
    def post(self, request: Request) -> Response:
        import io
        import uuid

        from django.conf import settings as dj

        from apps.api import storage

        i = self.integrator
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
            dj.MINIO_BUCKET, key, io.BytesIO(payload), length=len(payload), content_type=content_type
        )
        i.logo_key = key
        i.save(update_fields=["logo_key", "updated_at"])
        return Response({"success": True, "logo_url": f"/api/public/integrator-logo/{i.pk}"})
