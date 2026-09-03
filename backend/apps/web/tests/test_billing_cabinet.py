"""Cabinet daily-billing surface + suspension lock + same-day operator billing."""

from __future__ import annotations

from datetime import date

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.billing.models import BillingNotification, DailyCharge, MonthlyStatement
from apps.companies.models import Company

pytestmark = pytest.mark.django_db

BASE = "/api/web/v1"


class TestBillingEndpoints:
    def test_overview_and_charges_breakdown(
        self, client: APIClient, company: Company, op_a: OperatorProfile
    ) -> None:
        today = timezone.now().date()
        DailyCharge.all_objects.create(
            company=company,
            date=today,
            operator=op_a,
            operator_name=op_a.user_name,
            amount_uzs=1667,
            price_per_operator_uzs=50000,
        )
        overview = client.get(f"{BASE}/billing/overview").json()
        assert overview["balance_uzs"] == 0
        assert overview["month_accrued_uzs"] == 1667
        assert overview["seats"] == 1

        charges = client.get(
            f"{BASE}/billing/charges?month={today.strftime('%Y-%m')}"
        ).json()
        assert charges["total_uzs"] == 1667
        assert charges["charges"][0]["operator_name"] == op_a.user_name
        assert charges["days"][0]["total_uzs"] == 1667

        assert client.get(f"{BASE}/billing/charges?month=oops").status_code == 400

    def test_statements_history(self, client: APIClient, company: Company) -> None:
        MonthlyStatement.all_objects.create(
            company=company, month=date(2026, 8, 1), total_uzs=250000
        )
        body = client.get(f"{BASE}/billing/statements").json()
        assert body["statements"][0]["month"] == "2026-08"
        assert body["statements"][0]["total_uzs"] == 250000

    def test_notifications_flow(self, client: APIClient, company: Company) -> None:
        first = BillingNotification.all_objects.create(
            company=company,
            kind=BillingNotification.Kind.PAYMENT_DUE,
            message="To'lov qilish kerak",
            amount_uzs=300000,
        )
        BillingNotification.all_objects.create(
            company=company,
            kind=BillingNotification.Kind.TARIFF_CHANGED,
            message="Tarif o'zgardi",
        )
        listing = client.get(f"{BASE}/notifications").json()
        assert listing["unread"] == 2

        # Click-to-open: one notification at a time.
        assert client.post(f"{BASE}/notifications/{first.pk}/read").json()["success"]
        assert client.get(f"{BASE}/notifications").json()["unread"] == 1
        assert client.post(f"{BASE}/notifications/999999/read").status_code == 404

        assert client.post(f"{BASE}/notifications/read").json()["marked"] == 1
        assert client.get(f"{BASE}/notifications").json()["unread"] == 0


class TestManualPayRequest:
    def test_submit_creates_pending_payment_for_admin(
        self, client: APIClient, company: Company
    ) -> None:
        from apps.billing.models import Payment

        response = client.post(
            f"{BASE}/billing/pay",
            {"provider": "manual", "amount_uzs": 250000},
            format="json",
        )
        assert response.status_code == 201
        payment = Payment.all_objects.get(company=company)
        assert payment.provider == Payment.Provider.MANUAL
        assert payment.status == Payment.Status.PENDING
        assert payment.amount_uzs == 250000
        assert BillingNotification.all_objects.filter(
            company=company, kind=BillingNotification.Kind.PAYMENT_REQUESTED
        ).exists()

        # A second open request is rejected until the first is processed.
        assert (
            client.post(
                f"{BASE}/billing/pay",
                {"provider": "manual", "amount_uzs": 100000},
                format="json",
            ).status_code
            == 400
        )

    def test_invalid_amounts_rejected(self, client: APIClient, company: Company) -> None:
        for bad in (0, -5, "abc", 500):
            assert (
                client.post(
                    f"{BASE}/billing/pay",
                    {"provider": "manual", "amount_uzs": bad},
                    format="json",
                ).status_code
                == 400
            )

    def test_works_while_suspended(self, client: APIClient, company: Company) -> None:
        company.status = Company.Status.SUSPENDED
        company.save(update_fields=["status"])
        assert (
            client.post(
                f"{BASE}/billing/pay",
                {"provider": "manual", "amount_uzs": 100000},
                format="json",
            ).status_code
            == 201
        )


class TestSuspensionLock:
    def test_suspended_company_keeps_only_billing_surface(
        self, client: APIClient, company: Company
    ) -> None:
        company.status = Company.Status.SUSPENDED
        company.save(update_fields=["status"])
        assert client.get(f"{BASE}/dashboard").status_code == 402
        assert client.get(f"{BASE}/calls").status_code == 402
        assert client.get(f"{BASE}/settings/license").status_code == 200
        assert client.get(f"{BASE}/billing/overview").status_code == 200
        assert client.get(f"{BASE}/notifications").status_code == 200


class TestOperatorLifecycleBilling:
    def test_delete_same_day_still_bills_one_day(
        self, client: APIClient, company: Company, op_a: OperatorProfile
    ) -> None:
        assert client.delete(f"{BASE}/settings/users/{op_a.pk}").json()["success"]
        charge = DailyCharge.all_objects.get(company=company)
        assert charge.operator_name == op_a.user_name
        assert charge.date == timezone.now().date()
        assert charge.amount_uzs > 0
        assert not OperatorProfile.all_objects.filter(pk=op_a.pk).exists()

    def test_deactivate_bills_the_worked_day(
        self, client: APIClient, company: Company, op_a: OperatorProfile
    ) -> None:
        response = client.patch(
            f"{BASE}/settings/users/{op_a.pk}", {"is_active": False}, format="json"
        )
        assert response.status_code == 200
        assert DailyCharge.all_objects.filter(
            company=company, operator_name=op_a.user_name, date=timezone.now().date()
        ).exists()
