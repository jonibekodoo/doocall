"""Saved cards + auto-payment: the money invariants.

Paylov is replaced by an in-memory fake; every test asserts on what reached
the balance, because the rule is absolute — nothing is credited unless
Paylov confirmed the charge, and an unknown outcome never becomes a second
charge.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing import autopay, paylov_api
from apps.billing.models import (
    AutoPaySettings,
    BillingNotification,
    Payment,
    PaymentProviderConfig,
    SavedCard,
    Subscription,
)
from apps.companies.models import Company
from apps.core.models import AuditLog

from .conftest import PRICE, make_operators

pytestmark = pytest.mark.django_db
BASE = "/api/web/v1/billing"


class FakePaylov:
    """Scriptable stand-in for the Subscribe API calls autopay makes."""

    def __init__(self) -> None:
        self.pay_calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []
        self.pay_error: str | None = None      # PaylovError code raised by pay_receipt
        self.pay_no_result = False              # 2xx without "result"
        self.paid_register: dict[str, int] = {}  # txn → amount listed by getTransactions
        self.deleted: list[str] = []
        self._n = 0

    def create_receipt(self, user_id: str, amount_uzs: int, account: dict, *, payment=None) -> dict:
        self._n += 1
        self.create_calls.append({"user_id": user_id, "amount": amount_uzs, "account": account})
        return {"result": {"transactionId": f"txn-{self._n}"}}

    def pay_receipt(self, transaction_id: str, card_id: str, user_id: str, *, payment=None) -> dict:
        self.pay_calls.append({"txn": transaction_id, "card": card_id, "user": user_id})
        if self.pay_error:
            raise paylov_api.PaylovError(self.pay_error)
        if self.pay_no_result:
            return {"result": None}
        return {"result": {"transactionId": transaction_id}}

    def get_transaction(self, transaction_id: str, *, payment=None) -> dict:
        rows = (
            [{"id": transaction_id, "amount": self.paid_register[transaction_id]}]
            if transaction_id in self.paid_register
            else []
        )
        return {"result": {"totalTransaction": len(rows), "transactions": rows}, "error": None}

    def create_user_card(self, user_id: str, card_number: str, expire_date: str) -> dict:
        return {"result": {"cid": "cid-1", "otpSentPhone": "+99890***4567"}}

    def confirm_user_card(self, cid: str, otp: str) -> dict:
        if otp != "111111":
            raise paylov_api.PaylovError("invalid_otp")
        return {
            "result": {
                "card": {
                    "cardId": "card-uuid-1", "owner": "TEST OWNER", "number": "860000******9999",
                    "expireDate": "2912", "vendor": "Uzcard", "status": {"is_active": True},
                }
            }
        }

    def delete_user_card(self, card_id: str) -> dict:
        self.deleted.append(card_id)
        return {"result": True}


@pytest.fixture
def paylov(monkeypatch: pytest.MonkeyPatch, settings: Any) -> FakePaylov:
    settings.PAYLOV_CONSUMER_KEY = "key"
    settings.PAYLOV_API_USERNAME = "user"
    PaymentProviderConfig.objects.update_or_create(
        provider="paylov", defaults={"is_enabled": True, "autopay_enabled": True}
    )
    fake = FakePaylov()
    for name in (
        "create_receipt", "pay_receipt", "get_transaction",
        "create_user_card", "confirm_user_card", "delete_user_card",
    ):
        monkeypatch.setattr(paylov_api, name, getattr(fake, name))
    return fake


@pytest.fixture
def card(company: Company) -> SavedCard:
    return SavedCard.all_objects.create(
        company=company, paylov_card_id="card-uuid-1", paylov_user_id=autopay.paylov_user_id(company),
        masked_number="860000******9999", vendor="Uzcard", expire="2912",
        is_confirmed=True, confirmed_at=timezone.now(),
    )


@pytest.fixture
def auto(company: Company, subscription: Subscription, card: SavedCard) -> AutoPaySettings:
    """Two operators, auto-pay ON, balance at zero → a charge is due."""
    make_operators(company, 2)
    return AutoPaySettings.all_objects.create(
        company=company, is_enabled=True, card=card, consent_at=timezone.now()
    )


def balance(company: Company) -> int:
    company.refresh_from_db()
    return company.balance_uzs


# The nightly run of *today* (real date): rows get a real ``created_at``, so
# the simulated clock must not drift away from it.
NOW: datetime = timezone.localtime().replace(hour=0, minute=35, second=0, microsecond=0)
MONTH = 2 * PRICE  # two operators


class TestCharge:
    def test_confirmed_charge_credits_one_month(self, company, auto, paylov) -> None:
        assert autopay.run_autopay(NOW)["charged"] == 1
        assert balance(company) == MONTH
        payment = Payment.all_objects.get(company=company)
        assert payment.status == Payment.Status.APPROVED and payment.is_auto
        assert payment.saved_card_id == auto.card_id and payment.external_id == "txn-1"
        assert paylov.create_calls[0]["amount"] == MONTH  # SOM, not tiyin
        auto.refresh_from_db()
        assert (auto.last_status, auto.fail_streak) == ("ok", 0)

    def test_not_due_while_balance_covers_a_day(self, company, auto, paylov) -> None:
        company.balance_uzs = MONTH
        company.save(update_fields=["balance_uzs"])
        assert autopay.run_autopay(NOW) == {"reconciled": 0, "not_due": 1}
        assert paylov.pay_calls == [] and balance(company) == MONTH

    def test_fixed_amount_mode(self, company, auto, paylov) -> None:
        auto.amount_mode = AutoPaySettings.AmountMode.FIXED
        auto.fixed_amount_uzs = 30000
        auto.save()
        autopay.run_autopay(NOW)
        assert balance(company) == 30000

    def test_second_run_same_day_never_charges_twice(self, company, auto, paylov) -> None:
        autopay.run_autopay(NOW)
        # Force "due" again the same day: the idempotency key must stop it.
        company.balance_uzs = 0
        company.save(update_fields=["balance_uzs"])
        assert autopay.run_autopay(NOW + timedelta(hours=1)).get("already") == 1
        assert len(paylov.pay_calls) == 1
        with pytest.raises(autopay.AlreadyAttempted):
            autopay.charge_saved_card(
                company, auto.card, 5000, is_auto=True,
                idempotency_key=f"auto:{company.pk}:{NOW.date().isoformat()}",
            )


class TestDeclines:
    def test_decline_credits_nothing_and_retries_three_days(self, company, auto, paylov) -> None:
        paylov.pay_error = "insufficient_funds"
        for day in range(2):
            assert autopay.run_autopay(NOW + timedelta(days=day))["failed"] == 1
        auto.refresh_from_db()
        assert auto.is_enabled and auto.fail_streak == 2 and balance(company) == 0
        # Third consecutive failure switches auto-pay off and tells the client.
        assert autopay.run_autopay(NOW + timedelta(days=2))["disabled"] == 1
        auto.refresh_from_db()
        assert not auto.is_enabled and auto.disabled_reason == "too_many_failures"
        assert balance(company) == 0
        assert Payment.all_objects.filter(company=company, status=Payment.Status.FAILED).count() == 3
        assert BillingNotification.all_objects.filter(
            company=company, kind=BillingNotification.Kind.AUTOPAY_FAILED
        ).count() == 3
        # Off means off.
        assert autopay.run_autopay(NOW + timedelta(days=3)) == {"reconciled": 0}

    def test_success_resets_the_streak(self, company, auto, paylov) -> None:
        paylov.pay_error = "insufficient_funds"
        autopay.run_autopay(NOW)
        paylov.pay_error = None
        autopay.run_autopay(NOW + timedelta(days=1))
        auto.refresh_from_db()
        assert auto.fail_streak == 0 and balance(company) == MONTH

    def test_dead_card_disables_immediately(self, company, auto, paylov) -> None:
        paylov.pay_error = "card_expired"
        assert autopay.run_autopay(NOW)["disabled"] == 1
        auto.refresh_from_db()
        auto.card.refresh_from_db()
        assert not auto.is_enabled and auto.disabled_reason == "card_expired"
        assert not auto.card.is_active and balance(company) == 0


class TestUnknownOutcome:
    @pytest.mark.parametrize("mode", ["timeout", "no_result"])
    def test_unknown_outcome_is_never_credited_nor_retried(self, company, auto, paylov, mode) -> None:
        if mode == "timeout":
            paylov.pay_error = "connection_failed"
        else:
            paylov.pay_no_result = True
        assert autopay.run_autopay(NOW)["pending"] == 1
        assert balance(company) == 0
        payment = Payment.all_objects.get(company=company)
        assert payment.status == Payment.Status.PENDING

        # Next night: still unknown → hold, do NOT touch the card again.
        paylov.pay_error, paylov.pay_no_result = None, False
        assert autopay.run_autopay(NOW + timedelta(hours=20))["held"] == 1
        assert len(paylov.pay_calls) == 1 and balance(company) == 0

    def test_reconcile_credits_when_paylov_lists_it_paid(self, company, auto, paylov) -> None:
        paylov.pay_error = "connection_failed"
        autopay.run_autopay(NOW)
        paylov.paid_register["txn-1"] = MONTH
        assert autopay.reconcile_pending(NOW + timedelta(minutes=5)) == 1
        assert balance(company) == MONTH
        assert Payment.all_objects.get(company=company).status == Payment.Status.APPROVED
        # Idempotent: reconciling again credits nothing more.
        autopay.reconcile_pending(NOW + timedelta(minutes=10))
        assert balance(company) == MONTH

    def test_reconcile_wrong_amount_is_not_a_confirmation(self, company, auto, paylov) -> None:
        paylov.pay_error = "connection_failed"
        autopay.run_autopay(NOW)
        paylov.paid_register["txn-1"] = 1  # same id, different amount
        autopay.reconcile_pending(NOW + timedelta(minutes=5))
        assert balance(company) == 0

    def test_reconcile_gives_up_after_a_day_without_crediting(self, company, auto, paylov) -> None:
        paylov.pay_error = "connection_failed"
        autopay.run_autopay(NOW)
        payment = Payment.all_objects.get(company=company)
        assert autopay.reconcile_pending(payment.created_at + timedelta(hours=25)) == 1
        payment.refresh_from_db()
        assert payment.status == Payment.Status.FAILED and balance(company) == 0


class TestGuards:
    def test_monthly_limit_blocks_the_charge(self, company, auto, paylov) -> None:
        auto.monthly_limit_uzs = MONTH - 1
        auto.save()
        assert autopay.run_autopay(NOW)["limit"] == 1
        assert paylov.pay_calls == [] and balance(company) == 0
        auto.refresh_from_db()
        assert auto.is_enabled and auto.last_error == "limit_reached"

    def test_limit_counts_the_last_30_days(self, company, auto, paylov) -> None:
        autopay.run_autopay(NOW)                                   # 1 × month
        for day in (5, 10):                                        # default cap = 2 × month
            company.balance_uzs = 0
            company.save(update_fields=["balance_uzs"])
            autopay.run_autopay(NOW + timedelta(days=day))
        assert len(paylov.pay_calls) == 2
        assert Payment.all_objects.filter(company=company, status=Payment.Status.APPROVED).count() == 2

    def test_platform_switch_stops_everything(self, company, auto, paylov) -> None:
        PaymentProviderConfig.objects.filter(provider="paylov").update(autopay_enabled=False)
        assert autopay.run_autopay(NOW) == {"reconciled": 0}
        assert paylov.pay_calls == [] and balance(company) == 0

    def test_trial_company_is_not_charged(self, company, auto, paylov) -> None:
        company.status = Company.Status.TRIAL
        company.save(update_fields=["status"])
        assert autopay.run_autopay(NOW)["trial"] == 1 and paylov.pay_calls == []

    def test_staff_suspended_company_is_not_charged(self, company, auto, paylov) -> None:
        staff = User.objects.create_user(username="staff@doocall.uz", is_staff=True)
        company.status = Company.Status.SUSPENDED
        company.save(update_fields=["status"])
        AuditLog.objects.create(company=company, actor=staff, action="subscription.suspended")
        assert autopay.run_autopay(NOW)["staff_suspended"] == 1 and paylov.pay_calls == []

    def test_balance_suspended_company_is_charged_and_reactivated(
        self, company, subscription, auto, paylov
    ) -> None:
        company.status = Company.Status.SUSPENDED
        company.balance_uzs = -4000
        company.save(update_fields=["status", "balance_uzs"])
        subscription.status = Subscription.Status.SUSPENDED
        subscription.save(update_fields=["status"])
        AuditLog.objects.create(company=company, action="subscription.suspended")  # system, no actor
        assert autopay.run_autopay(NOW)["charged"] == 1
        company.refresh_from_db()
        assert company.balance_uzs == MONTH - 4000 and company.status == Company.Status.ACTIVE

    def test_someone_elses_card_is_refused(self, company, auto, paylov, pricing) -> None:
        other = Company.objects.create(name="Other", slug="other", status=Company.Status.ACTIVE)
        with pytest.raises(autopay.ChargeFailed):
            autopay.charge_saved_card(other, auto.card, 5000, is_auto=False)
        assert paylov.create_calls == []


class TestCabinetApi:
    @pytest.fixture
    def admin(self, company: Company) -> APIClient:
        user = User.objects.create_user(username="admin@billing-co.uz", company=company, is_company_admin=True)
        api = APIClient()
        api.force_authenticate(user=user)
        return api

    @pytest.fixture
    def member(self, company: Company) -> APIClient:
        user = User.objects.create_user(username="member@billing-co.uz", company=company)
        api = APIClient()
        api.force_authenticate(user=user)
        return api

    def test_link_card_flow(self, company, subscription, admin, paylov) -> None:
        started = admin.post(f"{BASE}/cards", {"card_number": "8600 0000 0000 9999", "expire_date": "2912"}, format="json")
        assert started.status_code == 201 and started.json()["otp_phone"]
        ref = started.json()["card_ref"]
        # The unconfirmed card is not usable and not listed.
        assert admin.get(f"{BASE}/autopay").json()["cards"] == []
        assert admin.post(f"{BASE}/cards/confirm", {"card_ref": ref, "otp": "000000"}, format="json").status_code == 400
        done = admin.post(f"{BASE}/cards/confirm", {"card_ref": ref, "otp": "111111"}, format="json")
        assert done.status_code == 200 and done.json()["card"]["masked_number"] == "860000******9999"
        stored = SavedCard.all_objects.get(pk=ref)
        assert stored.usable and stored.paylov_card_id == "card-uuid-1"
        assert "8600000000009999" not in str(SavedCard.all_objects.values())  # never the PAN

    def test_member_can_look_but_not_touch(self, company, auto, member, paylov) -> None:
        assert member.get(f"{BASE}/autopay").json()["can_manage"] is False
        assert member.post(f"{BASE}/cards", {"card_number": "8600000000009999", "expire_date": "2912"}, format="json").status_code == 403
        assert member.put(f"{BASE}/autopay", {"is_enabled": False}, format="json").status_code == 403
        assert member.post(f"{BASE}/cards/{auto.card_id}/pay", {"amount_uzs": 5000}, format="json").status_code == 403
        assert member.delete(f"{BASE}/cards/{auto.card_id}").status_code == 403
        assert paylov.pay_calls == []

    def test_enabling_needs_consent_and_a_card(self, company, subscription, card, admin, paylov) -> None:
        make_operators(company, 2)
        no_consent = admin.put(f"{BASE}/autopay", {"is_enabled": True, "card_id": card.pk}, format="json")
        assert no_consent.status_code == 400
        ok = admin.put(f"{BASE}/autopay", {"is_enabled": True, "card_id": card.pk, "consent": True}, format="json")
        assert ok.status_code == 200 and ok.json()["autopay"]["is_enabled"] is True
        row = AutoPaySettings.all_objects.get(company=company)
        assert row.consent_at is not None and row.consent_by is not None
        assert ok.json()["autopay"]["default_amount_uzs"] == MONTH
        assert ok.json()["autopay"]["effective_limit_uzs"] == 2 * MONTH

    def test_pay_now_and_remove_card(self, company, auto, admin, paylov) -> None:
        paid = admin.post(f"{BASE}/cards/{auto.card_id}/pay", {"amount_uzs": 25000}, format="json")
        assert paid.status_code == 200 and paid.json()["balance_uzs"] == 25000
        manual = Payment.all_objects.get(company=company)
        assert manual.is_auto is False and manual.status == Payment.Status.APPROVED

        paylov.pay_error = "insufficient_funds"
        declined = admin.post(f"{BASE}/cards/{auto.card_id}/pay", {"amount_uzs": 25000}, format="json")
        assert declined.status_code == 400 and balance(company) == 25000

        assert admin.delete(f"{BASE}/cards/{auto.card_id}").status_code == 200
        auto.refresh_from_db()
        assert not auto.is_enabled and auto.disabled_reason == "card_removed"
        assert paylov.deleted == ["card-uuid-1"]
        assert admin.get(f"{BASE}/autopay").json()["cards"] == []
