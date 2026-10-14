"""``fix_phone_code`` — rewrite one company's numbers from one calling code to
another (e.g. a Tajik company whose local numbers were stored as +998…).

    manage.py fix_phone_code --company <slug> --from 998 --to 992 [--apply]

Only numbers that are EXACTLY ``+{from}`` followed by the national-number
length of ``--from`` (apps.core.phone.NATIONAL_LENGTH) are touched; they keep
the same digits after the code. Dry-run by default: prints per-table counts
and a sample. ``--apply`` writes everything in one transaction plus one
AuditLog row. ContactPhone rows whose rewritten number already exists on the
same contact (unique per contact) are reported as conflicts and left alone.
"""

from __future__ import annotations

import re
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Concat, Substr

from apps.accounts.models import SimCard
from apps.calls.models import CallRecord, ContactPhone
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.core.phone import NATIONAL_LENGTH

CALL_FIELDS = ("from_number", "to_number", "operator_number", "counterparty_number")
SAMPLE = 5


class Command(BaseCommand):
    help = "Rewrite a company's +<from> numbers to +<to> (dry-run unless --apply)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--company", required=True, help="company slug")
        parser.add_argument("--from", dest="from_code", required=True, help="e.g. 998")
        parser.add_argument("--to", dest="to_code", required=True, help="e.g. 992")
        parser.add_argument("--apply", action="store_true", help="write the changes")

    def handle(self, *args: Any, **options: Any) -> None:
        from_code = str(options["from_code"]).lstrip("+")
        to_code = str(options["to_code"]).lstrip("+")
        if not re.fullmatch(r"[0-9]{1,4}", to_code):
            raise CommandError("--to must be 1–4 digits")
        national = NATIONAL_LENGTH.get(from_code)
        if national is None:
            raise CommandError(f"unknown national number length for --from {from_code}")
        if from_code == to_code:
            raise CommandError("--from and --to are the same")
        company = Company.objects.filter(slug=options["company"]).first()
        if company is None:
            raise CommandError(f"company {options['company']!r} not found")

        pattern = rf"^\+{from_code}[0-9]{{{national}}}$"
        keep_from = len(from_code) + 2  # Substr is 1-based; skip "+" and the code

        def rewrite(number: str) -> str:
            return f"+{to_code}{number[len(from_code) + 1 :]}"

        apply = bool(options["apply"])
        counts: dict[str, int] = {}
        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"{mode}: {company.slug} +{from_code} → +{to_code} ({national} digits)")

        with transaction.atomic():
            # ── Call records: four number columns ─────────────────────────
            calls = CallRecord.all_objects.filter(company=company)
            for field in CALL_FIELDS:
                qs = calls.filter(**{f"{field}__regex": pattern})
                counts[f"CallRecord.{field}"] = qs.count()
                self._sample(f"CallRecord.{field}", qs.values_list(field, flat=True), rewrite)
                if apply:
                    qs.update(**{field: Concat(Value(f"+{to_code}"), Substr(field, keep_from))})

            # ── SIM cards (unique per operator+slot, number is free) ───────
            sims = SimCard.all_objects.filter(company=company, number__regex=pattern)
            counts["SimCard.number"] = sims.count()
            self._sample("SimCard.number", sims.values_list("number", flat=True), rewrite)
            if apply:
                sims.update(number=Concat(Value(f"+{to_code}"), Substr("number", keep_from)))

            # ── Contact phones (unique per contact+number → conflicts) ─────
            phones = ContactPhone.objects.filter(
                contact__company=company, number__regex=pattern
            ).order_by("pk")
            changed = conflicts = 0
            for phone in phones:
                target = rewrite(phone.number)
                if ContactPhone.objects.filter(contact_id=phone.contact_id, number=target).exists():
                    conflicts += 1
                    self.stdout.write(
                        f"  conflict: contact {phone.contact_id} already has {target}"
                        f" (kept {phone.number})"
                    )
                    continue
                if changed < SAMPLE:
                    self.stdout.write(f"  ContactPhone.number: {phone.number} → {target}")
                changed += 1
                if apply:
                    phone.number = target
                    phone.save(update_fields=["number"])
            counts["ContactPhone.number"] = changed
            counts["ContactPhone.conflicts"] = conflicts

            for name, count in counts.items():
                self.stdout.write(f"{name}: {count}")

            if apply:
                AuditLog.objects.create(
                    company=company,
                    action="maintenance.phone_code_rewritten",
                    target_model="companies.Company",
                    target_id=str(company.pk),
                    changes={"from": from_code, "to": to_code, "counts": counts},
                )
                self.stdout.write(self.style.SUCCESS("applied"))
            else:
                self.stdout.write("dry-run: nothing written (use --apply)")

    def _sample(self, label: str, numbers: Any, rewrite: Any) -> None:
        for number in numbers[:SAMPLE]:
            self.stdout.write(f"  {label}: {number} → {rewrite(number)}")
