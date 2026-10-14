"""``fix_phone_code`` management command: dry-run vs --apply."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.accounts.models import OperatorProfile, SimCard, User
from apps.calls.models import CallRecord, Contact, ContactPhone
from apps.companies.models import Company
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(db: Any) -> dict[str, Any]:
    tj = Company.objects.create(name="Qayroqum", slug="qayroqum", phone_code="992")
    other = Company.objects.create(name="Tashkent", slug="tash")
    user = User.objects.create_user(username="op@qayroqum", company=tj)
    op = OperatorProfile.all_objects.create(company=tj, user=user, user_name="op")
    SimCard.all_objects.create(company=tj, operator=op, sim_slot=0, number="+998931112233")
    for company, call_id in ((tj, "c1"), (other, "c2")):
        CallRecord.all_objects.create(
            company=company,
            call_id=call_id,
            call_type="inbound",
            call_status="answered",
            from_number="+998921234567",
            to_number="+998931112233",
            operator_number="+998931112233",
            counterparty_number="+998921234567",
            duration=5,
            start_time=timezone.now(),
        )
    CallRecord.all_objects.filter(call_id="c1").update(to_number="+99893111223")  # 8 digits
    contact = Contact.all_objects.create(company=tj, name="A")
    ContactPhone.objects.create(contact=contact, number="+998921234567")
    dup = Contact.all_objects.create(company=tj, name="B")
    ContactPhone.objects.create(contact=dup, number="+998941234567")
    ContactPhone.objects.create(contact=dup, number="+992941234567")  # conflict target
    return {"tj": tj, "other": other, "contact": contact, "dup": dup}


def _run(*extra: str) -> str:
    out = StringIO()
    call_command(
        "fix_phone_code",
        "--company",
        "qayroqum",
        "--from",
        "998",
        "--to",
        "992",
        *extra,
        stdout=out,
    )
    return out.getvalue()


def test_dry_run_reports_and_writes_nothing(world: dict[str, Any]) -> None:
    output = _run()
    assert "DRY-RUN" in output
    assert "CallRecord.counterparty_number: 1" in output
    assert "CallRecord.to_number: 0" in output  # wrong length is left alone
    assert "SimCard.number: 1" in output
    assert "ContactPhone.number: 1" in output and "ContactPhone.conflicts: 1" in output
    assert "+998921234567 → +992921234567" in output
    assert CallRecord.all_objects.get(call_id="c1").counterparty_number == "+998921234567"
    assert not AuditLog.objects.filter(action="maintenance.phone_code_rewritten").exists()


def test_apply_rewrites_only_that_company(world: dict[str, Any]) -> None:
    output = _run("--apply")
    assert "applied" in output
    mine = CallRecord.all_objects.get(call_id="c1")
    assert mine.from_number == "+992921234567"
    assert mine.counterparty_number == "+992921234567"
    assert mine.operator_number == "+992931112233"
    assert mine.to_number == "+99893111223"  # not national length → untouched
    theirs = CallRecord.all_objects.get(call_id="c2")
    assert theirs.counterparty_number == "+998921234567"
    assert SimCard.all_objects.get(company=world["tj"]).number == "+992931112233"
    assert list(world["contact"].phones.values_list("number", flat=True)) == ["+992921234567"]
    # Conflict kept as-is instead of violating uniq_phone_per_contact.
    assert set(world["dup"].phones.values_list("number", flat=True)) == {
        "+998941234567",
        "+992941234567",
    }
    log = AuditLog.objects.get(action="maintenance.phone_code_rewritten")
    assert log.company == world["tj"] and log.changes["counts"]["ContactPhone.conflicts"] == 1


def test_rejects_unknown_codes(world: dict[str, Any]) -> None:
    with pytest.raises(CommandError):
        call_command("fix_phone_code", "--company", "qayroqum", "--from", "49", "--to", "992")
    with pytest.raises(CommandError):
        call_command("fix_phone_code", "--company", "nope", "--from", "998", "--to", "992")
