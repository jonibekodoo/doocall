"""``seed_demo`` v1 — demo tenant with realistic 30-day call history.

Deterministic (fixed RNG seed) and idempotent by reset: an existing
"Ahlan House" company is deleted and rebuilt from scratch on every run.

NOTE: the 6 operator names are placeholders — master spec §10 (which pins the
exact names) is not present in this repo; swap them in when it lands.
"""

from __future__ import annotations

import random
import uuid
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Device, OperatorProfile, Role, SimCard, User
from apps.billing.models import PricingSetting, Subscription
from apps.calls.models import CallRecord, Contact, ContactPhone
from apps.companies.models import Company

COMPANY_NAME = "Ahlan House"
COMPANY_SLUG = "ahlan-house"

# Placeholder names (master spec §10 not available — see module docstring).
OPERATORS = [
    ("aziz", "Aziz Karimov", "+998901112233"),
    ("malika", "Malika Tosheva", "+998902223344"),
    ("jasur", "Jasur Rahimov", "+998903334455"),
    ("nilufar", "Nilufar Azimova", "+998904445566"),
    ("bekzod", "Bekzod Ergashev", "+998905556677"),
    ("dildora", "Dildora Yusupova", "+998906667788"),
]

CONTACTS = [
    ("Alisher Umarov", ["+998911234501", "+998911234502"]),
    ("Gulnora Saidova", ["+998911234503"]),
    ("Rustam Nazarov", ["+998911234504"]),
    ("Kamola Islomova", ["+998911234505"]),
    ("Sherzod Tursunov", ["+998911234506"]),
]

DEVICE_MODELS = [
    ("Xiaomi", "Redmi Note 12"),
    ("Samsung", "Galaxy A54"),
    ("Xiaomi", "Redmi 13C"),
    ("Samsung", "Galaxy S23"),
    ("Google", "Pixel 7a"),
    ("Xiaomi", "Poco X6"),
]

BATCH_SIZE = 2000


class Command(BaseCommand):
    help = "Seed the demo tenant (Ahlan House) with operators, devices and ~12k calls."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--calls", type=int, default=12000, help="CallRecords to create")
        parser.add_argument("--days", type=int, default=30, help="History window in days")
        parser.add_argument("--seed", type=int, default=42, help="RNG seed (deterministic)")

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        rng = random.Random(options["seed"])
        n_calls: int = options["calls"]
        days: int = options["days"]
        now = timezone.now()

        # ── Reset (idempotency by rebuild) ────────────────────────────────
        deleted, _ = Company.objects.filter(slug=COMPANY_SLUG).delete()
        if deleted:
            self.stdout.write(f"Reset existing demo company ({deleted} rows cascaded).")

        # ── Platform superuser for admin access (dev convenience) ─────────
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@doocall.local", "admin")
            self.stdout.write(self.style.SUCCESS("Created superuser admin/admin (dev only)."))

        # ── Company + billing scaffolding ──────────────────────────────────
        pricing, _ = PricingSetting.objects.get_or_create(
            company=None,
            defaults={"price_per_operator_uzs": 50000, "trial_days": 14},
        )
        company = Company.objects.create(
            name=COMPANY_NAME,
            slug=COMPANY_SLUG,
            status=Company.Status.ACTIVE,
            trial_ends_at=now + timedelta(days=pricing.trial_days),
        )
        Subscription.objects.create(
            company=company,
            status=Subscription.Status.ACTIVE,
            price_per_operator_uzs=pricing.price_per_operator_uzs,
            current_period_start=now - timedelta(days=days),
            current_period_end=now + timedelta(days=30 - days % 30),
        )
        operator_role = Role.objects.create(
            company=company, name="Operator", permissions=["calls.view", "calls.upload"]
        )

        # Web cabinet admin (email login for the dashboard / E2E tests).
        User.objects.create_user(
            username="admin@ahlan.uz",
            email="admin@ahlan.uz",
            password="demo1234",
            company=company,
            is_company_admin=True,
        )

        # ── Operators, devices, SIMs ───────────────────────────────────────
        operators: list[tuple[OperatorProfile, list[SimCard]]] = []
        for i, (login, full_name, number) in enumerate(OPERATORS):
            user = User.objects.create_user(
                username=f"{login}@{COMPANY_SLUG}",
                password="demo1234",
                first_name=full_name.split()[0],
                last_name=full_name.split()[-1],
                company=company,
                role=operator_role,
            )
            profile = OperatorProfile.all_objects.create(
                company=company, user=user, user_name=login, full_name=full_name
            )
            manufacturer, model = DEVICE_MODELS[i]
            Device.all_objects.create(
                company=company,
                operator=profile,
                device_id=uuid.UUID(int=rng.getrandbits(128)).hex,
                model=model,
                manufacturer=manufacturer,
                app_version="1.0",
                os_version=rng.choice(["13", "14"]),
                last_seen_at=now - timedelta(minutes=rng.randint(1, 720)),
            )
            sims = [
                SimCard.all_objects.create(
                    company=company, operator=profile, sim_slot=0, number=number
                )
            ]
            if i % 2 == 0:  # half the operators are dual-SIM
                sims.append(
                    SimCard.all_objects.create(
                        company=company,
                        operator=profile,
                        sim_slot=1,
                        number=f"+99893{number[-7:]}",
                    )
                )
            operators.append((profile, sims))

        # ── Contacts ───────────────────────────────────────────────────────
        contact_numbers: dict[str, str] = {}
        for name, numbers in CONTACTS:
            contact = Contact.all_objects.create(company=company, name=name)
            for num in numbers:
                ContactPhone.objects.create(contact=contact, number=num)
                contact_numbers[num] = name

        # ── Call records ───────────────────────────────────────────────────
        counterparty_pool = list(contact_numbers) + [
            f"+9989{rng.choice('01234789')}{rng.randint(1000000, 9999999)}" for _ in range(800)
        ]

        records: list[CallRecord] = []
        created = 0
        for _ in range(n_calls):
            profile, sims = rng.choice(operators)
            sim = rng.choice(sims)
            counterparty = rng.choice(counterparty_pool)
            counterparty_name = contact_numbers.get(counterparty)

            call_type = (
                CallRecord.CallType.INBOUND if rng.random() < 0.55 else CallRecord.CallType.OUTBOUND
            )
            answered = rng.random() < 0.68  # realistic answer ratio
            status = CallRecord.CallStatus.ANSWERED if answered else CallRecord.CallStatus.NO_ANSWER
            duration = rng.randint(15, 600) if answered else 0

            start = now - timedelta(
                days=rng.uniform(0, days),
                hours=rng.uniform(0, 12),  # spread inside the 08:00-20:00 window
            )
            end = start + timedelta(seconds=duration)

            if call_type == CallRecord.CallType.INBOUND:
                from_number, from_name = counterparty, counterparty_name
                to_number, to_name = sim.number, profile.full_name
            else:
                from_number, from_name = sim.number, profile.full_name
                to_number, to_name = counterparty, counterparty_name

            records.append(
                CallRecord(
                    company=company,
                    operator=profile,
                    call_id=uuid.UUID(int=rng.getrandbits(128)).hex,
                    call_type=call_type,
                    call_status=status,
                    from_number=from_number,
                    from_name=from_name,
                    to_number=to_number,
                    to_name=to_name,
                    operator_number=sim.number,
                    counterparty_number=counterparty,
                    counterparty_name=counterparty_name,
                    sim_slot=sim.sim_slot,
                    duration=duration,
                    start_time=start,
                    end_time=end,
                    **(
                        {
                            "latitude": 41.311081 + rng.uniform(-0.05, 0.05),
                            "longitude": 69.240562 + rng.uniform(-0.05, 0.05),
                        }
                        if rng.random() < 0.4
                        else {}
                    ),
                )
            )
            if len(records) >= BATCH_SIZE:
                CallRecord.all_objects.bulk_create(records)
                created += len(records)
                records.clear()
                self.stdout.write(f"  … {created}/{n_calls} calls")

        if records:
            CallRecord.all_objects.bulk_create(records)
            created += len(records)

        # ── Integrators + cashback demo data (Phase 10) ────────────────────
        self._seed_partners(company, now, rng)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded '{COMPANY_NAME}': {len(operators)} operators, "
                f"{Contact.all_objects.filter(company=company).count()} contacts, "
                f"{created} call records over {days} days."
            )
        )

    def _seed_partners(self, ahlan_company: Company, now: Any, rng: random.Random) -> None:
        """Two integrators, both acquisition paths, accruals, pending payout."""
        from apps.billing import services as billing_services
        from apps.billing.models import Payment
        from apps.companies.models import Company
        from apps.partners import services as partner_services
        from apps.partners.models import Integrator, PlatformSetting

        if not PlatformSetting.objects.exists():
            PlatformSetting.objects.create()  # 10% / 12 months

        Integrator.objects.filter(referral_code__in=["DEMOINT1", "DEMOINT2"]).delete()
        User.objects.filter(username__in=["partner1@demo.uz", "partner2@demo.uz"]).delete()

        role = partner_services.get_platform_role("integrator")
        p1_user = User.objects.create_user(
            username="partner1@demo.uz",
            email="partner1@demo.uz",
            password="demo1234",
            role=role,
        )
        p1 = Integrator.objects.create(
            user=p1_user,
            name="Davron Integrator",
            referral_code="DEMOINT1",
            payout_details={"card": "8600 0000 0000 0001"},
        )
        p2_user = User.objects.create_user(
            username="partner2@demo.uz",
            email="partner2@demo.uz",
            password="demo1234",
            role=role,
        )
        p2 = Integrator.objects.create(
            user=p2_user,
            name="Sevara Integrator (15%)",
            referral_code="DEMOINT2",
            cashback_percent_override="15.00",
            payout_details={"bank": "NBU", "account": "2020 8000 0000 0000 0002"},
        )

        # Superadmin platform user for the admin portal.
        if not User.objects.filter(username="super@doocall.uz").exists():
            User.objects.create_user(
                username="super@doocall.uz",
                email="super@doocall.uz",
                password="demo1234",
                role=partner_services.get_platform_role("superadmin"),
            )

        # Bind: Ahlan House via referral to p1; one manual client for p2.
        partner_services.reassign_integrator(ahlan_company, p1, actor=p1_user)
        Company.objects.filter(slug="demo-client-co").delete()
        client_co = Company(
            name="Demo Client Co",
            slug="demo-client-co",
            status=Company.Status.ACTIVE,
            integrator=p2,
            acquired_via=Company.AcquiredVia.INTEGRATOR_MANUAL,
        )
        client_co.save()
        from apps.billing.models import Subscription

        Subscription.all_objects.create(
            company=client_co,
            status=Subscription.Status.ACTIVE,
            price_per_operator_uzs=50000,
        )

        # Payments → accruals for both, one pending payout for p1.
        for company, amount in ((ahlan_company, 600000), (client_co, 200000)):
            payment = Payment.all_objects.create(
                company=company,
                provider=rng.choice(["manual", "payme", "click"]),
                amount_uzs=amount,
            )
            billing_services.apply_payment(payment)
        partner_services.request_payout(p1, 50000, note="demo pending payout")
        self.stdout.write(
            "Seeded partners: DEMOINT1 (10%), DEMOINT2 (15% override), "
            "accruals + 1 pending payout. Logins: partner1@demo.uz, "
            "partner2@demo.uz, super@doocall.uz / demo1234"
        )
