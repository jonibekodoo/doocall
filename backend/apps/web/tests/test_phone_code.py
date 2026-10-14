"""Per-company phone_code: account settings + cabinet number normalization."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.calls.models import ContactPhone
from apps.companies.models import Company

pytestmark = pytest.mark.django_db

ACCOUNT = "/api/web/v1/settings/account"


def test_get_returns_phone_code(client: APIClient) -> None:
    assert client.get(ACCOUNT).json()["settings"]["phone_code"] == "998"


def test_country_change_sets_phone_code_from_map(client: APIClient, company: Company) -> None:
    body = client.put(ACCOUNT, {"country": "TJ"}, format="json").json()["settings"]
    assert body["country"] == "TJ" and body["phone_code"] == "992"
    company.refresh_from_db()
    assert company.phone_code == "992"


def test_unknown_country_keeps_phone_code(client: APIClient, company: Company) -> None:
    client.put(ACCOUNT, {"country": "TJ"}, format="json")
    client.put(ACCOUNT, {"country": "ZZ"}, format="json")
    company.refresh_from_db()
    assert company.country == "ZZ" and company.phone_code == "992"


def test_explicit_phone_code_wins_over_country(client: APIClient, company: Company) -> None:
    client.put(ACCOUNT, {"country": "TJ", "phone_code": "+996"}, format="json")
    company.refresh_from_db()
    assert company.country == "TJ" and company.phone_code == "996"


@pytest.mark.parametrize("bad", ["", "12345", "9a", "abc", None, "٩٩٢"])
def test_invalid_phone_code_400(client: APIClient, company: Company, bad: object) -> None:
    response = client.put(ACCOUNT, {"phone_code": bad}, format="json")
    assert response.status_code == 400
    company.refresh_from_db()
    assert company.phone_code == "998"


def test_contacts_use_company_code(client: APIClient, company: Company) -> None:
    company.phone_code = "992"  # the authenticated user's company instance
    company.save()
    response = client.post(
        "/api/web/v1/contacts",
        {"name": "Dushanbe client", "phones": ["92 123 45 67", "+998901234567"]},
        format="json",
    )
    assert response.status_code in (200, 201), response.content
    numbers = set(ContactPhone.objects.values_list("number", flat=True))
    assert numbers == {"+992921234567", "+998901234567"}
    found = client.get("/api/web/v1/contacts", {"q": "921234567"}).json()
    assert [c["name"] for c in found["results"]] == ["Dushanbe client"]
