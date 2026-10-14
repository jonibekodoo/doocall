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


# The app sends numbers exactly as dialled/typed; the server alone adds the
# country code. (raw, stored in a UZ company, stored in a TJ company)
RAW_CASES = [
    ("901234567", "+998901234567", "+992901234567"),
    ("921234567", "+998921234567", "+992921234567"),
    ("992921234567", "+992921234567", "+992921234567"),
    ("+998901234567", "+998901234567", "+998901234567"),  # dialled internationally
    ("0921234567", "0921234567", "+992921234567"),  # trunk 0: TJ only
    ("90 123-45-67", "+998901234567", "+992901234567"),
    # Shorter than the national length: local landline / short codes — the
    # server can't know the area code, so they are stored cleaned, unprefixed.
    ("2212345", "2212345", "2212345"),
    ("221-23-45", "2212345", "2212345"),
    ("1234", "1234", "1234"),
    ("*100#", "*100#", "*100#"),
]


@pytest.mark.parametrize("country", ["UZ", "TJ"])
@pytest.mark.parametrize(("raw", "uz", "tj"), RAW_CASES, ids=[c[0] for c in RAW_CASES])
def test_every_upload_number_field_uses_company_code(
    client: APIClient,
    operator: OperatorProfile,
    company: Company,
    fake_storage: dict[str, bytes],
    country: str,
    raw: str,
    uz: str,
    tj: str,
) -> None:
    if country == "TJ":
        Company.objects.filter(pk=company.pk).update(country="TJ", phone_code="992")
    response = client.post(
        UPLOAD_URL,
        doc_payload(
            call_id=f"raw-{country}",
            **{"from": raw},
            to=raw,
            operator_number=raw,
            counterparty_number=raw,
        ),
        format="json",
    )
    assert response.status_code == 200, response.content
    record = CallRecord.all_objects.get(call_id=f"raw-{country}")
    expected = tj if country == "TJ" else uz
    assert record.from_number == expected
    assert record.to_number == expected
    assert record.operator_number == expected
    assert record.counterparty_number == expected


@pytest.mark.parametrize("country", ["UZ", "TJ"])
def test_auth_sim_numbers_use_company_code(
    client: APIClient, operator: OperatorProfile, company: Company, country: str
) -> None:
    if country == "TJ":
        Company.objects.filter(pk=company.pk).update(country="TJ", phone_code="992")
    response = client.post(
        "/api/call/v1/auth",
        {
            "username": DOC_USERNAME,
            "password": DOC_PASSWORD,
            "phone_numbers": [
                {"sim_slot": 0, "number": "921234567"},
                {"sim_slot": 1, "number": "2212345"},
            ],
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["phone_code"] == ("992" if country == "TJ" else "998")
    sims = dict(SimCard.all_objects.filter(operator=operator).values_list("sim_slot", "number"))
    assert sims == {0: "+992921234567" if country == "TJ" else "+998921234567", 1: "2212345"}
