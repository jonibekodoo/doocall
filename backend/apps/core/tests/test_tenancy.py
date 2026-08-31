"""HARD tenancy-isolation guarantees.

Company A must never see company B's calls, contacts, operators or users
through the default managers while A's tenant context is active.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import OperatorProfile, User
from apps.calls.models import CallRecord, Contact
from apps.companies.models import Company
from apps.core.tenancy import get_current_company_id, tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_tenants() -> tuple[Company, Company]:
    now = timezone.now()
    companies = []
    for label in ("a", "b"):
        company = Company.objects.create(name=f"Co {label.upper()}", slug=f"co-{label}")
        user = User.objects.create_user(username=f"user-{label}", company=company)
        operator = OperatorProfile.all_objects.create(
            company=company, user=user, user_name=f"op-{label}"
        )
        Contact.all_objects.create(company=company, name=f"Contact {label.upper()}")
        CallRecord.all_objects.create(
            company=company,
            operator=operator,
            call_id=f"call-{label}",
            call_type=CallRecord.CallType.INBOUND,
            call_status=CallRecord.CallStatus.ANSWERED,
            from_number="+998901234567",
            to_number="+998998887766",
            counterparty_number="+998901234567",
            duration=60,
            start_time=now - timedelta(hours=1),
        )
        companies.append(company)
    return companies[0], companies[1]


class TestTenantIsolation:
    def test_calls_are_isolated(self, two_tenants: tuple[Company, Company]) -> None:
        a, b = two_tenants
        with tenant_context(a):
            visible = list(CallRecord.objects.all())
            assert [c.call_id for c in visible] == ["call-a"]
            # B's record is invisible even by direct PK probing.
            assert not CallRecord.objects.filter(call_id="call-b").exists()

    def test_contacts_are_isolated(self, two_tenants: tuple[Company, Company]) -> None:
        a, b = two_tenants
        with tenant_context(b):
            names = list(Contact.objects.values_list("name", flat=True))
            assert names == ["Contact B"]

    def test_operators_and_users_are_isolated(self, two_tenants: tuple[Company, Company]) -> None:
        a, b = two_tenants
        with tenant_context(a):
            assert list(OperatorProfile.objects.values_list("user_name", flat=True)) == ["op-a"]
            assert list(User.tenant_objects.values_list("username", flat=True)) == ["user-a"]

    def test_context_nesting_and_reset(self, two_tenants: tuple[Company, Company]) -> None:
        a, b = two_tenants
        assert get_current_company_id() is None
        with tenant_context(a):
            assert get_current_company_id() == a.pk
            with tenant_context(b):
                assert CallRecord.objects.get().call_id == "call-b"
            assert CallRecord.objects.get().call_id == "call-a"
        assert get_current_company_id() is None
        # No context → unscoped (platform/admin view).
        assert CallRecord.objects.count() == 2

    def test_escape_hatch_is_explicit(self, two_tenants: tuple[Company, Company]) -> None:
        a, _ = two_tenants
        with tenant_context(a):
            # all_objects is the ONLY way to cross tenants inside a context.
            assert CallRecord.all_objects.count() == 2
            assert CallRecord.objects.count() == 1
