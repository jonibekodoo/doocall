"""Daily-billing cabinet surface: balance, charges breakdown, statements,
in-app notifications. All reachable while the company is payment-blocked."""

from __future__ import annotations

from datetime import date, timedelta

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
    Subscription,
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
        subscription = Subscription.all_objects.filter(company=company).first()
        cycle_start = (
            subscription.current_period_start.date().isoformat()
            if subscription and subscription.current_period_start
            else None
        )
        cycle_end = (
            subscription.current_period_end.date().isoformat()
            if subscription and subscription.current_period_end
            else None
        )
        return Response(
            {
                "success": True,
                "balance_uzs": company.balance_uzs,
                "month_accrued_uzs": billing.month_accrued(company, month_start),
                # Billing cycle: usage accrued since the last deduction and the
                # date the balance will next be charged (cycle end).
                "cycle_accrued_uzs": billing.cycle_accrued(company),
                "cycle_start": cycle_start,
                "cycle_end": cycle_end,
                # How long the prepaid balance lasts at the CURRENT burn rate
                # (active operators × daily rate) — reacts to adding/removing operators.
                "days_left": (days_left := billing.days_of_balance_left(company, day=today)),
                "runs_out_on": (today + timedelta(days=days_left)).isoformat()
                if days_left is not None
                else None,
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
                "period_start": s.period_start.isoformat() if s.period_start else None,
                # Inclusive last day for display (stored end is exclusive).
                "period_end": (s.period_end - timedelta(days=1)).isoformat() if s.period_end else None,
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


# ── Localised user-facing payment messages (uz / ru / en) ───────────────────
# The cabinet UI language lives in the `doocall_locale` cookie, which the
# browser sends with every same-origin API call; fall back to Accept-Language,
# then Uzbek. Keys cover both our own validation and Paylov's error codes.
_LOCALES = ("uz", "ru", "en")
_MSG: dict[str, dict[str, str]] = {
    # ── our own validation / state ──
    "provider_disabled": {
        "uz": "Paylov orqali to'lov hozircha yoqilmagan",
        "ru": "Оплата через Paylov пока недоступна",
        "en": "Paylov payments are not enabled yet",
    },
    "not_configured": {
        "uz": "Paylov sozlanmagan — administratorga murojaat qiling",
        "ru": "Paylov не настроен — обратитесь к администратору",
        "en": "Paylov is not configured — contact the administrator",
    },
    "amount_invalid": {
        "uz": "Summa noto'g'ri (kamida 1 000 so'm)",
        "ru": "Неверная сумма (минимум 1 000 сум)",
        "en": "Invalid amount (minimum 1,000 UZS)",
    },
    "card_invalid": {
        "uz": "Karta raqami noto'g'ri",
        "ru": "Неверный номер карты",
        "en": "Invalid card number",
    },
    "expire_invalid": {
        "uz": "Amal muddati noto'g'ri (OO/YY)",
        "ru": "Неверный срок действия (ММ/ГГ)",
        "en": "Invalid expiry date (MM/YY)",
    },
    "no_transaction": {
        "uz": "Paylov tranzaksiya yaratmadi — qaytadan urinib ko'ring",
        "ru": "Paylov не создал транзакцию — попробуйте ещё раз",
        "en": "Paylov did not create a transaction — please try again",
    },
    "payment_id_invalid": {
        "uz": "To'lov identifikatori noto'g'ri",
        "ru": "Неверный идентификатор платежа",
        "en": "Invalid payment id",
    },
    "otp_required": {
        "uz": "SMS kodini (OTP) kiriting",
        "ru": "Введите SMS-код (OTP)",
        "en": "Enter the SMS code (OTP)",
    },
    "payment_not_found": {
        "uz": "To'lov topilmadi",
        "ru": "Платёж не найден",
        "en": "Payment not found",
    },
    "not_confirmable": {
        "uz": "Bu to'lovni tasdiqlab bo'lmaydi — qaytadan boshlang",
        "ru": "Этот платёж нельзя подтвердить — начните заново",
        "en": "This payment cannot be confirmed — please start again",
    },
    "otp_not_confirmed": {
        "uz": "OTP tasdiqlanmadi — kodni tekshirib qayta kiriting",
        "ru": "OTP не подтверждён — проверьте код и введите снова",
        "en": "OTP not confirmed — check the code and try again",
    },
    "generic": {
        "uz": "To'lovda xatolik yuz berdi — birozdan so'ng qayta urinib ko'ring",
        "ru": "Ошибка при оплате — попробуйте позже",
        "en": "Payment error — please try again later",
    },
    # ── Paylov API error codes ──
    "invalid_otp": {
        "uz": "SMS kod (OTP) noto'g'ri",
        "ru": "Неверный SMS-код (OTP)",
        "en": "Incorrect SMS code (OTP)",
    },
    "otp_expired": {
        "uz": "SMS kod muddati o'tgan — to'lovni qaytadan boshlang",
        "ru": "Срок действия SMS-кода истёк — начните оплату заново",
        "en": "The SMS code has expired — please start the payment again",
    },
    "insufficient_funds": {
        "uz": "Kartada mablag' yetarli emas",
        "ru": "Недостаточно средств на карте",
        "en": "Insufficient funds on the card",
    },
    "card_is_blocked": {
        "uz": "Karta bloklangan",
        "ru": "Карта заблокирована",
        "en": "The card is blocked",
    },
    "card_expired": {
        "uz": "Karta muddati tugagan",
        "ru": "Срок действия карты истёк",
        "en": "The card has expired",
    },
    "card_not_found": {
        "uz": "Karta topilmadi — raqam va muddatni tekshiring",
        "ru": "Карта не найдена — проверьте номер и срок действия",
        "en": "Card not found — check the number and expiry date",
    },
    "card_has_no_phone": {
        "uz": "Kartaga telefon raqam biriktirilmagan (SMS-xabar xizmati kerak)",
        "ru": "К карте не привязан номер телефона (нужна услуга SMS-информирования)",
        "en": "No phone number is linked to this card (SMS notifications required)",
    },
    "too_many_attempts": {
        "uz": "Juda ko'p urinish — birozdan so'ng qayta urinib ko'ring",
        "ru": "Слишком много попыток — попробуйте позже",
        "en": "Too many attempts — please try again later",
    },
    "card_is_not_supported": {
        "uz": "Bu karta turi qo'llab-quvvatlanmaydi (UzCard yoki Humo kiriting)",
        "ru": "Этот тип карты не поддерживается (введите UzCard или Humo)",
        "en": "This card type is not supported (use UzCard or Humo)",
    },
    "invalid_card": {
        "uz": "Karta ma'lumotlari noto'g'ri",
        "ru": "Неверные данные карты",
        "en": "Invalid card details",
    },
    "pan_not_valid": {
        "uz": "Karta raqami noto'g'ri",
        "ru": "Неверный номер карты",
        "en": "Invalid card number",
    },
    "invalid_amount": {
        "uz": "Summa noto'g'ri",
        "ru": "Неверная сумма",
        "en": "Invalid amount",
    },
    "sms_not_active": {
        "uz": "Kartada SMS-xabar xizmati yoqilmagan",
        "ru": "На карте не подключено SMS-информирование",
        "en": "SMS notifications are not enabled for this card",
    },
    "transaction_not_found": {
        "uz": "Tranzaksiya topilmadi — to'lovni qaytadan boshlang",
        "ru": "Транзакция не найдена — начните оплату заново",
        "en": "Transaction not found — please start the payment again",
    },
    "transaction_already_payed": {
        "uz": "Bu to'lov allaqachon amalga oshirilgan",
        "ru": "Этот платёж уже выполнен",
        "en": "This payment has already been completed",
    },
    "validation_error": {
        "uz": "Kiritilgan ma'lumotlar noto'g'ri — karta raqami va muddatni tekshiring",
        "ru": "Введённые данные неверны — проверьте номер карты и срок действия",
        "en": "The entered data is invalid — check the card number and expiry date",
    },
    "connection_failed": {
        "uz": "To'lov tizimi bilan aloqa yo'q — birozdan so'ng qayta urinib ko'ring",
        "ru": "Нет связи с платёжной системой — попробуйте позже",
        "en": "Cannot reach the payment provider — please try again later",
    },
    "http_error": {
        "uz": "To'lov tizimi vaqtincha ishlamayapti — birozdan so'ng qayta urinib ko'ring",
        "ru": "Платёжная система временно недоступна — попробуйте позже",
        "en": "The payment provider is temporarily unavailable — please try again later",
    },
    "auth_failed": {
        "uz": "To'lov tizimiga ulanishda xatolik — administratorga murojaat qiling",
        "ru": "Ошибка подключения к платёжной системе — обратитесь к администратору",
        "en": "Payment provider authentication failed — contact the administrator",
    },
    "ip_not_allowed": {
        "uz": "To'lov tizimi so'rovni rad etdi — administratorga murojaat qiling",
        "ru": "Платёжная система отклонила запрос — обратитесь к администратору",
        "en": "The payment provider rejected the request — contact the administrator",
    },
    "merchant_not_available": {
        "uz": "To'lov qabul qilish vaqtincha to'xtatilgan",
        "ru": "Приём платежей временно приостановлен",
        "en": "Payments are temporarily unavailable",
    },
    "processing_error": {
        "uz": "Bank tomonida xatolik — birozdan so'ng qayta urinib ko'ring",
        "ru": "Ошибка на стороне банка — попробуйте позже",
        "en": "Bank processing error — please try again later",
    },
}
# Paylov codes that map onto an existing message key.
_CODE_ALIASES = {
    "card_is_blocked_in_processing_center": "card_is_blocked",
    "card_not_found_in_processing_center": "card_not_found",
    "already_confirmed": "transaction_already_payed",
    "transaction_not_available_for_payment": "not_confirmable",
    "error_at_pay": "processing_error",
    "gateway_not_working": "http_error",
    "server_error": "http_error",
    "unknown_error": "generic",
    "field_required": "validation_error",
    "field_not_valid": "validation_error",
}


def _locale(request: Request) -> str:
    cookie = (request.COOKIES.get("doocall_locale") or "").lower()
    if cookie in _LOCALES:
        return cookie
    accept = (request.headers.get("Accept-Language") or "").lower()
    for loc in _LOCALES:
        if accept.startswith(loc):
            return loc
    return "uz"


def _t(request: Request, key: str) -> str:
    msg = _MSG.get(key) or _MSG["generic"]
    return msg.get(_locale(request)) or msg["uz"]


def _paylov_error(request: Request, e: Exception) -> ApiError:
    """Translate a PaylovError into a localised ApiError (keeps the raw code)."""
    code = getattr(e, "code", "") or ""
    key = _CODE_ALIASES.get(code, code)
    # PaylovError stores the bare code as its message when Paylov sent none —
    # never show a raw code to the user; prefer the localised generic text.
    raw = getattr(e, "message", "") or ""
    if raw == code:
        raw = ""
    text = _t(request, key) if key in _MSG else (raw or _t(request, "generic"))
    return ApiError(ErrorCode.MISSING_FIELD, text, 400, extra={"paylov_code": code})


class BillingPaylovPayView(CabinetView):
    allow_when_suspended = True  # a blocked company must be able to top up

    @extend_schema(summary="Start a Paylov card payment (card → transactionId, OTP sent)")
    def post(self, request: Request) -> Response:
        from django.conf import settings as dj

        from apps.billing import paylov_api

        cfg = PaymentProviderConfig.objects.filter(provider="paylov", is_enabled=True).first()
        if cfg is None:
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "provider_disabled"), 400)
        if not (dj.PAYLOV_CONSUMER_KEY and dj.PAYLOV_API_USERNAME):
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "not_configured"), 400)
        try:
            amount = int(request.data.get("amount_uzs") or 0)
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "amount_invalid"), 400) from None
        if amount < 1000:
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "amount_invalid"), 400)
        card = "".join((request.data.get("card_number") or "").split())
        expire = (request.data.get("expire_date") or "").strip()
        if not (card.isdigit() and 12 <= len(card) <= 19):
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "card_invalid"), 400)
        if not (expire.isdigit() and len(expire) == 4):
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "expire_invalid"), 400)

        payment = Payment.all_objects.create(
            company=self.company, provider=Payment.Provider.PAYLOV, amount_uzs=amount
        )
        try:
            # Paylov "Payment Without Registration": amount is in SOM
            # ("1000 = 1 Thousand SUM"). Sending tiyin (×100) made the gateway
            # try to charge 100× the top-up → insufficient_funds on real cards.
            resp = paylov_api.payment_without_registration(
                card, expire, amount, {"order_id": str(payment.pk)}, payment=payment
            )
        except paylov_api.PaylovError as e:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            raise _paylov_error(request, e) from None

        result = resp.get("result") or {}
        txn = result.get("transactionId") or resp.get("transactionId")
        if not txn:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "no_transaction"), 400)
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
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "payment_id_invalid"), 400) from None
        otp = (request.data.get("otp") or "").strip()
        if not otp:
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "otp_required"), 400)
        payment = Payment.all_objects.filter(
            pk=pid, company=self.company, provider=Payment.Provider.PAYLOV
        ).first()
        if payment is None:
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "payment_not_found"), 404)
        if payment.status == Payment.Status.APPROVED:
            return Response({"success": True, "status": payment.status})
        if payment.status != Payment.Status.PENDING or not payment.external_id:
            raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "not_confirmable"), 400)

        # ── The ONLY path that credits money: Paylov must confirm the charge. ──
        try:
            resp = paylov_api.confirm_payment(payment.external_id, otp, payment=payment)
        except paylov_api.PaylovError as e:
            # Paylov itself reporting "already paid" IS a confirmation (e.g. our
            # earlier confirm crashed after Paylov charged the card).
            if e.code not in ("transaction_already_payed", "already_confirmed"):
                raise _paylov_error(request, e) from None
        else:
            # A 2xx with no "result" (e.g. otp_required / result:null) is NOT a
            # completed payment — never credit on it.
            if not resp.get("result"):
                raise ApiError(ErrorCode.MISSING_FIELD, _t(request, "otp_not_confirmed"), 400)

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
