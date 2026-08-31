"""Fixtures: the five roles + integrators + bound companies."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing.models import PricingSetting, Subscription
from apps.companies.models import Company
from apps.partners import services
from apps.partners.models import (
    ROLE_INTEGRATOR,
    ROLE_PLATFORM_ADMIN,
    ROLE_SUPERADMIN,
    Integrator,
    PlatformSetting,
)


@pytest.fixture(autouse=True)
def _pricing(db: Any) -> None:
    PricingSetting.objects.create(price_per_operator_uzs=50000, trial_days=14)
    PlatformSetting.objects.create(min_payout_uzs=1000)  # low min for tests


@pytest.fixture
def superadmin(db: Any) -> User:
    return User.objects.create_user(
        username="root@platform.uz",
        email="root@platform.uz",
        role=services.get_platform_role(ROLE_SUPERADMIN),
    )


@pytest.fixture
def platform_admin(db: Any) -> User:
    return User.objects.create_user(
        username="staff@platform.uz",
        email="staff@platform.uz",
        role=services.get_platform_role(ROLE_PLATFORM_ADMIN),
    )


def make_integrator(tag: str, *, override: str | None = None) -> Integrator:
    user = User.objects.create_user(
        username=f"{tag}@partners",
        email=f"{tag}@partners.uz",
        role=services.get_platform_role(ROLE_INTEGRATOR),
    )
    return Integrator.objects.create(
        user=user,
        name=f"Integrator {tag}",
        cashback_percent_override=override,
        referral_code=f"REF{tag.upper()[:5]}",
    )


@pytest.fixture
def integrator(db: Any) -> Integrator:
    return make_integrator("alpha")


@pytest.fixture
def integrator_override(db: Any) -> Integrator:
    return make_integrator("beta", override="15.00")


def make_company(slug: str, *, integrator: Integrator | None = None) -> Company:
    company = Company(
        name=f"Co {slug}",
        slug=slug,
        status=Company.Status.ACTIVE,
        integrator=integrator,
        acquired_via=Company.AcquiredVia.REFERRAL_LINK
        if integrator
        else Company.AcquiredVia.SELF_SIGNUP,
    )
    company.save()
    Subscription.all_objects.create(
        company=company, status=Subscription.Status.ACTIVE, price_per_operator_uzs=50000
    )
    return company


@pytest.fixture
def bound_company(integrator: Integrator) -> Company:
    return make_company("bound-co", integrator=integrator)


@pytest.fixture
def company_admin(bound_company: Company) -> User:
    return User.objects.create_user(
        username="boss@bound-co",
        email="boss@bound-co.uz",
        company=bound_company,
        is_company_admin=True,
    )


@pytest.fixture
def company_user(bound_company: Company) -> User:
    return User.objects.create_user(
        username="member@bound-co", company=bound_company, is_company_admin=False
    )


def client_for(user: User | None) -> APIClient:
    api = APIClient()
    if user is not None:
        api.force_authenticate(user=user)
    return api
