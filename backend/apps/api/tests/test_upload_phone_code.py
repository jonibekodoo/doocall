"""Device API in a non-Uzbek company: numbers use Company.phone_code."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, SimCard
from apps.calls.models import CallRecord
from apps.companies.models import Company

from .conftest import DOC_PASSWORD, DOC_USERNAME
from .test_upload_contract import UPLOAD_URL, doc_payload

pytestmark = pytest.mark.django_db


@pytest.fixture
def tj_company(company: Company) -> Company:
    Company.objects.filter(pk=company.pk).update(country="TJ", phone_code="992")
    company.refresh_from_db()
    return company


def test_upload_normalizes_with_company_code(
    client: APIClient,
    operator: OperatorProfile,
    tj_company: Company,
    fake_storage: dict[str, bytes],
) -> None:
    response = client.post(
        UPLOAD_URL,
        doc_payload(
            call_id="tj-1",
            **{"from": "921234567"},
            to="992931112233",
            operator_number="0931112233",
            counterparty_number="92 123 45 67",
        ),
        format="json",
    )
    assert response.status_code == 200, response.content
    record = CallRecord.all_objects.get(call_id="tj-1")
    assert record.from_number == "+992921234567"
    assert record.to_number == "+992931112233"
    assert record.operator_number == "+992931112233"
    assert record.counterparty_number == "+992921234567"


def test_device_prefixed_numbers_are_not_rewritten(
    client: APIClient,
    operator: OperatorProfile,
    tj_company: Company,
    fake_storage: dict[str, bytes],
) -> None:
    # The shipped app prefixes +998 itself — the server keeps "+" numbers.
    client.post(
        UPLOAD_URL,
        doc_payload(call_id="tj-2", counterparty_number="+998921234567"),
        format="json",
    )
    assert CallRecord.all_objects.get(call_id="tj-2").counterparty_number == "+998921234567"


def test_auth_returns_phone_code_and_normalizes_sims(
    client: APIClient, operator: OperatorProfile, tj_company: Company
) -> None:
    response = client.post(
        "/api/call/v1/auth",
        {
            "username": DOC_USERNAME,
            "password": DOC_PASSWORD,
            "phone_numbers": [{"sim_slot": 1, "number": "931112233"}],
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["phone_code"] == "992"
    assert SimCard.all_objects.get(operator=operator, sim_slot=1).number == "+992931112233"
