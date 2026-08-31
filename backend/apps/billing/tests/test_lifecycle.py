"""Trial expiry, state machine, manual payment approval → activation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, User
from apps.billing import services
from apps.billing.models import Invoice, Payment, PricingSetting, Subscription
from apps.billing.tasks import run_trial_expiry
from apps.companies.models import Company
from apps.core.models import AuditLog

from .conftest import PRICE

pytestmark = pytest.mark.django_db


@pytest.fixture
def trial_company(pricing: PricingSetting) -> Company:
    now = timezone.now()
    company = Company.objects.create(
        name="Trial Co",
        slug="trial-co",
        status=Company.Status.TRIAL,
        trial_ends_at=now + timedelta(days=14),
    )
    Subscription.all_objects.create(
        company=company,
        status=Subscription.Status.TRIAL,
        price_per_operator_uzs=PRICE,
        trial_ends_at=company.trial_ends_at,
    )
    return company


def make_device_operator(company: Company) -> OperatorProfile:
    user = User.objects.create_user(username=f"dev-op@{company.slug}", company=company)
    return OperatorProfile.all_objects.create(
        company=company, user=user, user_name="dev-op", api_key="trial-co-key"
    )


class TestTrialExpiry:
    def test_frozen_time_sweep_suspends_and_blocks_upload(self, trial_company: Company) -> None:
        make_device_operator(trial_company)
        frozen_now = timezone.now() + timedelta(days=15)  # past trial_ends_at

        count = run_trial_expiry(frozen_now)

        assert count == 1
        trial_company.refresh_from_db()
        assert trial_company.status == Company.Status.SUSPENDED
        subscription = Subscription.all_objects.get(company=trial_company)
        assert subscription.status == Subscription.Status.SUSPENDED
        assert AuditLog.objects.filter(
            company=trial_company, action="subscription.suspended"
        ).exists()

        # Mobile upload now rejected with 402 — driven by real state.
        response = APIClient().post(
            "/api/call/v1/upload",
            {
                "user_name": "dev-op",
                "api_key": "trial-co-key",
                "call_id": "post-expiry-1",
                "call_type": "inbound",
                "call_status": "answered",
                "from": "+998901234567",
                "to": "+998998887766",
                "counterparty_number": "+998901234567",
                "duration": 10,
                "start_time": "2026-08-14 10:00:00",
            },
            format="json",
        )
        assert response.status_code == 402
        assert response.json()["error_code"] == "SUBSCRIPTION_INACTIVE"

    def test_sweep_ignores_live_trials(self, trial_company: Company) -> None:
        assert run_trial_expiry(timezone.now()) == 0
        trial_company.refresh_from_db()
        assert trial_company.status == Company.Status.TRIAL


class TestStateMachine:
    def test_full_lifecycle(self, trial_company: Company) -> None:
        subscription = Subscription.all_objects.get(company=trial_company)

        services.activate(subscription)
        assert subscription.status == Subscription.Status.ACTIVE
        assert subscription.current_period_end is not None

        services.suspend(subscription, reason="unpaid")
        assert subscription.status == Subscription.Status.SUSPENDED

        services.activate(subscription)  # payment arrived
        assert subscription.status == Subscription.Status.ACTIVE

        services.cancel(subscription)
        assert subscription.status == Subscription.Status.CANCELED

    def test_canceled_is_terminal(self, trial_company: Company) -> None:
        subscription = Subscription.all_objects.get(company=trial_company)
        services.cancel(subscription)
        with pytest.raises(services.InvalidTransition):
            services.activate(subscription)


class TestManualPaymentApproval:
    def test_apply_payment_activates_and_extends(self, trial_company: Company) -> None:
        subscription = Subscription.all_objects.get(company=trial_company)
        services.suspend(subscription, reason="trial_expired")

        invoice = Invoice.all_objects.create(
            company=trial_company,
            subscription=subscription,
            total_uzs=PRICE,
            status=Invoice.Status.PENDING,
        )
        payment = Payment.all_objects.create(
            company=trial_company,
            invoice=invoice,
            provider=Payment.Provider.MANUAL,
            amount_uzs=PRICE,
        )

        now = timezone.now()
        services.apply_payment(payment, now=now)

        payment.refresh_from_db()
        invoice.refresh_from_db()
        subscription.refresh_from_db()
        trial_company.refresh_from_db()
        assert payment.status == Payment.Status.APPROVED
        assert invoice.status == Invoice.Status.PAID
        assert subscription.status == Subscription.Status.ACTIVE
        assert trial_company.status == Company.Status.ACTIVE
        assert subscription.current_period_end is not None
        assert subscription.current_period_end > now + timedelta(days=29)
        assert AuditLog.objects.filter(company=trial_company, action="payment.applied").exists()

    def test_apply_payment_is_idempotent(self, trial_company: Company) -> None:
        subscription = Subscription.all_objects.get(company=trial_company)
        services.activate(subscription)
        first_end = subscription.current_period_end

        payment = Payment.all_objects.create(
            company=trial_company, provider=Payment.Provider.MANUAL, amount_uzs=PRICE
        )
        services.apply_payment(payment)
        subscription.refresh_from_db()
        extended_end = subscription.current_period_end
        assert extended_end is not None and first_end is not None
        assert extended_end > first_end

        # Webhook retry / double click — must NOT extend again.
        services.apply_payment(payment)
        subscription.refresh_from_db()
        assert subscription.current_period_end == extended_end


class TestCeleryTaskWrappers:
    def test_suspend_expired_trials_task_with_frozen_now(self, trial_company: Company) -> None:
        from apps.billing.tasks import cleanup_expired_audio, suspend_expired_trials

        frozen = (timezone.now() + timedelta(days=15)).isoformat()
        assert suspend_expired_trials(now_iso=frozen) == 1
        trial_company.refresh_from_db()
        assert trial_company.status == Company.Status.SUSPENDED

        # Retention stub is schedulable and a no-op.
        assert cleanup_expired_audio() == 0

    def test_generate_due_invoices_task(self, trial_company: Company) -> None:
        from apps.billing.tasks import generate_due_invoices

        subscription = Subscription.all_objects.get(company=trial_company)
        services.activate(subscription)
        frozen = (timezone.now() + timedelta(days=31)).isoformat()
        assert generate_due_invoices(now_iso=frozen) == 1
        assert Invoice.all_objects.filter(company=trial_company).count() == 1
