"""Remote Dial fixtures: company, operators with devices, cabinet clients,
in-memory channel layer + locmem cache (fresh per test)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Device, OperatorProfile, User
from apps.companies.models import Company


@pytest.fixture(autouse=True)
def _isolated_layers(settings: Any) -> None:
    from channels.layers import channel_layers

    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": uuid.uuid4().hex,
        }
    }
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    channel_layers.backends = {}


@pytest.fixture
def company(db: Any) -> Company:
    return Company.objects.create(name="Dial Co", slug="dial-co", status=Company.Status.ACTIVE)


def make_operator(company: Company, name: str, device_id: str) -> OperatorProfile:
    user = User.objects.create_user(username=f"{name}@{company.slug}", company=company)
    op = OperatorProfile.all_objects.create(
        company=company,
        user=user,
        user_name=name,
        full_name=name.title(),
        api_key=f"key-{name}-{company.pk}",
    )
    Device.all_objects.create(
        company=company, operator=op, device_id=device_id, manufacturer="Samsung", model="A54"
    )
    return op


@pytest.fixture
def op_a(company: Company) -> OperatorProfile:
    return make_operator(company, "ali", "aaaa1111bbbb2222")


@pytest.fixture
def op_b(company: Company) -> OperatorProfile:
    return make_operator(company, "vali", "cccc3333dddd4444")


@pytest.fixture
def admin(company: Company) -> User:
    return User.objects.create_user(
        username="boss@dial-co.uz", email="boss@dial-co.uz", company=company, is_company_admin=True
    )


@pytest.fixture
def admin_client(admin: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=admin)
    return api


def client_for(user: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api
