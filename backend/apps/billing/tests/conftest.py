"""Fixtures for billing tests."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.accounts.models import OperatorProfile, User
from apps.billing.models import PricingSetting, Subscription
from apps.companies.models import Company

PRICE = 50000
TRIAL_DAYS = 14


@pytest.fixture
def pricing(db: Any) -> PricingSetting:
    return PricingSetting.objects.create(price_per_operator_uzs=PRICE, trial_days=TRIAL_DAYS)


@pytest.fixture
def company(pricing: PricingSetting) -> Company:
    return Company.objects.create(
        name="Billing Co",
        slug="billing-co",
        status=Company.Status.ACTIVE,
    )


@pytest.fixture
def subscription(company: Company) -> Subscription:
    now = timezone.now()
    return Subscription.all_objects.create(
        company=company,
        status=Subscription.Status.ACTIVE,
        price_per_operator_uzs=PRICE,
        current_period_start=now - timedelta(days=30),
        current_period_end=now,
    )


def make_operators(company: Company, count: int, *, active: bool = True) -> list[OperatorProfile]:
    created = []
    start = OperatorProfile.all_objects.filter(company=company).count()
    for i in range(start, start + count):
        user = User.objects.create_user(username=f"op{i}@{company.slug}", company=company)
        created.append(
            OperatorProfile.all_objects.create(
                company=company, user=user, user_name=f"op{i}", is_active=active
            )
        )
    return created
