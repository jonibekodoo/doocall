"""Shared fixtures for the /api/call/v1 contract tests.

The operator fixture uses the LITERAL credentials from backend-api-docs.md
(``operator1`` / ``••••••••`` / api_key ``b7e2f1c9-....``) so the example
payloads from the contract replay byte-for-byte.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, SimCard, User
from apps.api import storage
from apps.calls.models import Contact, ContactPhone
from apps.companies.models import Company

DOC_USERNAME = "operator1"
DOC_PASSWORD = "••••••••"  # noqa: S105 - literal masked example from the contract
DOC_API_KEY = "b7e2f1c9-...."


@pytest.fixture(autouse=True)
def _isolated_cache_and_throttles(settings: Any) -> None:
    """Fresh locmem cache per test → throttle counters can never leak."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": uuid.uuid4().hex,
        }
    }
    settings.MINIO_PUBLIC_ENDPOINT = ""  # presign against the in-network endpoint


@pytest.fixture(autouse=True)
def _fresh_storage_clients() -> None:
    storage.client.cache_clear()
    storage.presign_client.cache_clear()


@pytest.fixture
def company(db: Any) -> Company:
    return Company.objects.create(name="Acme LLC", slug="acme", status=Company.Status.ACTIVE)


@pytest.fixture
def operator(company: Company) -> OperatorProfile:
    user = User.objects.create_user(
        username="operator1@acme", password=DOC_PASSWORD, company=company
    )
    profile = OperatorProfile.all_objects.create(
        company=company,
        user=user,
        user_name=DOC_USERNAME,
        api_key=DOC_API_KEY,
        full_name="Jonibek Yorqulov",
    )
    SimCard.all_objects.create(
        company=company, operator=profile, sim_slot=0, number="+998998887766"
    )
    return profile


@pytest.fixture
def contact_aziz(company: Company) -> Contact:
    """Backend contact catalogue entry matching the §5.1 counterparty."""
    contact = Contact.all_objects.create(company=company, name="Aziz Karimov (Mijoz)")
    ContactPhone.objects.create(contact=contact, number="+998901234567")
    return contact


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Capture uploads instead of hitting MinIO (contract tests stay unit-fast)."""
    stored: dict[str, bytes] = {}

    def _store(object_key: str, payload: bytes, filename: str) -> str:
        stored[object_key] = payload
        return f"https://minio.test/doocall-recordings/{object_key}?X-Amz-Signature=test"

    monkeypatch.setattr(storage, "store_audio", _store)
    return stored
