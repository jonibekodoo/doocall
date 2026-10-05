"""Cabinet: saved cards + auto-payment (/api/web/v1/billing/cards|autopay).

Reading is open to every cabinet user of the company; linking/removing a
card, paying with it and changing auto-pay are for the company admin only.
All money movement goes through ``apps.billing.autopay.charge_saved_card``.
"""

from __future__ import annotations

from typing import Any, cast

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.api.errors import ApiError, ErrorCode
from apps.billing import autopay, paylov_api
from apps.billing.models import AutoPaySettings, SavedCard
from apps.core.models import AuditLog

from .permissions import CabinetView
from .views_billing import _locale, _paylov_error

_TEXT: dict[str, dict[str, str]] = {
    "admin_only": {
        "uz": "Bu amal faqat kompaniya administratori uchun",
        "ru": "Это действие доступно только администратору компании",
        "en": "Only the company administrator can do this",
    },
    "unavailable": {
        "uz": "Karta orqali to'lov hozircha yoqilmagan",
        "ru": "Оплата картой пока недоступна",
        "en": "Card payments are not enabled yet",
    },
    "card_invalid": {"uz": "Karta raqami noto'g'ri", "ru": "Неверный номер карты", "en": "Invalid card number"},
    "expire_invalid": {
        "uz": "Amal muddati noto'g'ri (OO/YY)",
        "ru": "Неверный срок действия (ММ/ГГ)",
        "en": "Invalid expiry date (MM/YY)",
    },
    "card_limit": {
        "uz": "Kartalar soni chegaraga yetdi — avval birini olib tashlang",
        "ru": "Достигнут лимит карт — сначала удалите одну",
        "en": "Card limit reached — remove one first",
    },
    "card_missing": {"uz": "Karta topilmadi", "ru": "Карта не найдена", "en": "Card not found"},
    "otp_required": {"uz": "SMS kodini kiriting", "ru": "Введите SMS-код", "en": "Enter the SMS code"},
    "consent_required": {
        "uz": "Avto to'lovni yoqish uchun rozilikni tasdiqlang",
        "ru": "Чтобы включить автоплатёж, подтвердите согласие",
        "en": "Confirm your consent to turn auto-payment on",
    },
    "card_required": {
        "uz": "Avto to'lov uchun avval kartani bog'lang",
        "ru": "Для автоплатежа сначала привяжите карту",
        "en": "Link a card first to use auto-payment",
    },
    "amount_invalid": {
        "uz": "Summa noto'g'ri (kamida 1 000 so'm)",
        "ru": "Неверная сумма (минимум 1 000 сум)",
        "en": "Invalid amount (minimum 1,000 UZS)",
    },
    "limit_invalid": {
        "uz": "Oylik limit yechiladigan summadan kam bo'lmasligi kerak",
        "ru": "Месячный лимит не может быть меньше суммы списания",
        "en": "The monthly limit cannot be below the charge amount",
    },
    "pending": {
        "uz": "To'lov natijasi tekshirilmoqda — balans tasdiqlangach yangilanadi. Qayta to'lamang.",
        "ru": "Результат платежа проверяется — баланс обновится после подтверждения. Не платите повторно.",
        "en": "The payment is being verified — the balance updates once confirmed. Do not pay again.",
    },
}


def _msg(request: Request, key: str) -> str:
    row = _TEXT[key]
    return row.get(_locale(request)) or row["uz"]


def _card_body(card: SavedCard) -> dict[str, Any]:
    return {
        "id": card.pk,
        "masked_number": card.masked_number,
        "owner": card.owner,
        "vendor": card.vendor,
        "expire": card.expire,
        "is_active": card.is_active,
    }


class _AutopayBase(CabinetView):
    allow_when_suspended = True  # a blocked company must be able to pay

    def require_admin(self, request: Request) -> None:
        if not getattr(request.user, "is_company_admin", False):
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "admin_only"), 403)
        if not autopay.cards_available():
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "unavailable"), 400)

    def card(self, request: Request, card_id: int, *, confirmed: bool = True) -> SavedCard:
        card = SavedCard.objects.filter(pk=card_id, is_active=True, is_confirmed=confirmed).first()
        if card is None:
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "card_missing"), 404)
        return card

    def body(self, request: Request) -> dict[str, Any]:
        company = self.company
        row = autopay.get_settings(company)
        q = autopay.quote(company, row)
        lang = _locale(request)
        cards = SavedCard.objects.filter(is_confirmed=True, is_active=True)
        return {
            "success": True,
            "can_manage": bool(getattr(request.user, "is_company_admin", False)),
            "available": autopay.cards_available(),
            "cards": [_card_body(c) for c in cards],
            "autopay": {
                "is_enabled": row.is_enabled and autopay.platform_enabled(),
                "card_id": row.card_id if row.card and row.card.usable else None,
                "amount_mode": row.amount_mode,
                "fixed_amount_uzs": row.fixed_amount_uzs,
                "monthly_limit_uzs": row.monthly_limit_uzs,
                "default_amount_uzs": q.month_cost_uzs,
                "effective_amount_uzs": q.amount_uzs,
                "effective_limit_uzs": q.limit_uzs,
                "spent_30d_uzs": q.spent_30d_uzs,
                "last_attempt_at": row.last_attempt_at.isoformat() if row.last_attempt_at else None,
                "last_status": row.last_status,
                "last_error": autopay.error_text(row.last_error, lang),
                "fail_streak": row.fail_streak,
                "disabled_reason": autopay.error_text(row.disabled_reason, lang),
                "consent_at": row.consent_at.isoformat() if row.consent_at else None,
            },
        }


class BillingAutopayView(_AutopayBase):
    @extend_schema(summary="Saved cards + auto-payment settings")
    def get(self, request: Request) -> Response:
        return Response(self.body(request))

    @extend_schema(summary="Change auto-payment (enabling requires consent + a card)")
    def put(self, request: Request) -> Response:
        from django.utils import timezone

        self.require_admin(request)
        row = autopay.get_settings(self.company)
        data = request.data

        if "amount_mode" in data:
            mode = str(data.get("amount_mode") or "")
            if mode not in AutoPaySettings.AmountMode.values:
                raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "amount_invalid"), 400)
            row.amount_mode = mode
        for field, key in (("fixed_amount_uzs", "amount_invalid"), ("monthly_limit_uzs", "limit_invalid")):
            if field in data:
                raw = data.get(field)
                if raw in (None, "", 0, "0"):
                    setattr(row, field, None)
                    continue
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, key), 400) from None
                if value < autopay.MIN_AMOUNT_UZS:
                    raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, key), 400)
                setattr(row, field, value)
        if row.amount_mode == AutoPaySettings.AmountMode.FIXED and not row.fixed_amount_uzs:
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "amount_invalid"), 400)
        if "card_id" in data and data.get("card_id"):
            row.card = self.card(request, int(data["card_id"]))

        enable = bool(data.get("is_enabled", row.is_enabled))
        if enable:
            if row.card is None or not row.card.usable:
                raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "card_required"), 400)
            # Turning it on (or back on) is a fresh, explicit authorisation.
            if not row.is_enabled:
                if not data.get("consent"):
                    raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "consent_required"), 400)
                row.consent_at = timezone.now()
                row.consent_by = cast(User, request.user)
                row.fail_streak = 0
                row.disabled_reason = ""
            q = autopay.quote(self.company, row)
            if row.monthly_limit_uzs and row.monthly_limit_uzs < q.amount_uzs and not q.due:
                raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "limit_invalid"), 400)
        changed_state = enable != row.is_enabled
        row.is_enabled = enable
        row.save()
        AuditLog.objects.create(
            company=self.company, actor=cast(User, request.user),
            action="billing.autopay_enabled" if enable else "billing.autopay_disabled"
            if changed_state else "billing.autopay_updated",
            target_model="billing.AutoPaySettings", target_id=str(row.pk),
            changes={
                "is_enabled": enable, "amount_mode": row.amount_mode,
                "fixed_amount_uzs": row.fixed_amount_uzs, "monthly_limit_uzs": row.monthly_limit_uzs,
                "card": row.card.label if row.card else None,
            },
        )
        return Response(self.body(request))


class BillingCardsView(_AutopayBase):
    @extend_schema(summary="Start linking a card (Paylov texts an SMS code)")
    def post(self, request: Request) -> Response:
        self.require_admin(request)
        number = "".join((request.data.get("card_number") or "").split())
        expire = (request.data.get("expire_date") or "").strip()
        if not (number.isdigit() and 12 <= len(number) <= 19):
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "card_invalid"), 400)
        if not (expire.isdigit() and len(expire) == 4):
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "expire_invalid"), 400)
        if SavedCard.objects.filter(is_confirmed=True, is_active=True).count() >= autopay.MAX_CARDS:
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "card_limit"), 400)
        try:
            card, phone = autopay.start_card_link(
                self.company, number, expire, cast(User, request.user)
            )
        except paylov_api.PaylovError as exc:
            raise _paylov_error(request, exc) from None
        return Response({"success": True, "card_ref": card.pk, "otp_phone": phone}, status=201)


class BillingCardConfirmView(_AutopayBase):
    @extend_schema(summary="Confirm the card link with the SMS code")
    def post(self, request: Request) -> Response:
        self.require_admin(request)
        otp = (request.data.get("otp") or "").strip()
        if not otp:
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "otp_required"), 400)
        try:
            ref = int(request.data.get("card_ref") or 0)
        except (TypeError, ValueError):
            ref = 0
        card = self.card(request, ref, confirmed=False)
        try:
            card = autopay.confirm_card_link(card, otp)
        except paylov_api.PaylovError as exc:
            raise _paylov_error(request, exc) from None
        AuditLog.objects.create(
            company=self.company, actor=cast(User, request.user), action="billing.card_linked",
            target_model="billing.SavedCard", target_id=str(card.pk), changes={"card": card.label},
        )
        return Response({"success": True, "card": _card_body(card)})


class BillingCardDetailView(_AutopayBase):
    @extend_schema(summary="Remove a saved card (stops auto-pay that uses it)")
    def delete(self, request: Request, card_id: int) -> Response:
        self.require_admin(request)
        autopay.remove_card(self.card(request, card_id), actor=cast(User, request.user))
        return Response({"success": True})


class BillingCardPayView(_AutopayBase):
    @extend_schema(summary="Top up now from a saved card (no SMS code)")
    def post(self, request: Request, card_id: int) -> Response:
        self.require_admin(request)
        card = self.card(request, card_id)
        try:
            amount = int(request.data.get("amount_uzs") or 0)
        except (TypeError, ValueError):
            amount = 0
        if amount < autopay.MIN_AMOUNT_UZS:
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "amount_invalid"), 400)
        try:
            payment = autopay.charge_saved_card(
                self.company, card, amount, is_auto=False, actor=cast(User, request.user)
            )
        except autopay.ChargePending:
            raise ApiError(ErrorCode.MISSING_FIELD, _msg(request, "pending"), 409) from None
        except autopay.ChargeFailed as exc:
            raise _paylov_error(request, paylov_api.PaylovError(exc.code)) from None
        self.company.refresh_from_db(fields=["balance_uzs"])
        return Response(
            {"success": True, "status": payment.status, "balance_uzs": self.company.balance_uzs}
        )
