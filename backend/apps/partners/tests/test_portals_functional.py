"""Functional endpoint coverage: admin portal flows + partner portal flows."""

from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.billing.models import Payment
from apps.companies.models import Company
from apps.partners import services
from apps.partners.models import Integrator

from .conftest import client_for, make_company

pytestmark = pytest.mark.django_db


class TestAdminPortalFlows:
    def test_dashboard_kpis(self, superadmin: User, bound_company: Company) -> None:
        body = client_for(superadmin).get("/api/admin/v1/dashboard").json()
        assert body["companies"]["total"] >= 1
        assert "mrr_uzs" in body and "pending_payouts" in body

    def test_companies_list_filters_and_detail(
        self, platform_admin: User, bound_company: Company
    ) -> None:
        client = client_for(platform_admin)
        listing = client.get("/api/admin/v1/companies?q=bound").json()
        assert [c["slug"] for c in listing["companies"]] == ["bound-co"]
        listing2 = client.get("/api/admin/v1/companies?status=suspended").json()
        assert listing2["companies"] == []

        detail = client.get(f"/api/admin/v1/companies/{bound_company.pk}").json()["company"]
        assert detail["slug"] == "bound-co"
        assert "operators" in detail and "payments" in detail

    def test_company_lifecycle_actions(self, platform_admin: User, bound_company: Company) -> None:
        client = client_for(platform_admin)
        base = f"/api/admin/v1/companies/{bound_company.pk}"

        assert client.post(f"{base}/suspend").json()["company"]["status"] == "suspended"
        assert client.post(f"{base}/activate").json()["company"]["status"] == "active"
        extended = client.post(f"{base}/extend-trial", {"days": 10}, format="json").json()
        assert extended["company"]["status"] == "trial"
        assert extended["company"]["trial_ends_at"] is not None
        assert client.post(f"{base}/explode").status_code == 400

    def test_payment_approve_fires_cashback(
        self, platform_admin: User, bound_company: Company, integrator: Integrator
    ) -> None:
        payment = Payment.all_objects.create(
            company=bound_company, provider="manual", amount_uzs=500000
        )
        body = (
            client_for(platform_admin).post(f"/api/admin/v1/payments/{payment.pk}/approve").json()
        )
        assert body["payment_status"] == "approved"
        assert body["cashback_accrued_uzs"] == 50000  # 10%

    def test_integrator_create_and_suspend(self, superadmin: User) -> None:
        client = client_for(superadmin)
        created = client.post(
            "/api/admin/v1/integrators",
            {"email": "newpartner@x.uz", "name": "New Partner", "password": "partner-pw-1"},
            format="json",
        )
        assert created.status_code == 201
        integrator_id = created.json()["integrator"]["id"]
        assert len(created.json()["integrator"]["referral_code"]) == 8

        assert (
            client.post(
                "/api/admin/v1/integrators",
                {"email": "newpartner@x.uz", "name": "Dup", "password": "partner-pw-1"},
                format="json",
            ).status_code
            == 400
        )

        assert (
            client.patch(
                f"/api/admin/v1/integrators/{integrator_id}",
                {"status": "suspended"},
                format="json",
            ).status_code
            == 200
        )
        assert Integrator.objects.get(pk=integrator_id).status == "suspended"

    def test_cashback_settings_roundtrip(self, superadmin: User) -> None:
        client = client_for(superadmin)
        before = client.get("/api/admin/v1/settings/cashback").json()
        assert before["default_cashback_percent"] == "10.00"

        assert client.put(
            "/api/admin/v1/settings/cashback",
            {"default_cashback_percent": "12.50", "cashback_months_limit": 6},
            format="json",
        ).json()["success"]
        after = client.get("/api/admin/v1/settings/cashback").json()
        assert after["default_cashback_percent"] == "12.50"
        assert after["cashback_months_limit"] == 6

    def test_platform_admin_crud(self, superadmin: User) -> None:
        client = client_for(superadmin)
        created = client.post(
            "/api/admin/v1/admins",
            {"email": "second-admin@x.uz", "password": "admin-pw-123"},
            format="json",
        )
        assert created.status_code == 201
        admin_id = created.json()["id"]
        assert any(
            row["email"] == "second-admin@x.uz"
            for row in client.get("/api/admin/v1/admins").json()["admins"]
        )
        assert client.patch(
            f"/api/admin/v1/admins/{admin_id}", {"is_active": False}, format="json"
        ).json()["success"]
        assert not User.objects.get(pk=admin_id).is_active

    def test_payout_queue_and_actions(
        self, superadmin: User, bound_company: Company, integrator: Integrator
    ) -> None:
        payment = Payment.all_objects.create(
            company=bound_company, provider="manual", amount_uzs=100000
        )
        from apps.billing import services as billing

        billing.apply_payment(payment)
        payout = services.request_payout(integrator, 5000)

        client = client_for(superadmin)
        queue = client.get("/api/admin/v1/payouts?status=pending").json()["payouts"]
        assert [p["id"] for p in queue] == [payout.pk]

        assert (
            client.post(f"/api/admin/v1/payouts/{payout.pk}/approve").json()["status"] == "approved"
        )
        assert (
            client.post(f"/api/admin/v1/payouts/{payout.pk}/mark-paid").json()["status"] == "paid"
        )
        # Terminal state → further actions rejected.
        assert client.post(f"/api/admin/v1/payouts/{payout.pk}/reject").status_code == 400
        assert client.post(f"/api/admin/v1/payouts/{payout.pk}/detonate").status_code == 400

    def test_audit_query_filters(self, superadmin: User, bound_company: Company) -> None:
        services.reassign_integrator(bound_company, None, actor=superadmin)
        client = client_for(superadmin)
        entries = client.get("/api/admin/v1/audit?action=integrator_reassigned").json()["entries"]
        assert entries and entries[0]["company"] == "bound-co"
        scoped = client.get(
            f"/api/admin/v1/audit?company={bound_company.pk}&date_from=2000-01-01"
        ).json()["entries"]
        assert scoped


class TestPartnerPortalFlows:
    def test_dashboard_series_and_percent(self, integrator_override: Integrator) -> None:
        company = make_company("series-co", integrator=integrator_override)
        from apps.billing import services as billing

        payment = Payment.all_objects.create(company=company, provider="click", amount_uzs=200000)
        billing.apply_payment(payment)

        body = client_for(integrator_override.user).get("/api/partner/v1/dashboard").json()
        assert body["effective_percent"] == "15.00"
        assert body["accrued_total_uzs"] == 30000
        assert len(body["monthly_series"]) == 12
        assert sum(m["amount_uzs"] for m in body["monthly_series"]) == 30000

    def test_accrual_ledger_filters(self, bound_company: Company, integrator: Integrator) -> None:
        from apps.billing import services as billing

        payment = Payment.all_objects.create(
            company=bound_company, provider="manual", amount_uzs=100000
        )
        billing.apply_payment(payment)
        client = client_for(integrator.user)

        assert len(client.get("/api/partner/v1/accruals?status=accrued").json()["accruals"]) == 1
        assert client.get("/api/partner/v1/accruals?status=reversed").json()["accruals"] == []
        assert (
            len(
                client.get(
                    f"/api/partner/v1/accruals?company={bound_company.pk}&date_from=2000-01-01"
                ).json()["accruals"]
            )
            == 1
        )

    def test_payout_create_via_endpoint(
        self, bound_company: Company, integrator: Integrator
    ) -> None:
        from apps.billing import services as billing

        payment = Payment.all_objects.create(
            company=bound_company, provider="manual", amount_uzs=100000
        )
        billing.apply_payment(payment)
        client = client_for(integrator.user)

        ok = client.post("/api/partner/v1/payouts", {"amount_uzs": 8000}, format="json")
        assert ok.status_code == 201
        assert ok.json()["balance_uzs"] == 2000

        too_much = client.post("/api/partner/v1/payouts", {"amount_uzs": 99999}, format="json")
        assert too_much.status_code == 400
        garbage = client.post("/api/partner/v1/payouts", {"amount_uzs": "x"}, format="json")
        assert garbage.status_code == 400

        listing = client.get("/api/partner/v1/payouts").json()
        assert listing["payouts"][0]["amount_uzs"] == 8000

    def test_profile_update(self, integrator: Integrator) -> None:
        client = client_for(integrator.user)
        assert client.put(
            "/api/partner/v1/profile",
            {"name": "Renamed Partner", "payout_details": {"card": "8600 **** 1234"}},
            format="json",
        ).json()["success"]
        profile = client.get("/api/partner/v1/profile").json()
        assert profile["name"] == "Renamed Partner"
        assert profile["payout_details"]["card"] == "8600 **** 1234"

    def test_on_behalf_duplicate_slug_rejected(self, integrator: Integrator) -> None:
        make_company("taken-co")
        response = client_for(integrator.user).post(
            "/api/partner/v1/companies",
            {"company_name": "Taken Co", "admin_email": "t@x.uz", "password": "pw-12345678"},
            format="json",
        )
        assert response.status_code == 400


class TestPhase11Additions:
    def test_dashboard_series_and_calls_today(
        self, superadmin: User, bound_company: Company
    ) -> None:
        body = client_for(superadmin).get("/api/admin/v1/dashboard").json()
        assert len(body["payments_series"]) == 30
        assert len(body["calls_series"]) == 30
        assert "calls_today" in body

    def test_payments_list_filters_and_refund(
        self, superadmin: User, bound_company: Company, integrator: Integrator
    ) -> None:
        from apps.billing import services as billing
        from apps.partners.models import CashbackAccrual

        payment = Payment.all_objects.create(
            company=bound_company, provider="payme", amount_uzs=100000
        )
        billing.apply_payment(payment)
        client = client_for(superadmin)

        rows = client.get("/api/admin/v1/payments?provider=payme").json()["payments"]
        assert rows[0]["cashback_uzs"] == 10000
        assert client.get("/api/admin/v1/payments?provider=click").json()["payments"] == []

        # Refund reverses cashback.
        assert client.post(f"/api/admin/v1/payments/{payment.pk}/refund").json()["success"]
        accrual = CashbackAccrual.objects.get(payment=payment)
        assert accrual.status == CashbackAccrual.Status.REVERSED
        # Double refund blocked (no longer approved).
        assert client.post(f"/api/admin/v1/payments/{payment.pk}/refund").status_code == 400

    def test_pricing_editor_superadmin_only(self, superadmin: User, platform_admin: User) -> None:
        assert client_for(platform_admin).get("/api/admin/v1/settings/pricing").status_code == 403
        client = client_for(superadmin)
        assert client.put(
            "/api/admin/v1/settings/pricing",
            {"price_per_operator_uzs": 60000},
            format="json",
        ).json()["success"]
        body = client.get("/api/admin/v1/settings/pricing").json()
        assert body["price_per_operator_uzs"] == 60000
        assert body["history"]  # history-tracked

    def test_integrator_detail_payload(
        self, superadmin: User, bound_company: Company, integrator: Integrator
    ) -> None:
        from apps.billing import services as billing

        payment = Payment.all_objects.create(
            company=bound_company, provider="manual", amount_uzs=100000
        )
        billing.apply_payment(payment)

        body = client_for(superadmin).get(f"/api/admin/v1/integrators/{integrator.pk}").json()
        info = body["integrator"]
        assert info["effective_percent"] == "10.00"
        assert info["override_percent"] is None
        assert info["lifetime_cashback_uzs"] == 10000
        assert body["companies"][0]["cashback_uzs"] == 10000
        assert len(body["accruals"]) == 1


class TestAdminEditing:
    """Phase-13: company + integrator editing from the admin portal."""

    def test_company_patch_name_and_retention(
        self, platform_admin: User, bound_company: Company
    ) -> None:
        client = client_for(platform_admin)
        body = client.patch(
            f"/api/admin/v1/companies/{bound_company.pk}",
            {"name": "Renamed Co", "audio_retention_days": 90},
            format="json",
        ).json()
        assert body["company"]["name"] == "Renamed Co"
        assert body["company"]["audio_retention_days"] == 90
        bound_company.refresh_from_db()
        assert bound_company.name == "Renamed Co"
        assert bound_company.slug == "bound-co"  # slug untouched

    def test_company_patch_rejects_duplicate_and_empty(
        self, superadmin: User, bound_company: Company
    ) -> None:
        other = make_company("other-co")
        client = client_for(superadmin)
        base = f"/api/admin/v1/companies/{bound_company.pk}"
        assert client.patch(base, {"name": other.name.upper()}, format="json").status_code == 400
        assert client.patch(base, {"name": "  "}, format="json").status_code == 400
        assert client.patch(base, {}, format="json").status_code == 400
        assert (
            client.patch(base, {"audio_retention_days": "zero"}, format="json").status_code == 400
        )

    def test_company_patch_clears_retention(self, superadmin: User, bound_company: Company) -> None:
        bound_company.audio_retention_days = 30
        bound_company.save(update_fields=["audio_retention_days"])
        body = (
            client_for(superadmin)
            .patch(
                f"/api/admin/v1/companies/{bound_company.pk}",
                {"audio_retention_days": None},
                format="json",
            )
            .json()
        )
        assert body["company"]["audio_retention_days"] is None

    def test_integrator_patch_contacts_and_payout_details(
        self, superadmin: User, integrator: Integrator
    ) -> None:
        client = client_for(superadmin)
        body = client.patch(
            f"/api/admin/v1/integrators/{integrator.pk}",
            {
                "phone": " +998901234567 ",
                "email": "NEW@partners.uz",
                "payout_details": {"card": "8600 12** **** 1234", "bank": "Kapital"},
            },
            format="json",
        ).json()
        assert body["success"] is True
        integrator.refresh_from_db()
        integrator.user.refresh_from_db()
        assert integrator.phone == "+998901234567"
        assert integrator.user.email == "new@partners.uz"
        assert integrator.user.username == "new@partners.uz"
        assert integrator.payout_details["bank"] == "Kapital"

    def test_integrator_patch_rejects_bad_email_and_details(
        self, superadmin: User, integrator: Integrator, integrator_override: Integrator
    ) -> None:
        client = client_for(superadmin)
        base = f"/api/admin/v1/integrators/{integrator.pk}"
        # duplicate email (belongs to the other integrator's user)
        taken = integrator_override.user.username
        assert client.patch(base, {"email": taken}, format="json").status_code == 400
        assert client.patch(base, {"email": ""}, format="json").status_code == 400
        assert client.patch(base, {"payout_details": "card"}, format="json").status_code == 400
