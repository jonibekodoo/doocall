"""Payme / Click webhook tests — signature validation (valid + tampered)."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.billing.models import Invoice, Payment, Subscription
from apps.companies.models import Company

from .conftest import PRICE, make_operators

pytestmark = pytest.mark.django_db

PAYME_URL = "/api/web/v1/billing/webhooks/payme"
CLICK_URL = "/api/web/v1/billing/webhooks/click"

PAYME_SECRET = "payme-test-secret"
CLICK_SECRET = "click-test-secret"


@pytest.fixture(autouse=True)
def _provider_credentials(settings: Any) -> None:
    settings.PAYME_SECRET_KEY = PAYME_SECRET
    settings.CLICK_SECRET_KEY = CLICK_SECRET


@pytest.fixture
def invoice(company: Company, subscription: Subscription) -> Invoice:
    make_operators(company, 1)
    return Invoice.all_objects.create(
        company=company,
        subscription=subscription,
        total_uzs=PRICE,
        status=Invoice.Status.PENDING,
    )


def payme_auth(secret: str = PAYME_SECRET) -> str:
    return "Basic " + base64.b64encode(f"Paycom:{secret}".encode()).decode()


class TestPaymeWebhook:
    def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    def test_valid_flow_check_create_perform(self, invoice: Invoice) -> None:
        client = APIClient()
        auth = payme_auth()
        account = {"account": {"invoice_number": invoice.number}}

        check = client.post(
            PAYME_URL,
            self.rpc("CheckPerformTransaction", {**account, "amount": PRICE * 100}),
            format="json",
            HTTP_AUTHORIZATION=auth,
        )
        assert check.status_code == 200
        assert check.json()["result"] == {"allow": True}

        create = client.post(
            PAYME_URL,
            self.rpc(
                "CreateTransaction",
                {**account, "amount": PRICE * 100, "id": "payme-txn-1", "time": 1755150000000},
            ),
            format="json",
            HTTP_AUTHORIZATION=auth,
        )
        assert create.json()["result"]["state"] == 1

        perform = client.post(
            PAYME_URL,
            self.rpc("PerformTransaction", {"id": "payme-txn-1"}),
            format="json",
            HTTP_AUTHORIZATION=auth,
        )
        assert perform.json()["result"]["state"] == 2

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PAID
        payment = Payment.all_objects.get(provider="payme", external_id="payme-txn-1")
        assert payment.status == Payment.Status.APPROVED
        invoice.company.refresh_from_db()
        assert invoice.company.status == Company.Status.ACTIVE

    def test_tampered_credentials_rejected(self, invoice: Invoice) -> None:
        response = APIClient().post(
            PAYME_URL,
            self.rpc("CheckPerformTransaction", {"amount": PRICE * 100}),
            format="json",
            HTTP_AUTHORIZATION=payme_auth("wrong-secret"),
        )
        # Payme convention: HTTP 200 + JSON-RPC auth error, nothing processed.
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32504
        assert not Payment.all_objects.exists()

    def test_missing_auth_rejected(self, invoice: Invoice) -> None:
        response = APIClient().post(
            PAYME_URL, self.rpc("CheckPerformTransaction", {}), format="json"
        )
        assert response.json()["error"]["code"] == -32504

    def test_wrong_amount_rejected(self, invoice: Invoice) -> None:
        response = APIClient().post(
            PAYME_URL,
            self.rpc(
                "CheckPerformTransaction",
                {"account": {"invoice_number": invoice.number}, "amount": 1},
            ),
            format="json",
            HTTP_AUTHORIZATION=payme_auth(),
        )
        assert response.json()["error"]["code"] == -31001


def click_sign(p: dict[str, str], *, secret: str = CLICK_SECRET) -> str:
    parts = [p["click_trans_id"], p["service_id"], secret, p["merchant_trans_id"]]
    if p["action"] == "1":
        parts.append(p["merchant_prepare_id"])
    parts += [p["amount"], p["action"], p["sign_time"]]
    return hashlib.md5("".join(parts).encode()).hexdigest()  # noqa: S324


class TestClickWebhook:
    def base_params(self, invoice: Invoice, action: str) -> dict[str, str]:
        return {
            "click_trans_id": "click-txn-7",
            "service_id": "12345",
            "merchant_trans_id": invoice.number,
            "amount": str(invoice.total_uzs),
            "action": action,
            "error": "0",
            "sign_time": "2026-08-14 12:00:00",
        }

    def test_valid_prepare_and_complete(self, invoice: Invoice) -> None:
        client = APIClient()

        prepare = self.base_params(invoice, "0")
        prepare["sign_string"] = click_sign(prepare)
        r1 = client.post(CLICK_URL, prepare, format="json")
        assert r1.status_code == 200
        assert r1.json()["error"] == 0
        prepare_id = str(r1.json()["merchant_prepare_id"])

        complete = self.base_params(invoice, "1")
        complete["merchant_prepare_id"] = prepare_id
        complete["sign_string"] = click_sign(complete)
        r2 = client.post(CLICK_URL, complete, format="json")
        assert r2.json()["error"] == 0

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PAID
        assert (
            Payment.all_objects.get(provider="click", external_id="click-txn-7").status
            == Payment.Status.APPROVED
        )

    def test_tampered_signature_rejected(self, invoice: Invoice) -> None:
        params = self.base_params(invoice, "0")
        params["sign_string"] = click_sign(params)
        params["amount"] = str(invoice.total_uzs * 10)  # tamper AFTER signing

        response = APIClient().post(CLICK_URL, params, format="json")

        assert response.json()["error"] == -1
        assert "SIGN" in response.json()["error_note"]
        assert not Payment.all_objects.exists()

    def test_wrong_secret_rejected(self, invoice: Invoice) -> None:
        params = self.base_params(invoice, "0")
        params["sign_string"] = click_sign(params, secret="attacker-secret")
        response = APIClient().post(CLICK_URL, params, format="json")
        assert response.json()["error"] == -1


class TestUnknownProvider:
    def test_unknown_provider_404(self, db: Any) -> None:
        response = APIClient().post("/api/web/v1/billing/webhooks/stripe", {}, format="json")
        assert response.status_code == 404

    def test_manual_has_no_webhook(self, db: Any) -> None:
        response = APIClient().post("/api/web/v1/billing/webhooks/manual", {}, format="json")
        assert response.status_code == 404


class TestPaymeCancelAndCheck:
    def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": 9, "method": method, "params": params}

    def _create_txn(self, invoice: Invoice) -> None:
        APIClient().post(
            PAYME_URL,
            self.rpc(
                "CreateTransaction",
                {
                    "account": {"invoice_number": invoice.number},
                    "amount": PRICE * 100,
                    "id": "payme-txn-9",
                    "time": 1755150000000,
                },
            ),
            format="json",
            HTTP_AUTHORIZATION=payme_auth(),
        )

    def test_cancel_rejects_pending(self, invoice: Invoice) -> None:
        self._create_txn(invoice)
        response = APIClient().post(
            PAYME_URL,
            self.rpc("CancelTransaction", {"id": "payme-txn-9"}),
            format="json",
            HTTP_AUTHORIZATION=payme_auth(),
        )
        assert response.json()["result"]["state"] == -1
        payment = Payment.all_objects.get(external_id="payme-txn-9")
        assert payment.status == Payment.Status.REJECTED

    def test_check_reports_state(self, invoice: Invoice) -> None:
        self._create_txn(invoice)
        response = APIClient().post(
            PAYME_URL,
            self.rpc("CheckTransaction", {"id": "payme-txn-9"}),
            format="json",
            HTTP_AUTHORIZATION=payme_auth(),
        )
        assert response.json()["result"]["state"] == 1  # created/pending

    def test_unknown_method_error(self, invoice: Invoice) -> None:
        response = APIClient().post(
            PAYME_URL,
            self.rpc("ExplodeTransaction", {}),
            format="json",
            HTTP_AUTHORIZATION=payme_auth(),
        )
        assert response.json()["error"]["code"] == -32601

    def test_unknown_transaction_not_found(self, invoice: Invoice) -> None:
        response = APIClient().post(
            PAYME_URL,
            self.rpc("PerformTransaction", {"id": "ghost"}),
            format="json",
            HTTP_AUTHORIZATION=payme_auth(),
        )
        assert response.json()["error"]["code"] == -31003
