"""Daily billing model: per-operator-day charges, balance, statements,
notifications, grace-period blocking."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone as dt_tz

import pytest

from apps.billing import services, tasks
from apps.billing.models import (
    BillingNotification,
    DailyCharge,
    MonthlyStatement,
    Payment,
    PricingSetting,
    Subscription,
)
from apps.companies.models import Company

from .conftest import PRICE, make_operators

pytestmark = pytest.mark.django_db

AUG_DAYS = 31
RATE_AUG = round(PRICE / AUG_DAYS)


def dt(y: int, m: int, d: int, h: int = 12) -> datetime:
    return datetime(y, m, d, h, tzinfo=dt_tz.utc)


class TestDailyAccrual:
    def test_accrues_one_charge_per_active_operator(self, company: Company) -> None:
        make_operators(company, 2)
        make_operators(company, 1, active=False)
        day = date(2026, 8, 15)
        assert services.accrue_company_day(company, day) == 2
        # Idempotent — a second run adds nothing.
        assert services.accrue_company_day(company, day) == 2
        charges = DailyCharge.all_objects.filter(company=company, date=day)
        assert charges.count() == 2
        assert {c.amount_uzs for c in charges} == {RATE_AUG}

    def test_trial_and_suspended_companies_are_free(self, company: Company) -> None:
        make_operators(company, 1)
        company.status = Company.Status.TRIAL
        company.save(update_fields=["status"])
        assert services.accrue_company_day(company, date(2026, 8, 15)) == 0
        assert DailyCharge.all_objects.filter(company=company).count() == 0

    def test_rate_follows_tariff_change_same_day(self, company: Company) -> None:
        (operator,) = make_operators(company, 1)
        services.accrue_operator_day(company, operator, date(2026, 8, 10))
        row = PricingSetting.objects.get(company=None)
        row.price_per_operator_uzs = 93000
        row.save()
        services.accrue_operator_day(company, operator, date(2026, 8, 11))
        by_date = {
            c.date: c for c in DailyCharge.all_objects.filter(company=company)
        }
        assert by_date[date(2026, 8, 10)].amount_uzs == RATE_AUG
        assert by_date[date(2026, 8, 11)].amount_uzs == round(93000 / AUG_DAYS)
        assert by_date[date(2026, 8, 11)].price_per_operator_uzs == 93000

    def test_nightly_task_bills_previous_day(self, company: Company) -> None:
        make_operators(company, 3)
        # 00:30 on Aug 16 bills Aug 15.
        assert tasks.run_daily_accrual(dt(2026, 8, 16, 0)) == 3
        assert DailyCharge.all_objects.filter(date=date(2026, 8, 15)).count() == 3


class TestMonthlySettlement:
    def _accrue_month(self, company: Company, operators: int, days: int) -> int:
        ops = make_operators(company, operators)
        for d in range(1, days + 1):
            for op in ops:
                services.accrue_operator_day(company, op, date(2026, 8, d))
        return operators * days * RATE_AUG

    def test_settles_from_balance_and_notifies(self, company: Company) -> None:
        total = self._accrue_month(company, 2, 10)
        company.balance_uzs = 500_000
        company.save(update_fields=["balance_uzs"])
        assert tasks.run_monthly_settlement(dt(2026, 9, 1, 0)) == 1
        company.refresh_from_db()
        statement = MonthlyStatement.all_objects.get(company=company)
        assert statement.month == date(2026, 8, 1)
        assert statement.total_uzs == total
        assert statement.status == MonthlyStatement.Status.PAID
        assert company.balance_uzs == 500_000 - total
        kinds = set(
            BillingNotification.all_objects.filter(company=company).values_list(
                "kind", flat=True
            )
        )
        assert BillingNotification.Kind.CHARGE_SETTLED in kinds

    def test_insufficient_balance_leaves_pending_and_warns(self, company: Company) -> None:
        self._accrue_month(company, 2, 10)
        assert tasks.run_monthly_settlement(dt(2026, 9, 1, 0)) == 1
        statement = MonthlyStatement.all_objects.get(company=company)
        assert statement.status == MonthlyStatement.Status.PENDING
        assert BillingNotification.all_objects.filter(
            company=company, kind=BillingNotification.Kind.PAYMENT_DUE
        ).exists()

    def test_not_first_of_month_is_noop(self, company: Company) -> None:
        self._accrue_month(company, 1, 5)
        assert tasks.run_monthly_settlement(dt(2026, 9, 2, 0)) == 0


class TestOverdueBlocking:
    def _pending_statement(self, company: Company) -> MonthlyStatement:
        return MonthlyStatement.all_objects.create(
            company=company, month=date(2026, 8, 1), total_uzs=100_000
        )

    def test_blocks_after_grace_days(
        self, company: Company, subscription: Subscription
    ) -> None:
        self._pending_statement(company)
        # Sep 1 + 2 grace days → still open on Sep 2, blocked on Sep 3.
        assert services.run_overdue_enforcement(dt(2026, 9, 2, 12)) == 0
        assert services.run_overdue_enforcement(dt(2026, 9, 3, 2)) == 1
        company.refresh_from_db()
        assert company.status == Company.Status.SUSPENDED
        assert BillingNotification.all_objects.filter(
            company=company, kind=BillingNotification.Kind.BLOCKED
        ).exists()
        statement = MonthlyStatement.all_objects.get(company=company)
        assert statement.status == MonthlyStatement.Status.OVERDUE

    def test_payment_credits_balance_settles_and_unblocks(
        self, company: Company, subscription: Subscription
    ) -> None:
        self._pending_statement(company)
        services.run_overdue_enforcement(dt(2026, 9, 3, 2))
        payment = Payment.all_objects.create(
            company=company, provider="manual", amount_uzs=300_000
        )
        services.apply_payment(payment, now=dt(2026, 9, 4, 10))
        company.refresh_from_db()
        assert company.balance_uzs == 200_000  # 300k − 100k statement
        assert company.status == Company.Status.ACTIVE
        statement = MonthlyStatement.all_objects.get(company=company)
        assert statement.status == MonthlyStatement.Status.PAID
        assert BillingNotification.all_objects.filter(
            company=company, kind=BillingNotification.Kind.PAYMENT_RECEIVED
        ).exists()


class TestTariffChangeNotification:
    def test_global_price_change_notifies_companies(self, company: Company) -> None:
        row = PricingSetting.objects.get(company=None)
        row.price_per_operator_uzs = 60000
        row.save()
        note = BillingNotification.all_objects.filter(
            company=company, kind=BillingNotification.Kind.TARIFF_CHANGED
        ).first()
        assert note is not None
        assert "60 000" in note.message

    def test_trial_days_change_does_not_notify(self, company: Company) -> None:
        row = PricingSetting.objects.get(company=None)
        row.trial_days = 30
        row.save()
        assert not BillingNotification.all_objects.filter(
            kind=BillingNotification.Kind.TARIFF_CHANGED
        ).exists()


class TestDailyRate:
    def test_rate_uses_days_in_month(self) -> None:
        assert services.daily_rate(PRICE, date(2026, 2, 10)) == round(
            PRICE / calendar.monthrange(2026, 2)[1]
        )
        assert services.daily_rate(PRICE, date(2026, 8, 10)) == RATE_AUG
