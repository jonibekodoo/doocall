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
    return {
        "id": company.pk,
        "name": company.name,
        "status": company.status,
        "acquired_via": company.acquired_via,
        "created_at": company.created_at.isoformat(),
        "seats": billing.seat_count(company),
        "subscription_status": subscription.status if subscription else None,
        "my_cashback_uzs": int(accrued),
    }


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
                "month_cashback_uzs": int(month_sum),
                "min_payout_uzs": get_platform_settings().min_payout_uzs,
                "referral_code": integrator.referral_code,
                "effective_percent": str(integrator.effective_percent),
                "companies_total": companies.count(),
                "companies_active": companies.filter(status="active").count(),
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
                "phone": i.phone,
                "email": cast(User, self.request.user).email,
                "referral_code": i.referral_code,
                "payout_details": i.payout_details,
            }
        )

    @extend_schema(summary="Update profile / payout details")
    def put(self, request: Request) -> Response:
        i = self.integrator
        if "name" in request.data:
            i.name = (request.data["name"] or "").strip() or i.name
        if "phone" in request.data:
            i.phone = request.data["phone"] or ""
        if "payout_details" in request.data and isinstance(request.data["payout_details"], dict):
            i.payout_details = request.data["payout_details"]
        i.save()
        return Response({"success": True})
