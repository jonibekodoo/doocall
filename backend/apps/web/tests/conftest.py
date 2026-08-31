"""Cabinet test fixtures: company + admin JWT user + operators + noise tenant."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, User
from apps.billing.models import PricingSetting, Subscription
from apps.companies.models import Company


@pytest.fixture(autouse=True)
def _pricing(db: Any) -> PricingSetting:
    return PricingSetting.objects.create(price_per_operator_uzs=50000, trial_days=14)


@pytest.fixture
def company(db: Any) -> Company:
    company = Company.objects.create(
        name="Cabinet Co", slug="cabinet-co", status=Company.Status.ACTIVE
    )
    Subscription.all_objects.create(
        company=company,
        status=Subscription.Status.ACTIVE,
        price_per_operator_uzs=50000,
    )
    return company


@pytest.fixture
def admin_user(company: Company) -> User:
    return User.objects.create_user(
        username="admin@cabinet-co",
        email="admin@cabinet-co.uz",
        password="cabinet-admin-1",
        company=company,
        is_company_admin=True,
    )


@pytest.fixture
def member_user(company: Company) -> User:
    return User.objects.create_user(
        username="member@cabinet-co",
        email="member@cabinet-co.uz",
        password="cabinet-member-1",
        company=company,
        is_company_admin=False,
    )


@pytest.fixture
def op_a(company: Company) -> OperatorProfile:
    user = User.objects.create_user(username="op-a@cabinet-co", company=company)
    return OperatorProfile.all_objects.create(
        company=company, user=user, user_name="op-a", full_name="Operator A"
    )


@pytest.fixture
def op_b(company: Company) -> OperatorProfile:
    user = User.objects.create_user(username="op-b@cabinet-co", company=company)
    return OperatorProfile.all_objects.create(
        company=company, user=user, user_name="op-b", full_name="Operator B"
    )


@pytest.fixture
def client(admin_user: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=admin_user)
    return api


@pytest.fixture
def member_client(member_user: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=member_user)
    return api


@pytest.fixture
def other_company_noise(db: Any) -> Company:
    """A second tenant with data that must NEVER appear in Cabinet Co results."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.calls.models import CallRecord

    other = Company.objects.create(name="Noise Co", slug="noise-co")
    user = User.objects.create_user(username="noise-op@noise-co", company=other)
    operator = OperatorProfile.all_objects.create(company=other, user=user, user_name="noise-op")
    for i in range(5):
        CallRecord.all_objects.create(
            company=other,
            operator=operator,
            call_id=f"noise-{i}",
            call_type="inbound",
            call_status="answered",
            from_number="+998900000001",
            to_number="+998900000002",
            counterparty_number="+998900000001",
            duration=999,
            start_time=timezone.now() - timedelta(hours=i),
        )
    return other
