"""Admin: set / change / clear a company's integrator, its history, and the
company's cashback list. Accruals follow company.integrator at approval time."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing.models import Payment
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.partners import services
from apps.partners.models import (
    ROLE_SALES_MANAGER,
    CashbackAccrual,
    Integrator,
    PlatformNotification,
    SalesCommission,
    SalesManager,
)

from .conftest import client_for

pytestmark = pytest.mark.django_db


def reassign_url(company: Company) -> str:
    return f"/api/admin/v1/companies/{company.pk}/reassign"


def history_url(company: Company) -> str:
    return f"/api/admin/v1/companies/{company.pk}/integrator-history"


def attach_sales_manager(integrator: Integrator, tag: str, percent: str = "5.00") -> SalesManager:
    user = User.objects.create_user(
        username=f"{tag}@sales",
        email=f"{tag}@sales.uz",
        role=services.get_platform_role(ROLE_SALES_MANAGER),
    )
    manager = SalesManager.objects.create(
        user=user, name=f"Sales {tag}", commission_percent=Decimal(percent)
    )
    integrator.sales_manager = manager
    integrator.save(update_fields=["sales_manager"])
    return manager


def approve_payment(admin: APIClient, company: Company, amount: int = 100000) -> Payment:
    """A pending bank/cash payment approved through the admin endpoint."""
    payment = Payment.all_objects.create(
        company=company, provider=Payment.Provider.MANUAL, amount_uzs=amount
    )
    assert admin.post(f"/api/admin/v1/payments/{payment.pk}/approve").status_code == 200
    return payment


class TestReassignAccruals:
    def test_next_payment_credits_new_integrator_old_accrual_untouched(
        self,
        superadmin: User,
        bound_company: Company,
        integrator: Integrator,
        integrator_override: Integrator,
    ) -> None:
        old_manager = attach_sales_manager(integrator, "old")
        new_manager = attach_sales_manager(integrator_override, "new")
        admin = client_for(superadmin)

        before = approve_payment(admin, bound_company)
        old_accrual = CashbackAccrual.objects.get(payment=before)
        old_commission = SalesCommission.objects.get(payment=before)
        assert old_accrual.integrator == integrator
        assert old_commission.sales_manager == old_manager

        response = admin.post(
            reassign_url(bound_company),
            {"integrator_id": integrator_override.pk, "note": "moved by request"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["company"]["integrator_id"] == integrator_override.pk

        after = approve_payment(admin, bound_company)
        new_accrual = CashbackAccrual.objects.get(payment=after)
        assert new_accrual.integrator == integrator_override
        assert new_accrual.percent == Decimal("15.00")  # the new integrator's rate
        new_commission = SalesCommission.objects.get(payment=after)
        assert new_commission.sales_manager == new_manager
        assert new_commission.integrator == integrator_override

        # Earlier rows keep their owner, amount and status.
        old_accrual.refresh_from_db()
        old_commission.refresh_from_db()
        assert old_accrual.integrator == integrator
        assert old_accrual.amount_uzs == 10000
        assert old_accrual.status == CashbackAccrual.Status.ACCRUED
        assert old_commission.sales_manager == old_manager
        assert old_commission.integrator == integrator

    def test_unassign_stops_accruals(
        self, superadmin: User, bound_company: Company, integrator: Integrator
    ) -> None:
        attach_sales_manager(integrator, "solo")
        admin = client_for(superadmin)

        response = admin.post(reassign_url(bound_company), {"integrator_id": None}, format="json")
        assert response.status_code == 200
        assert response.json()["company"]["integrator_id"] is None
        assert response.json()["entry"]["to"] is None

        payment = approve_payment(admin, bound_company)
        assert not CashbackAccrual.objects.filter(payment=payment).exists()
        assert not SalesCommission.objects.filter(payment=payment).exists()

    def test_assign_to_unbound_company(self, superadmin: User, integrator: Integrator) -> None:
        from .conftest import make_company

        company = make_company("orphan-co")
        response = client_for(superadmin).post(
            reassign_url(company), {"integrator_id": integrator.pk}, format="json"
        )
        assert response.status_code == 200
        entry = response.json()["entry"]
        assert entry["from"] is None
        assert entry["to"]["id"] == integrator.pk
        company.refresh_from_db()
        assert company.integrator == integrator
        # acquired_via is left as is (the original acquisition path).
        assert company.acquired_via == Company.AcquiredVia.SELF_SIGNUP


class TestReassignValidation:
    def test_inactive_integrator_rejected(
        self, superadmin: User, bound_company: Company, integrator_override: Integrator
    ) -> None:
        integrator_override.status = Integrator.Status.SUSPENDED
        integrator_override.save(update_fields=["status"])

        response = client_for(superadmin).post(
            reassign_url(bound_company), {"integrator_id": integrator_override.pk}, format="json"
        )
        assert response.status_code == 400
        assert "not active" in response.json()["message"]
        bound_company.refresh_from_db()
        assert bound_company.integrator_id != integrator_override.pk
        assert not AuditLog.objects.filter(action=services.INTEGRATOR_REASSIGNED).exists()

    def test_same_integrator_rejected(
        self, superadmin: User, bound_company: Company, integrator: Integrator
    ) -> None:
        admin = client_for(superadmin)
        response = admin.post(
            reassign_url(bound_company), {"integrator_id": integrator.pk}, format="json"
        )
        assert response.status_code == 400
        assert "already assigned" in response.json()["message"]

        assert admin.post(reassign_url(bound_company), {}, format="json").status_code == 200
        again = admin.post(reassign_url(bound_company), {"integrator_id": None}, format="json")
        assert again.status_code == 400
        assert "no integrator" in again.json()["message"]
        assert AuditLog.objects.filter(action=services.INTEGRATOR_REASSIGNED).count() == 1

    def test_unknown_integrator_and_long_note(
        self, superadmin: User, bound_company: Company, integrator_override: Integrator
    ) -> None:
        admin = client_for(superadmin)
        for bad_id in (999999, "abc"):
            response = admin.post(
                reassign_url(bound_company), {"integrator_id": bad_id}, format="json"
            )
            assert response.status_code == 400
            assert "not found" in response.json()["message"]

        too_long = admin.post(
            reassign_url(bound_company),
            {"integrator_id": integrator_override.pk, "note": "x" * 501},
            format="json",
        )
        assert too_long.status_code == 400
        assert "500" in too_long.json()["message"]

        missing = admin.post("/api/admin/v1/companies/999999/reassign", {}, format="json")
        assert missing.status_code == 404

    def test_superadmin_only(
        self,
        platform_admin: User,
        integrator: Integrator,
        bound_company: Company,
        integrator_override: Integrator,
    ) -> None:
        body = {"integrator_id": integrator_override.pk}
        for user in (platform_admin, integrator.user):
            response = client_for(user).post(reassign_url(bound_company), body, format="json")
            assert response.status_code == 403
        bound_company.refresh_from_db()
        assert bound_company.integrator == integrator


class TestReassignNotifications:
    def test_old_and_new_integrators_are_notified(
        self,
        superadmin: User,
        bound_company: Company,
        integrator: Integrator,
        integrator_override: Integrator,
    ) -> None:
        services.reassign_integrator(bound_company, integrator_override, actor=superadmin)

        old_note = PlatformNotification.objects.get(user=integrator.user)
        new_note = PlatformNotification.objects.get(user=integrator_override.user)
        assert bound_company.name in old_note.message
        assert "o'tkazildi" in old_note.message
        assert "biriktirildi" in new_note.message


class TestIntegratorHistory:
    def test_history_newest_first_with_actor_from_to_note(
        self,
        superadmin: User,
        platform_admin: User,
        bound_company: Company,
        integrator: Integrator,
        integrator_override: Integrator,
    ) -> None:
        admin = client_for(superadmin)
        admin.post(
            reassign_url(bound_company),
            {"integrator_id": integrator_override.pk, "note": "  first move  "},
            format="json",
        )
        admin.post(
            reassign_url(bound_company), {"integrator_id": None, "note": "cleared"}, format="json"
        )

        # Names are snapshotted: a later rename doesn't rewrite history.
        integrator_override.name = "Renamed Beta"
        integrator_override.save(update_fields=["name"])

        response = client_for(platform_admin).get(history_url(bound_company))  # staff can read
        assert response.status_code == 200
        history = response.json()["history"]
        assert len(history) == 2

        latest, first = history
        assert latest["note"] == "cleared"
        assert latest["from"] == {
            "id": integrator_override.pk,
            "name": "Integrator beta",
            "company_name": "",
        }
        assert latest["to"] is None
        assert latest["actor"] == {"id": superadmin.pk, "email": superadmin.email}

        assert first["note"] == "first move"  # stripped
        assert first["from"]["id"] == integrator.pk
        assert first["from"]["name"] == "Integrator alpha"
        assert first["to"]["id"] == integrator_override.pk
        assert first["at"] <= latest["at"]
        assert set(first) == {"id", "at", "actor", "from", "to", "note"}

    def test_legacy_rows_fall_back_to_current_names(
        self, superadmin: User, bound_company: Company, integrator: Integrator
    ) -> None:
        # Shape written before names were snapshotted: ids only, no note.
        AuditLog.objects.create(
            company=bound_company,
            actor=None,
            action=services.INTEGRATOR_REASSIGNED,
            target_model="companies.Company",
            target_id=str(bound_company.pk),
            changes={"from": None, "to": integrator.pk},
        )
        row = client_for(superadmin).get(history_url(bound_company)).json()["history"][0]
        assert row["actor"] is None
        assert row["from"] is None
        assert row["to"] == {"id": integrator.pk, "name": "Integrator alpha", "company_name": ""}
        assert row["note"] == ""

    def test_history_is_scoped_and_staff_only(
        self, superadmin: User, bound_company: Company, integrator: Integrator
    ) -> None:
        from .conftest import make_company

        other = make_company("other-co", integrator=integrator)
        services.reassign_integrator(other, None, actor=superadmin)

        assert client_for(superadmin).get(history_url(bound_company)).json()["history"] == []
        assert client_for(integrator.user).get(history_url(bound_company)).status_code == 403
        missing = client_for(superadmin).get("/api/admin/v1/companies/999999/integrator-history")
        assert missing.status_code == 404


class TestCompanyDetailCashbacks:
    def test_detail_lists_cashbacks_newest_first(
        self,
        superadmin: User,
        bound_company: Company,
        integrator: Integrator,
        integrator_override: Integrator,
    ) -> None:
        admin = client_for(superadmin)
        first = approve_payment(admin, bound_company, 100000)
        services.reassign_integrator(bound_company, integrator_override, actor=superadmin)
        second = approve_payment(admin, bound_company, 200000)

        detail = admin.get(f"/api/admin/v1/companies/{bound_company.pk}").json()["company"]
        cashbacks = detail["cashbacks"]
        assert [c["payment_id"] for c in cashbacks] == [second.pk, first.pk]
        assert cashbacks[0] == {
            "id": CashbackAccrual.objects.get(payment=second).pk,
            "payment_id": second.pk,
            "integrator_id": integrator_override.pk,
            "integrator_name": "Integrator beta",
            "percent": "15.00",
            "amount_uzs": 30000,
            "status": "accrued",
            "created_at": cashbacks[0]["created_at"],
        }
        assert cashbacks[1]["integrator_id"] == integrator.pk
        assert cashbacks[1]["amount_uzs"] == 10000
