"""apply_payment credits ONLY a payment that is PENDING under the row lock.

A payment rejected/failed after a caller loaded it as pending (gateway cancel,
admin rejection racing an approval) must never reach the balance — through
the service directly, the Payme/Click webhooks or the admin approve endpoint —
and none of those callers may crash on it."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing import services
from apps.billing.models import Invoice, Payment, Subscription
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.partners import services as partner_services
from apps.partners.models import ROLE_PLATFORM_ADMIN

from .conftest import PRICE
from .test_webhooks import CLICK_URL, PAYME_URL, click_sign, payme_auth

pytestmark = pytest.mark.django_db

REFUSED = [Payment.Status.REJECTED, Payment.Status.FAILED]


@pytest.fixture
def invoice(company: Company, subscription: Subscription) -> Invoice:
    return Invoice.all_objects.create(
        company=company,
        subscription=subscription,
        total_uzs=PRICE,
        status=Invoice.Status.PENDING,
    )


def _balance(company: Company) -> int:
    company.refresh_from_db(fields=["balance_uzs"])
    return company.balance_uzs


class TestService:
    @pytest.mark.parametrize("final_status", REFUSED)
    def test_rejected_after_load_is_not_credited(
        self, company: Company, invoice: Invoice, final_status: str
    ) -> None:
        payment = Payment.all_objects.create(
            company=company,
            invoice=invoice,
            provider=Payment.Provider.MANUAL,
            amount_uzs=PRICE,
        )
        stale = Payment.all_objects.get(pk=payment.pk)  # caller saw PENDING
        Payment.all_objects.filter(pk=payment.pk).update(status=final_status)

        returned = services.apply_payment(stale)

        assert returned is stale
        assert stale.status == final_status  # caller's copy refreshed
        assert stale.approved_at is None
        assert _balance(company) == 0
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PENDING
        assert not AuditLog.objects.filter(company=company, action="payment.applied").exists()

    def test_refused_payment_does_not_end_a_trial(self, company: Company) -> None:
        company.status = Company.Status.TRIAL
        company.save(update_fields=["status"])
        subscription = Subscription.all_objects.create(
            company=company, status=Subscription.Status.TRIAL, price_per_operator_uzs=PRICE
        )
        payment = Payment.all_objects.create(
            company=company,
            provider=Payment.Provider.MANUAL,
            amount_uzs=PRICE,
            status=Payment.Status.REJECTED,
        )
        services.apply_payment(payment)
        subscription.refresh_from_db()
        company.refresh_from_db()
        assert subscription.status == Subscription.Status.TRIAL
        assert company.status == Company.Status.TRIAL
        assert company.balance_uzs == 0

    def test_pending_payment_is_still_credited(self, company: Company) -> None:
        payment = Payment.all_objects.create(
            company=company, provider=Payment.Provider.MANUAL, amount_uzs=PRICE
        )
        services.apply_payment(payment)
        assert payment.status == Payment.Status.APPROVED
        assert _balance(company) == PRICE


@pytest.fixture(autouse=True)
def _provider_credentials(settings: Any) -> None:
    from .test_webhooks import CLICK_SECRET, PAYME_SECRET

    settings.PAYME_SECRET_KEY = PAYME_SECRET
    settings.CLICK_SECRET_KEY = CLICK_SECRET


class TestWebhooks:
    def _payme(self, method: str, params: dict[str, Any]) -> Any:
        return APIClient().post(
            PAYME_URL,
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            format="json",
            HTTP_AUTHORIZATION=payme_auth(),
        )

    def test_payme_perform_after_cancel_is_not_credited(
        self, company: Company, invoice: Invoice
    ) -> None:
        self._payme(
            "CreateTransaction",
            {
                "account": {"invoice_number": invoice.number},
                "amount": PRICE * 100,
                "id": "payme-guard-1",
                "time": 1755150000000,
            },
        )
        self._payme("CancelTransaction", {"id": "payme-guard-1"})

        response = self._payme("PerformTransaction", {"id": "payme-guard-1"})

        assert response.status_code == 200  # webhook answered, no crash
        payment = Payment.all_objects.get(external_id="payme-guard-1")
        assert payment.status == Payment.Status.REJECTED
        assert _balance(company) == 0
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PENDING

    def test_click_complete_after_failure_is_not_credited(
        self, company: Company, invoice: Invoice
    ) -> None:
        def params(action: str, error: str = "0") -> dict[str, str]:
            return {
                "click_trans_id": "click-guard-1",
                "service_id": "12345",
                "merchant_trans_id": invoice.number,
                "amount": str(invoice.total_uzs),
                "action": action,
                "error": error,
                "sign_time": "2026-08-14 12:00:00",
            }

        client = APIClient()
        prepare = params("0")
        prepare["sign_string"] = click_sign(prepare)
        prepare_id = str(
            client.post(CLICK_URL, prepare, format="json").json()["merchant_prepare_id"]
        )

        failed = params("1", error="-5017")
        failed["merchant_prepare_id"] = prepare_id
        failed["sign_string"] = click_sign(failed)
        client.post(CLICK_URL, failed, format="json")
        payment = Payment.all_objects.get(external_id="click-guard-1")
        assert payment.status == Payment.Status.FAILED

        late_ok = params("1")
        late_ok["merchant_prepare_id"] = prepare_id
        late_ok["sign_string"] = click_sign(late_ok)
        response = client.post(CLICK_URL, late_ok, format="json")

        assert response.status_code == 200  # webhook answered, no crash
        payment.refresh_from_db()
        assert payment.status == Payment.Status.FAILED
        assert _balance(company) == 0


class TestAdminApprove:
    def test_rejected_manual_payment_is_not_credited(self, company: Company) -> None:
        admin = User.objects.create_user(
            username="staff@platform.uz",
            email="staff@platform.uz",
            role=partner_services.get_platform_role(ROLE_PLATFORM_ADMIN),
        )
        payment = Payment.all_objects.create(
            company=company,
            provider=Payment.Provider.MANUAL,
            amount_uzs=PRICE,
            status=Payment.Status.REJECTED,
        )
        api = APIClient()
        api.force_authenticate(user=admin)

        response = api.post(f"/api/admin/v1/payments/{payment.pk}/approve")

        assert response.status_code < 500
        assert response.json()["payment_status"] == Payment.Status.REJECTED
        assert response.json()["cashback_accrued_uzs"] == 0
        payment.refresh_from_db()
        assert payment.status == Payment.Status.REJECTED
        assert _balance(company) == 0
