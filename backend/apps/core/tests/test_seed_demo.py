"""seed_demo: creates expected counts and is idempotent (reset-and-rebuild)."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import Device, OperatorProfile, SimCard
from apps.calls.models import CallRecord, Contact
from apps.companies.models import Company

pytestmark = pytest.mark.django_db

N_CALLS = 400  # small but statistically meaningful; full 12k run is `make seed`


def run_seed(calls: int = N_CALLS) -> str:
    out = StringIO()
    call_command("seed_demo", calls=calls, stdout=out)
    return out.getvalue()


class TestSeedDemo:
    def test_creates_expected_counts(self) -> None:
        output = run_seed()

        company = Company.objects.get(slug="ahlan-house")
        assert company.name == "Ahlan House"
        assert OperatorProfile.all_objects.filter(company=company).count() == 6
        assert Device.all_objects.filter(company=company).count() == 6
        # 6 operators, every second one dual-SIM → 9 SIMs
        assert SimCard.all_objects.filter(company=company).count() == 9
        assert Contact.all_objects.filter(company=company).count() == 5
        assert CallRecord.all_objects.filter(company=company).count() == N_CALLS
        assert f"{N_CALLS} call records" in output

    def test_realistic_status_and_type_mix(self) -> None:
        run_seed()
        company = Company.objects.get(slug="ahlan-house")
        calls = CallRecord.all_objects.filter(company=company)

        answered = calls.filter(call_status="answered").count() / N_CALLS
        inbound = calls.filter(call_type="inbound").count() / N_CALLS
        assert 0.55 < answered < 0.8, "answered ratio should be ~68%"
        assert 0.45 < inbound < 0.65, "inbound ratio should be ~55%"
        # Missed calls have zero duration; answered have positive.
        assert not calls.filter(call_status="no_answer", duration__gt=0).exists()
        assert not calls.filter(call_status="answered", duration=0).exists()

    def test_idempotent_by_reset(self) -> None:
        run_seed()
        first_ids = set(
            CallRecord.all_objects.filter(company__slug="ahlan-house").values_list("id", flat=True)
        )
        run_seed()  # second run must rebuild, not duplicate
        assert Company.objects.filter(slug="ahlan-house").count() == 1
        second = CallRecord.all_objects.filter(company__slug="ahlan-house")
        assert second.count() == N_CALLS
        assert first_ids.isdisjoint(set(second.values_list("id", flat=True)))
