"""Invoice math: seats × price, mid-period seat changes, price-next-period rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.billing import services
from apps.billing.models import Invoice, PricingSetting, Subscription
from apps.billing.tasks import run_invoice_generation, run_monthly_settlement
from apps.companies.models import Company

from .conftest import PRICE, make_operators

pytestmark = pytest.mark.django_db


class TestInvoiceMath:
    def test_total_is_seats_times_price(self, company: Company, subscription: Subscription) -> None:
        make_operators(company, 4)
        make_operators(company, 2, active=False)  # inactive seats don't count

        invoice = services.roll_period(subscription, now=timezone.now())

        assert invoice.total_uzs == 4 * PRICE
        line = invoice.lines.get()
        assert line.quantity == 4
        assert line.unit_price_uzs == PRICE
        assert invoice.status == Invoice.Status.PENDING

    def test_operator_added_mid_period_counts_in_next_invoice(
        self, company: Company, subscription: Subscription
    ) -> None:
        make_operators(company, 3)
        now = timezone.now()

        first = services.roll_period(subscription, now=now)
        assert first.total_uzs == 3 * PRICE

        # Mid-period hire → next period-end invoice includes the new seat.
        make_operators(company, 1)
        subscription.refresh_from_db()
        second = services.roll_period(subscription, now=now + timedelta(days=30))
        assert second.total_uzs == 4 * PRICE

    def test_price_change_applies_next_period_only(
        self, company: Company, subscription: Subscription, pricing: PricingSetting
    ) -> None:
        make_operators(company, 2)
        now = timezone.now()

        # Admin raises the price MID-period.
        pricing.price_per_operator_uzs = 80000
        pricing.save()

        # Invoice for the period that just ended → OLD snapshot price.
        first = services.roll_period(subscription, now=now)
        assert first.total_uzs == 2 * PRICE
        assert first.lines.get().unit_price_uzs == PRICE

        # The rolled subscription picked up the NEW price for the new period…
        subscription.refresh_from_db()
        assert subscription.price_per_operator_uzs == 80000

        # …so the NEXT period-end invoice bills at the new price.
        second = services.roll_period(subscription, now=now + timedelta(days=30))
        assert second.total_uzs == 2 * 80000

    def test_period_rolls_forward_30_days(
        self, company: Company, subscription: Subscription
    ) -> None:
        old_end = subscription.current_period_end
        assert old_end is not None
        services.roll_period(subscription, now=timezone.now())
        subscription.refresh_from_db()
        assert subscription.current_period_start == old_end
        assert subscription.current_period_end == old_end + timedelta(days=30)


class TestInvoiceSweepTask:
    def test_only_due_subscriptions_are_invoiced(
        self, company: Company, subscription: Subscription, pricing: PricingSetting
    ) -> None:
        """Prepaid billing cycles superseded period-end invoices: the sweep
        issues none, and only cycles that have ENDED are settled/rolled."""
        make_operators(company, 1)
        now = datetime(2026, 9, 1, 0, 30, tzinfo=UTC)
        due_end = datetime(2026, 9, 1, tzinfo=UTC)
        subscription.current_period_start = datetime(2026, 8, 1, tzinfo=UTC)
        subscription.current_period_end = due_end
        subscription.save()
        # A second company whose cycle is NOT over yet.
        other = Company.objects.create(name="Fresh Co", slug="fresh-co")
        fresh_end = datetime(2026, 9, 30, tzinfo=UTC)
        fresh = Subscription.all_objects.create(
            company=other,
            status=Subscription.Status.ACTIVE,
            price_per_operator_uzs=PRICE,
            current_period_start=datetime(2026, 8, 31, tzinfo=UTC),
            current_period_end=fresh_end,
        )

        assert run_invoice_generation(now) == 0
        assert Invoice.all_objects.count() == 0

        assert run_monthly_settlement(now) == 1
        subscription.refresh_from_db()
        fresh.refresh_from_db()
        assert subscription.current_period_start == due_end
        assert subscription.current_period_end == datetime(2026, 10, 1, tzinfo=UTC)
        assert fresh.current_period_end == fresh_end

    def test_suspended_subscription_not_invoiced(
        self, company: Company, subscription: Subscription
    ) -> None:
        services.suspend(subscription, reason="unpaid")
        assert run_invoice_generation(timezone.now()) == 0
