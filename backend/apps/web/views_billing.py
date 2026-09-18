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
    PaymentProviderConfig,
    ensure_provider_configs,
)
from apps.core.models import AuditLog

from .permissions import CabinetView


def _enabled_provider_rows() -> list[dict]:
    """Enabled providers the cabinet may offer (code, label, logo)."""
    from django.conf import settings as dj

    ensure_provider_configs()
    rows = []
    for cfg in PaymentProviderConfig.objects.filter(is_enabled=True).order_by("sort_order"):
        # Never offer Paylov to a customer until its API credentials are configured.
        if cfg.provider == "paylov" and not (dj.PAYLOV_CONSUMER_KEY and dj.PAYLOV_API_USERNAME):
            continue
        try:
            label = Payment.Provider(cfg.provider).label
        except ValueError:
            label = cfg.provider
        rows.append(
            {
                "name": cfg.provider,
                "label": label,
                "logo_url": f"/api/public/provider-logo/{cfg.provider}" if cfg.logo_key else None,
            }
        )
    return rows


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
                "providers": _enabled_provider_rows(),
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


# Human-friendly Uzbek messages for Paylov API error codes.
_PAYLOV_MESSAGES = {
    "invalid_otp": "OTP kod noto'g'ri",
    "otp_expired": "OTP muddati o'tgan, qaytadan urinib ko'ring",
    "insufficient_funds": "Kartada mablag' yetarli emas",
    "card_is_blocked": "Karta bloklangan",
    "card_is_blocked_in_processing_center": "Karta bloklangan",
    "card_expired": "Karta muddati o'tgan",
    "card_not_found": "Karta topilmadi",
    "card_not_found_in_processing_center": "Karta topilmadi",
    "card_has_no_phone": "Kartaga telefon raqam biriktirilmagan",
    "too_many_attempts": "Juda ko'p urinish — birozdan so'ng qayta urinib ko'ring",
    "card_is_not_supported": "Bu karta turi qo'llab-quvvatlanmaydi",
    "invalid_card": "Karta ma'lumoti noto'g'ri",
    "pan_not_valid": "Karta raqami noto'g'ri",
    "invalid_amount": "Summa noto'g'ri",
    "sms_not_active": "Kartada SMS-xabar xizmati yoqilmagan",
    "transaction_not_found": "Tranzaksiya topilmadi",
    "transaction_already_payed": "Bu to'lov allaqachon amalga oshirilgan",
}


def _paylov_msg(e) -> str:
    return _PAYLOV_MESSAGES.get(getattr(e, "code", ""), getattr(e, "message", "") or "To'lovda xatolik")


class BillingPaylovPayView(CabinetView):
    allow_when_suspended = True  # a blocked company must be able to top up

    @extend_schema(summary="Start a Paylov card payment (card → transactionId, OTP sent)")
    def post(self, request: Request) -> Response:
        from django.conf import settings as dj

        from apps.billing import paylov_api

        cfg = PaymentProviderConfig.objects.filter(provider="paylov", is_enabled=True).first()
        if cfg is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "Paylov to'lovi yoqilmagan", 400)
        if not (dj.PAYLOV_CONSUMER_KEY and dj.PAYLOV_API_USERNAME):
            raise ApiError(ErrorCode.MISSING_FIELD, "Paylov sozlanmagan", 400)
        try:
            amount = int(request.data.get("amount_uzs") or 0)
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.MISSING_FIELD, "amount_uzs invalid", 400) from None
        if amount < 1000:
            raise ApiError(ErrorCode.MISSING_FIELD, "amount_uzs invalid", 400)
        card = "".join((request.data.get("card_number") or "").split())
        expire = (request.data.get("expire_date") or "").strip()
        if not (card.isdigit() and 12 <= len(card) <= 19):
            raise ApiError(ErrorCode.MISSING_FIELD, "Karta raqami noto'g'ri", 400)
        if not (expire.isdigit() and len(expire) == 4):
            raise ApiError(ErrorCode.MISSING_FIELD, "Amal muddati noto'g'ri (YYMM)", 400)

        payment = Payment.all_objects.create(
            company=self.company, provider=Payment.Provider.PAYLOV, amount_uzs=amount
        )
        try:
            resp = paylov_api.payment_without_registration(
                card, expire, amount * 100, {"order_id": str(payment.pk)}, payment=payment
            )
        except paylov_api.PaylovError as e:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            raise ApiError(ErrorCode.MISSING_FIELD, _paylov_msg(e), 400) from None

        result = resp.get("result") or {}
        txn = result.get("transactionId") or resp.get("transactionId")
        if not txn:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            raise ApiError(ErrorCode.MISSING_FIELD, "Paylov javobida transactionId yo'q", 400)
        payment.external_id = txn
        payment.save(update_fields=["external_id"])
        AuditLog.objects.create(
            company=self.company, actor=request.user, action="billing.paylov_pay_created",
            target_model="billing.Payment", target_id=str(payment.pk), changes={"amount_uzs": amount},
        )
        otp_phone = result.get("otpSentPhone") or resp.get("otp_phone") or ""
        return Response(
            {"success": True, "payment_id": payment.pk, "otp_phone": otp_phone, "needs_otp": True},
            status=201,
        )


class BillingPaylovConfirmView(CabinetView):
    allow_when_suspended = True

    @extend_schema(summary="Confirm a Paylov card payment with the OTP → credit balance")
    def post(self, request: Request) -> Response:
        from apps.billing import paylov_api

        try:
            pid = int(request.data.get("payment_id") or 0)
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.MISSING_FIELD, "payment_id invalid", 400) from None
        otp = (request.data.get("otp") or "").strip()
        if not otp:
            raise ApiError(ErrorCode.MISSING_FIELD, "OTP kiriting", 400)
        payment = Payment.all_objects.filter(
            pk=pid, company=self.company, provider=Payment.Provider.PAYLOV
        ).first()
        if payment is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "To'lov topilmadi", 404)
        if payment.status == Payment.Status.APPROVED:
            return Response({"success": True, "status": payment.status})
        if payment.status != Payment.Status.PENDING or not payment.external_id:
            raise ApiError(ErrorCode.MISSING_FIELD, "To'lov tasdiqlash uchun yaroqsiz", 400)

        # ── The ONLY path that credits money: Paylov must confirm the charge. ──
        try:
            resp = paylov_api.confirm_payment(payment.external_id, otp, payment=payment)
        except paylov_api.PaylovError as e:
            # Paylov itself reporting "already paid" IS a confirmation (e.g. our
            # earlier confirm crashed after Paylov charged the card).
            if e.code not in ("transaction_already_payed", "already_confirmed"):
                raise ApiError(ErrorCode.MISSING_FIELD, _paylov_msg(e), 400) from None
        else:
            # A 2xx with no "result" (e.g. otp_required / result:null) is NOT a
            # completed payment — never credit on it.
            if not resp.get("result"):
                raise ApiError(ErrorCode.MISSING_FIELD, "OTP tasdiqlanmadi", 400)

        # Lock the row so two concurrent confirms can never credit twice.
        from django.db import transaction as db_tx

        with db_tx.atomic():
            locked = Payment.all_objects.select_for_update().get(pk=payment.pk)
            if locked.status != Payment.Status.APPROVED:
                billing.apply_payment(locked, actor=request.user)
        self.company.refresh_from_db(fields=["balance_uzs"])
        return Response(
            {"success": True, "status": Payment.Status.APPROVED, "balance_uzs": self.company.balance_uzs}
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


class NotificationReadOneView(CabinetView):
    allow_when_suspended = True

    @extend_schema(summary="Mark ONE notification read (click-to-open)")
    def post(self, request: Request, note_id: int) -> Response:
        updated = BillingNotification.objects.filter(pk=note_id).update(is_read=True)
        if not updated:
            raise ApiError(ErrorCode.MISSING_FIELD, "notification not found", 404)
        return Response({"success": True})
