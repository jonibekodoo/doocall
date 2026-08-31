"""Contacts CRUD, multi-phone, responsible, create-from-call linking."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, User
from apps.calls.models import CallRecord, Contact
from apps.companies.models import Company

from .fixture_calls import N1, seed_fixture_calls

pytestmark = pytest.mark.django_db

URL = "/api/web/v1/contacts"


class TestContactsCrud:
    def test_create_with_phones_normalized(
        self, client: APIClient, company: Company, admin_user: User
    ) -> None:
        response = client.post(
            URL,
            {
                "name": "Alisher Umarov",
                "phones": ["901234567", "+998931112233", "90 123-45-67"],
                "note": "VIP",
                "responsible_id": admin_user.pk,
            },
            format="json",
        )
        assert response.status_code == 201
        body = response.json()["contact"]
        # Normalized + deduplicated ("901234567" == "90 123-45-67").
        assert body["phones"] == ["+998901234567", "+998931112233"]
        assert body["responsible_id"] == admin_user.pk

    def test_search_by_name_and_phone(self, client: APIClient, company: Company) -> None:
        client.post(URL, {"name": "Gulnora", "phones": ["911110001"]}, format="json")
        client.post(URL, {"name": "Rustam", "phones": ["911110002"]}, format="json")

        assert client.get(f"{URL}?q=gulnora").json()["count"] == 1
        assert client.get(f"{URL}?q=911110002").json()["count"] == 1
        assert client.get(f"{URL}?q=nothing").json()["count"] == 0

    def test_update_and_delete(self, client: APIClient, company: Company) -> None:
        contact_id = client.post(
            URL, {"name": "Old Name", "phones": ["911110009"]}, format="json"
        ).json()["contact"]["id"]

        updated = client.put(
            f"{URL}/{contact_id}",
            {"name": "New Name", "phones": ["911110009", "935556677"]},
            format="json",
        ).json()["contact"]
        assert updated["name"] == "New Name"
        assert len(updated["phones"]) == 2

        assert client.delete(f"{URL}/{contact_id}").json()["success"]
        assert client.get(f"{URL}/{contact_id}").status_code == 404

    def test_missing_name_400(self, client: APIClient, company: Company) -> None:
        assert client.post(URL, {"phones": ["901112233"]}, format="json").status_code == 400


class TestContactDetailWithHistory:
    def test_call_history_by_e164_match(
        self,
        client: APIClient,
        company: Company,
        op_a: OperatorProfile,
        op_b: OperatorProfile,
    ) -> None:
        seed_fixture_calls(company, op_a, op_b)
        contact_id = client.post(URL, {"name": "Client One", "phones": [N1]}, format="json").json()[
            "contact"
        ]["id"]

        body = client.get(f"{URL}/{contact_id}").json()
        assert len(body["calls"]) == 8  # N1 appears in 8 fixture calls
        assert all(c["counterparty_number"] == N1 for c in body["calls"])


class TestContactFromCall:
    def test_prefills_and_links_past_calls(
        self,
        client: APIClient,
        company: Company,
        op_a: OperatorProfile,
        op_b: OperatorProfile,
    ) -> None:
        seed_fixture_calls(company, op_a, op_b)
        record = CallRecord.all_objects.get(call_id="fx-1")  # N1 inbound

        response = client.post(
            f"{URL}/from-call/{record.pk}", {"name": "Linked Client"}, format="json"
        )
        assert response.status_code == 201
        body = response.json()
        assert body["contact"]["phones"] == [N1]
        assert body["linked_calls"] == 8  # all N1 history now carries the name

        refreshed = CallRecord.all_objects.get(call_id="fx-11")
        assert refreshed.resolved_name == "Linked Client"

        # Mobile upload for N1 now resolves the catalogue name (§5.4 path).
        contact = Contact.all_objects.get(pk=body["contact"]["id"])
        assert contact.company_id == company.pk

    def test_duplicate_number_409(
        self,
        client: APIClient,
        company: Company,
        op_a: OperatorProfile,
        op_b: OperatorProfile,
    ) -> None:
        seed_fixture_calls(company, op_a, op_b)
        record = CallRecord.all_objects.get(call_id="fx-1")
        assert client.post(f"{URL}/from-call/{record.pk}", {}, format="json").status_code == 201
        assert client.post(f"{URL}/from-call/{record.pk}", {}, format="json").status_code == 409
