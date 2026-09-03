"""Daily-billing cabinet surface: balance, charges breakdown, statements,
in-app notifications. All reachable while the company is payment-blocked."""

from __future__ import annotations

from datetime import date

from django.db.models import Count, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.api.errors import ApiError, ErrorCode
from apps.billing import services as billing
from apps.billing.models import (
    BillingNotification,
    DailyCharge,
    MonthlyStatement,
    Payment,
)
from apps.core.models import AuditLog

from .permissions import CabinetView


def _parse_month(value: str | None) -> date:
    if not value:
        return timezone.now().date().replace(day=1)
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, AttributeError):
        raise ApiError(ErrorCode.MISSING_FIELD, f"invalid month {value!r} (YYYY-MM)", 400) from None


class BillingOverviewView(CabinetView):
    allow_when_suspended = True

    @extend_schema(summary="Balance + this-month accrual + unpaid statement")
    def get(self, request: Request) -> Response:
        company = self.company
        today = timezone.now().date()
        month_start = today.replace(day=1)
        unpaid = (
            MonthlyStatement.objects.exclude(status=MonthlyStatement.Status.PAID)
            .order_by("month")
            .first()
        )
        price = billing.effective_price(company)
        return Response(
            {
                "success": True,
                "balance_uzs": company.balance_uzs,
                "month_accrued_uzs": billing.month_accrued(company, month_start),
                "price_per_operator_uzs": price,
                "daily_rate_uzs": billing.daily_rate(price, today),
                "seats": billing.seat_count(company),
                "blocked": company.status == "suspended",
                "unpaid_statement": {
                    "month": unpaid.month.isoformat(),
                    "total_uzs": unpaid.total_uzs,
                    "status": unpaid.status,
                }
                if unpaid
                else None,
            }
        )


class BillingChargesView(CabinetView):
    allow_when_suspended = True

    @extend_schema(summary="Daily per-operator charges for a month (?month=YYYY-MM)")
    def get(self, request: Request) -> Response:
        month = _parse_month(request.query_params.get("month"))
        if month.month == 12:
            next_month = month.replace(year=month.year + 1, month=1)
        else:
            next_month = month.replace(month=month.month + 1)
        qs = DailyCharge.objects.filter(date__gte=month, date__lt=next_month)
        rows = [
            {
                "date": c.date.isoformat(),
                "operator_name": c.operator_name,
                "amount_uzs": c.amount_uzs,
                "price_per_operator_uzs": c.price_per_operator_uzs,
            }
            for c in qs.order_by("-date", "operator_name")[:1000]
        ]
        by_day = [
            {
                "date": r["date"].isoformat(),
                "total_uzs": int(r["total"] or 0),
                "operators": r["n"],
            }
            for r in qs.values("date")
            .annotate(total=Sum("amount_uzs"), n=Count("id"))
            .order_by("-date")
        ]
        total = int(qs.aggregate(s=Sum("amount_uzs"))["s"] or 0)
        return Response(
            {
                "success": True,
                "month": month.strftime("%Y-%m"),
                "total_uzs": total,
                "days": by_day,
                "charges": rows,
            }
        )


class BillingStatementsView(CabinetView):
    allow_when_suspended = True

    @extend_schema(summary="Monthly statements history")
    def get(self, request: Request) -> Response:
        rows = [
            {
                "month": s.month.strftime("%Y-%m"),
                "total_uzs": s.total_uzs,
                "status": s.status,
                "settled_at": s.settled_at.isoformat() if s.settled_at else None,
            }
            for s in MonthlyStatement.objects.all()[:36]
        ]
        return Response({"success": True, "statements": rows})


class BillingPayView(CabinetView):
    allow_when_suspended = True  # blocked clients must be able to request payment

    @extend_schema(summary="Submit a bank/cash payment request (platform admin approves)")
    def post(self, request: Request) -> Response:
        provider = str(request.data.get("provider") or "manual")
        if provider != Payment.Provider.MANUAL:
            raise ApiError(
                ErrorCode.MISSING_FIELD, "only bank/cash requests are accepted here", 400
            )
        try:
            amount = int(request.data.get("amount_uzs") or 0)
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.MISSING_FIELD, "amount_uzs invalid", 400) from None
        if amount < 1000:
            raise ApiError(ErrorCode.MISSING_FIELD, "amount_uzs invalid", 400)
        # One open request at a time keeps the admin queue clean.
        existing = Payment.objects.filter(
            provider=Payment.Provider.MANUAL, status=Payment.Status.PENDING
        ).first()
        if existing is not None:
            raise ApiError(
                ErrorCode.MISSING_FIELD,
                f"pending request already exists ({existing.amount_uzs} UZS)",
                400,
            )
        payment = Payment.all_objects.create(
            company=self.company, provider=Payment.Provider.MANUAL, amount_uzs=amount
        )
        billing.notify(
            self.company,
            BillingNotification.Kind.PAYMENT_REQUESTED,
            f"Bank/Naqd to'lov so'rovi yuborildi: {amount:,} UZS. "
            "Administrator tasdiqlagach balansingizga tushadi.".replace(",", " "),
            amount,
        )
        AuditLog.objects.create(
            company=self.company,
            actor=request.user,
            action="billing.payment_requested",
            target_model="billing.Payment",
            target_id=str(payment.pk),
            changes={"amount_uzs": amount, "provider": "manual"},
        )
        return Response(
            {
                "success": True,
                "payment": {
                    "id": payment.pk,
                    "amount_uzs": payment.amount_uzs,
                    "status": payment.status,
                },
            },
            status=201,
        )


class NotificationsView(CabinetView):
    allow_when_suspended = True

    @extend_schema(summary="In-app billing notifications (newest first)")
    def get(self, request: Request) -> Response:
        qs = BillingNotification.objects.all()
        unread = qs.filter(is_read=False).count()
        rows = [
            {
                "id": n.pk,
                "kind": n.kind,
                "message": n.message,
                "amount_uzs": n.amount_uzs,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in qs[:50]
        ]
        return Response({"success": True, "unread": unread, "notifications": rows})


class NotificationsReadView(CabinetView):
    allow_when_suspended = True

    @extend_schema(summary="Mark all notifications read")
    def post(self, request: Request) -> Response:
        updated = BillingNotification.objects.filter(is_read=False).update(is_read=True)
        return Response({"success": True, "marked": updated})
