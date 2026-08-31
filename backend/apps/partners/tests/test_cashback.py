"""Cashback engine (A.5): math, idempotency, snapshots, limits, lifecycle."""

from __future__ import annotations

from datetime import timedelta

import pytest

from apps.accounts.models import User
from apps.billing import services as billing
from apps.billing.models import Payment
from apps.companies.models import Company
from apps.partners import services
from apps.partners.models import (
    CashbackAccrual,
    Integrator,
    PayoutRequest,
    get_platform_settings,
)

from .conftest import client_for, make_company

pytestmark = pytest.mark.django_db


def pay(company: Company, amount: int = 300000, provider: str = "manual") -> Payment:
    payment = Payment.all_objects.create(company=company, provider=provider, amount_uzs=amount)
    billing.apply_payment(payment)  # engine hook fires here
    return payment


class TestAccrualMath:
    def test_global_default_percent(self, bound_company: Company, integrator: Integrator) -> None:
        payment = pay(bound_company, 300000)
        accrual = CashbackAccrual.objects.get(payment=payment)
        assert accrual.amount_uzs == 30000  # 10% default
        assert str(accrual.percent) == "10.00"
        assert accrual.integrator == integrator

    def test_override_beats_default(self, integrator_override: Integrator) -> None:
        company = make_company("override-co", integrator=integrator_override)
        payment = pay(company, 200000)
        accrual = CashbackAccrual.objects.get(payment=payment)
        assert accrual.amount_uzs == 30000  # 15% override
        assert str(accrual.percent) == "15.00"

    def test_all_three_providers_accrue(self, bound_company: Company) -> None:
        for provider in ("manual", "payme", "click"):
            payment = pay(bound_company, 100000, provider=provider)
            assert CashbackAccrual.objects.filter(payment=payment).exists(), provider

    def test_unbound_company_no_accrual(self, db: object) -> None:
        company = make_company("solo-co", integrator=None)
        payment = pay(company)
        assert not CashbackAccrual.objects.filter(payment=payment).exists()

    def test_suspended_integrator_no_accrual(
        self, bound_company: Company, integrator: Integrator
    ) -> None:
        integrator.status = Integrator.Status.SUSPENDED
        integrator.save()
        payment = pay(bound_company)
        assert not CashbackAccrual.objects.filter(payment=payment).exists()


class TestIdempotencyAndSnapshot:
    def test_same_payment_processed_twice_one_accrual(self, bound_company: Company) -> None:
        payment = pay(bound_company)
        # Webhook retry / double admin click:
        billing.apply_payment(payment)
        services.accrue_cashback(payment)
        assert CashbackAccrual.objects.filter(payment=payment).count() == 1

    def test_percent_change_affects_only_future_payments(
        self, bound_company: Company, superadmin: User
    ) -> None:
        first = pay(bound_company, 100000)
        settings_row = get_platform_settings()
        settings_row.default_cashback_percent = "25.00"
        settings_row.updated_by = superadmin
        settings_row.save()

        second = pay(bound_company, 100000)

        assert CashbackAccrual.objects.get(payment=first).amount_uzs == 10000  # old 10%
        assert CashbackAccrual.objects.get(payment=second).amount_uzs == 25000  # new 25%
        # History row was appended (PricingSetting-style tracking).
        assert settings_row.history.count() == 2  # create + change

    def test_months_limit_cutoff_frozen_time(self, bound_company: Company) -> None:
        limit = get_platform_settings().cashback_months_limit  # 12
        # Payment INSIDE the window (11 months after signup).
        inside = Payment.all_objects.create(
            company=bound_company, provider="manual", amount_uzs=100000
        )
        billing.apply_payment(inside, now=services.add_months(bound_company.created_at, limit - 1))
        assert CashbackAccrual.objects.filter(payment=inside).exists()

        # Payment AFTER the window (12 months + 1 day).
        outside = Payment.all_objects.create(
            company=bound_company, provider="manual", amount_uzs=100000
        )
        billing.apply_payment(
            outside,
            now=services.add_months(bound_company.created_at, limit) + timedelta(days=1),
        )
        assert not CashbackAccrual.objects.filter(payment=outside).exists()


class TestReversalAndBalance:
    def test_refund_reverses_accrual(self, bound_company: Company, integrator: Integrator) -> None:
        payment = pay(bound_company, 100000)
        assert integrator.balance_uzs == 10000

        services.reverse_cashback(payment)
        accrual = CashbackAccrual.objects.get(payment=payment)
        assert accrual.status == CashbackAccrual.Status.REVERSED
        assert accrual.reversed_at is not None
        assert integrator.balance_uzs == 0

        # Reversal is idempotent too.
        services.reverse_cashback(payment)
        assert CashbackAccrual.objects.filter(payment=payment).count() == 1

    def test_balance_property(self, bound_company: Company, integrator: Integrator) -> None:
        pay(bound_company, 100000)  # +10 000
        pay(bound_company, 200000)  # +20 000
        assert integrator.balance_uzs == 30000

        services.request_payout(integrator, 25000)
        assert integrator.balance_uzs == 5000  # pending holds funds


class TestPayoutLifecycle:
    def test_full_lifecycle_and_allocation(
        self, bound_company: Company, integrator: Integrator, superadmin: User
    ) -> None:
        pay(bound_company, 100000)
        pay(bound_company, 200000)
        payout = services.request_payout(integrator, 30000)

        services.process_payout(payout, PayoutRequest.Status.APPROVED, actor=superadmin)
        services.process_payout(payout, PayoutRequest.Status.PAID, actor=superadmin)

        payout.refresh_from_db()
        assert payout.status == PayoutRequest.Status.PAID
        assert payout.processed_by == superadmin
        # Oldest-first allocation marked both accruals paid_out.
        assert (
            CashbackAccrual.objects.filter(
                integrator=integrator, status=CashbackAccrual.Status.PAID_OUT
            ).count()
            == 2
        )
        assert integrator.balance_uzs == 0

    def test_rejected_releases_balance(
        self, bound_company: Company, integrator: Integrator, superadmin: User
    ) -> None:
        pay(bound_company, 100000)
        payout = services.request_payout(integrator, 10000)
        assert integrator.balance_uzs == 0

        services.process_payout(payout, PayoutRequest.Status.REJECTED, actor=superadmin)
        assert integrator.balance_uzs == 10000  # hold released

    def test_cannot_request_above_balance(
        self, bound_company: Company, integrator: Integrator
    ) -> None:
        pay(bound_company, 100000)
        with pytest.raises(services.PayoutError):
            services.request_payout(integrator, 999999)

    def test_cannot_request_below_minimum(
        self, bound_company: Company, integrator: Integrator
    ) -> None:
        pay(bound_company, 100000)
        settings_row = get_platform_settings()
        settings_row.min_payout_uzs = 50000
        settings_row.save()
        with pytest.raises(services.PayoutError, match="minimum"):
            services.request_payout(integrator, 5000)

    def test_invalid_transition_blocked(
        self, bound_company: Company, integrator: Integrator, superadmin: User
    ) -> None:
        pay(bound_company, 100000)
        payout = services.request_payout(integrator, 5000)
        with pytest.raises(services.PayoutError):
            services.process_payout(payout, PayoutRequest.Status.PAID, actor=superadmin)


class TestReassignment:
    def test_reassignment_keeps_old_accruals(
        self,
        bound_company: Company,
        integrator: Integrator,
        integrator_override: Integrator,
        superadmin: User,
    ) -> None:
        payment = pay(bound_company, 100000)
        old_accrual = CashbackAccrual.objects.get(payment=payment)

        services.reassign_integrator(bound_company, integrator_override, actor=superadmin)
        bound_company.refresh_from_db()
        assert bound_company.integrator == integrator_override

        # Old accrual still belongs to the ORIGINAL integrator…
        old_accrual.refresh_from_db()
        assert old_accrual.integrator == integrator

        # …and NEW payments accrue to the new one at their percent.
        new_payment = pay(bound_company, 100000)
        new_accrual = CashbackAccrual.objects.get(payment=new_payment)
        assert new_accrual.integrator == integrator_override
        assert new_accrual.amount_uzs == 15000  # beta's 15% override

    def test_direct_binding_mutation_is_blocked(
        self, bound_company: Company, integrator_override: Integrator
    ) -> None:
        bound_company.integrator = integrator_override
        with pytest.raises(ValueError, match="immutable"):
            bound_company.save()

    def test_reassign_endpoint_superadmin_only(
        self,
        bound_company: Company,
        integrator_override: Integrator,
        superadmin: User,
        platform_admin: User,
    ) -> None:
        url = f"/api/admin/v1/companies/{bound_company.pk}/reassign"
        body = {"integrator_id": integrator_override.pk}
        assert client_for(platform_admin).post(url, body, format="json").status_code == 403
        assert client_for(superadmin).post(url, body, format="json").status_code == 200
