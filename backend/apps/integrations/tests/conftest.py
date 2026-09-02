"""Integration app fixtures: company + admin client + a call with audio."""

from __future__ import annotations

from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, User
from apps.calls.models import CallAudio, CallRecord
from apps.companies.models import Company


@pytest.fixture
def company(db: Any) -> Company:
    return Company.objects.create(
        name="Integr Co",
        slug="integr-co",
        status=Company.Status.ACTIVE,
        api_key="companykey123456",
    )


@pytest.fixture
def admin_user(company: Company) -> User:
    return User.objects.create_user(
        username="admin@integr-co.uz",
        email="admin@integr-co.uz",
        password="integr-admin-1",
        company=company,
        is_company_admin=True,
    )


@pytest.fixture
def client(admin_user: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=admin_user)
    return api


@pytest.fixture
def operator(company: Company) -> OperatorProfile:
    user = User.objects.create_user(username="op-1@integr-co", company=company)
    return OperatorProfile.all_objects.create(
        company=company, user=user, user_name="op-1", full_name="Op One"
    )


@pytest.fixture
def call(company: Company, operator: OperatorProfile) -> CallRecord:
    record = CallRecord.all_objects.create(
        company=company,
        operator=operator,
        call_id="c-1",
        call_type="inbound",
        call_status="answered",
        from_number="+998901112233",
        to_number="+998907654321",
        counterparty_number="+998901112233",
        duration=65,
        start_time=timezone.now(),
    )
    CallAudio.objects.create(
        call=record,
        kind=CallAudio.Kind.PRIMARY,
        filename="rec.ogg",
        object_key=f"{company.pk}/c-1/primary/rec.ogg",
    )
    return record
