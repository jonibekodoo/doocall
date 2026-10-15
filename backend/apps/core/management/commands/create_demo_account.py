"""``create_demo_account`` — ONE production-safe demo tenant for showing the
reports (dashboard, Hisobotlar) to prospects.

Unlike ``seed_demo`` (dev only) this command never creates superusers,
platform users or integrators, never touches any company other than the one
it owns, and never uses a known password: the cabinet admin gets a random
password that is printed once to stdout and stored nowhere else.

The company is marked ``feature_flags["demo"] = True``; billing skips it
(no daily charges → never suspended or warned) and the admin dashboard KPIs
exclude it — see ``apps.billing.services.demo_q``.

Usage::

    python manage.py create_demo_account                 # slug "demo"
    python manage.py create_demo_account --reset         # rebuild (demo only)
    python manage.py create_demo_account --slug acme-demo --name "Acme demo" \\
        --email demo@acme.uz --operators 8 --calls 5000 --days 60 --seed 7
"""

from __future__ import annotations

import math
import random
import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Device, OperatorProfile, Role, SimCard, User
from apps.billing.services import DEMO_FLAG, is_demo
from apps.calls.models import CallAudio, CallRecord, Contact, ContactPhone
from apps.companies.models import Company
from apps.core.models import AuditLog

TIMEZONE = "Asia/Tashkent"
BATCH_SIZE = 2000
MAX_CALLS = 200_000
MAX_DAYS = 365
TASHKENT = (41.311081, 69.240562)

# (login, full name, activity weight, answer rate, inbound share, median talk s)
# — distinct per-operator profiles so the operator reports differ visibly.
OPERATORS = [
    ("aziz", "Aziz Karimov", 1.45, 0.82, 0.60, 140),
    ("malika", "Malika Tosheva", 1.25, 0.88, 0.70, 110),
    ("jasur", "Jasur Rahimov", 1.10, 0.74, 0.40, 190),
    ("nilufar", "Nilufar Azimova", 1.00, 0.79, 0.55, 95),
    ("bekzod", "Bekzod Ergashev", 0.80, 0.66, 0.35, 230),
    ("dildora", "Dildora Yusupova", 0.65, 0.85, 0.65, 80),
    ("sardor", "Sardor Qodirov", 0.95, 0.71, 0.50, 160),
    ("madina", "Madina Xolmatova", 0.90, 0.80, 0.60, 120),
    ("otabek", "Otabek Mirzayev", 0.75, 0.69, 0.45, 175),
    ("zarina", "Zarina Ahmedova", 0.70, 0.84, 0.58, 100),
    ("shoxrux", "Shoxrux Aliyev", 0.60, 0.73, 0.42, 150),
    ("feruza", "Feruza Nazarova", 0.55, 0.81, 0.62, 90),
]

CONTACT_NAMES = [
    "Alisher Umarov",
    "Gulnora Saidova",
    "Rustam Nazarov",
    "Kamola Islomova",
    "Sherzod Tursunov",
    "Dilnoza Rahimova",
    "Javohir Sobirov",
    "Nodira Qosimova",
    "Ulug'bek Hamidov",
    "Mohira Abdullayeva",
    "Farrux Jo'rayev",
    "Sevara Ismoilova",
    "Bobur Toshmatov",
    "Shahnoza Ergasheva",
    "Akmal Yo'ldoshev",
    "Lola Karimova",
    "Doniyor Rasulov",
    "Nargiza Mamatova",
    "Islom Xudoyberdiyev",
    "Barno Sultonova",
    "Temur Usmonov",
    "Gulchehra Valiyeva",
    "Anvar Po'latov",
    "Ziyoda Raximova",
    "Elyor Murodov",
    "Hilola Tojiyeva",
    "Sanjar Boboyev",
    "Munisa G'aniyeva",
    '"Orient Trade" MChJ',
    '"Baraka Qurilish" MChJ',
]

DEVICE_MODELS = [
    ("Xiaomi", "Redmi Note 12"),
    ("Samsung", "Galaxy A54"),
    ("Xiaomi", "Redmi 13C"),
    ("Samsung", "Galaxy S23"),
    ("Google", "Pixel 7a"),
    ("Xiaomi", "Poco X6"),
    ("Samsung", "Galaxy A34"),
    ("Honor", "X8b"),
    ("Tecno", "Spark 20"),
    ("Xiaomi", "Redmi 12"),
    ("Samsung", "Galaxy A15"),
    ("Vivo", "Y36"),
]

# Local-hour weights: the working day peaks 10–12 and 14–17, quiet lunch.
HOUR_WEIGHTS = {
    8: 2,
    9: 6,
    10: 9,
    11: 10,
    12: 7,
    13: 6,
    14: 9,
    15: 10,
    16: 9,
    17: 8,
    18: 5,
    19: 3,
    20: 1,
}
# Monday … Sunday.
WEEKDAY_WEIGHTS = [1.0, 1.0, 0.95, 1.0, 0.9, 0.5, 0.2]

UZ_PREFIXES = ["90", "91", "93", "94", "95", "97", "98", "99", "33", "88", "77"]


def _uz_number(rng: random.Random) -> str:
    return f"+998{rng.choice(UZ_PREFIXES)}{rng.randint(1_000_000, 9_999_999)}"


class Command(BaseCommand):
    help = "Create (or --reset) ONE production-safe demo company with realistic calls."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--slug", default="demo")
        parser.add_argument("--name", default="Demo kompaniya")
        parser.add_argument("--email", default="demo@doocall.uz", help="cabinet admin login")
        parser.add_argument("--operators", type=int, default=6)
        parser.add_argument("--calls", type=int, default=3000)
        parser.add_argument("--days", type=int, default=30, help="history window")
        parser.add_argument("--seed", type=int, default=42, help="RNG seed for the data")
        parser.add_argument(
            "--reset",
            action="store_true",
            help="delete and rebuild the company — only if it is marked demo",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        slug: str = opts["slug"].strip()
        name: str = opts["name"].strip()
        email: str = opts["email"].strip().lower()
        n_ops: int = opts["operators"]
        n_calls: int = opts["calls"]
        days: int = opts["days"]
        if not slug or not name or "@" not in email:
            raise CommandError("--slug, --name and a valid --email are required")
        if not 1 <= n_ops <= len(OPERATORS):
            raise CommandError(f"--operators must be 1..{len(OPERATORS)}")
        if not 0 <= n_calls <= MAX_CALLS:
            raise CommandError(f"--calls must be 0..{MAX_CALLS}")
        if not 1 <= days <= MAX_DAYS:
            raise CommandError(f"--days must be 1..{MAX_DAYS}")

        password = secrets.token_urlsafe(12)  # never derived from --seed
        with transaction.atomic():
            replaced = self._clear_existing(slug, name, email, opts["reset"])
            company, created = self._build(
                slug=slug,
                name=name,
                email=email,
                password=password,
                n_ops=n_ops,
                n_calls=n_calls,
                days=days,
                rng=random.Random(opts["seed"]),
            )
            AuditLog.objects.create(
                company=company,
                action="demo.account_created",
                target_model="companies.Company",
                target_id=str(company.pk),
                changes={
                    "slug": slug,
                    "admin_email": email,
                    "operators": n_ops,
                    "contacts": created["contacts"],
                    "calls": created["calls"],
                    "days": days,
                    "seed": opts["seed"],
                    "reset": replaced is not None,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo company '{name}' ({slug}) ready: {n_ops} operators, "
                f"{created['contacts']} contacts, {created['calls']} calls over {days} days."
            )
        )
        self.stdout.write(f"Cabinet login: {email}")
        self.stdout.write(f"Password:      {password}")
        self.stdout.write("The password is shown ONCE and stored nowhere else — save it now.")

    # ── Safety ─────────────────────────────────────────────────────────────
    def _clear_existing(self, slug: str, name: str, email: str, reset: bool) -> int | None:
        """Refuse anything that is not ours; with --reset delete the old demo.
        Returns the deleted company's pk (None when nothing was replaced)."""
        existing = Company.objects.select_for_update().filter(slug=slug).first()
        if existing is not None:
            if not is_demo(existing):
                raise CommandError(
                    f"company '{slug}' exists and is NOT a demo company — refusing to touch it"
                )
            if not reset:
                raise CommandError(
                    f"demo company '{slug}' already exists — pass --reset to rebuild it"
                )
        if Company.objects.filter(name__iexact=name).exclude(slug=slug).exists():
            raise CommandError(f"another company is already named '{name}'")
        ours = User.objects.filter(company=existing) if existing else User.objects.none()
        taken = User.objects.filter(username__in=[email, *self._operator_usernames(slug)])
        if taken.exclude(pk__in=ours.values("pk")).exists():
            raise CommandError("a user with the demo admin/operator login already exists")
        if User.objects.filter(email__iexact=email).exclude(pk__in=ours.values("pk")).exists():
            raise CommandError(f"email {email} already belongs to another user")

        if existing is None:
            return None
        pk = existing.pk
        has_audio = CallAudio.objects.filter(call__company=existing).exists()
        existing.delete()  # cascades to its users, operators, devices, calls…
        if has_audio:
            from apps.billing.tasks import purge_company_storage

            transaction.on_commit(lambda: purge_company_storage.delay(pk))
        self.stdout.write(f"Removed the previous demo company '{slug}'.")
        return pk

    @staticmethod
    def _operator_usernames(slug: str) -> list[str]:
        return [f"{login}@{slug}.demo" for login, *_ in OPERATORS]

    # ── Data ───────────────────────────────────────────────────────────────
    def _build(
        self,
        *,
        slug: str,
        name: str,
        email: str,
        password: str,
        n_ops: int,
        n_calls: int,
        days: int,
        rng: random.Random,
    ) -> tuple[Company, dict[str, int]]:
        now = timezone.now()
        company = Company.objects.create(
            name=name,
            slug=slug,
            status=Company.Status.ACTIVE,
            country="UZ",
            phone_code="998",
            timezone=TIMEZONE,
            feature_flags={DEMO_FLAG: True},
        )
        User.objects.create_user(
            username=email,
            email=email,
            password=password,
            company=company,
            is_company_admin=True,
            email_verified=True,
            first_name="Demo",
        )
        role = Role.objects.create(
            company=company, name="Operator", permissions=["calls.view", "calls.upload"]
        )

        operators: list[dict[str, Any]] = []
        used_numbers: set[str] = set()
        for i, (login, full_name, weight, answer, inbound, talk) in enumerate(OPERATORS[:n_ops]):
            user = User.objects.create_user(
                username=self._operator_usernames(slug)[i],
                password=None,  # unusable — operators sign in on the device by API key
                first_name=full_name.split()[0],
                last_name=full_name.split()[-1],
                company=company,
                role=role,
            )
            profile = OperatorProfile.all_objects.create(
                company=company, user=user, user_name=login, full_name=full_name
            )
            manufacturer, model = DEVICE_MODELS[i % len(DEVICE_MODELS)]
            device = Device.all_objects.create(
                company=company,
                operator=profile,
                device_id=uuid.UUID(int=rng.getrandbits(128)).hex[:16],
                model=model,
                manufacturer=manufacturer,
                app_version="1.4.2",
                os_version=rng.choice(["12", "13", "14"]),
                last_seen_at=now - timedelta(minutes=rng.randint(1, 240)),
            )
            sims = []
            for slot in range(2 if i % 2 == 0 else 1):  # every other operator dual-SIM
                number = _uz_number(rng)
                while number in used_numbers:
                    number = _uz_number(rng)
                used_numbers.add(number)
                sims.append(
                    SimCard.all_objects.create(
                        company=company, operator=profile, sim_slot=slot, number=number
                    )
                )
            operators.append(
                {
                    "profile": profile,
                    "device": device,
                    "sims": sims,
                    "weight": weight,
                    "answer": answer,
                    "inbound": inbound,
                    "mu": math.log(talk),
                }
            )

        # Contacts: some with two numbers; their owners call most often.
        contact_numbers: dict[str, str] = {}
        for contact_name in CONTACT_NAMES:
            contact = Contact.all_objects.create(
                company=company,
                name=contact_name,
                responsible=rng.choice(operators)["profile"].user,
            )
            for _ in range(2 if rng.random() < 0.25 else 1):
                number = _uz_number(rng)
                while number in used_numbers:
                    number = _uz_number(rng)
                used_numbers.add(number)
                ContactPhone.objects.create(contact=contact, number=number)
                contact_numbers[number] = contact_name

        calls = self._create_calls(company, operators, contact_numbers, n_calls, days, now, rng)
        return company, {"contacts": len(CONTACT_NAMES), "calls": calls}

    def _create_calls(
        self,
        company: Company,
        operators: list[dict[str, Any]],
        contact_numbers: dict[str, str],
        n_calls: int,
        days: int,
        now: datetime,
        rng: random.Random,
    ) -> int:
        tz = ZoneInfo(TIMEZONE)
        today = now.astimezone(tz).date()
        dates = [today - timedelta(days=k) for k in range(days)]
        date_weights = [WEEKDAY_WEIGHTS[d.weekday()] for d in dates]
        hours = list(HOUR_WEIGHTS)
        hour_weights = list(HOUR_WEIGHTS.values())
        op_weights = [op["weight"] for op in operators]

        # Counterparties: catalog contacts and a set of regulars call again and
        # again (repeat callers); a long tail of one-off numbers fills the rest.
        regulars = [_uz_number(rng) for _ in range(60)]
        one_offs = [_uz_number(rng) for _ in range(max(200, n_calls // 2))]
        pool = list(contact_numbers) + regulars + one_offs
        pool_weights = [14.0] * len(contact_numbers) + [6.0] * len(regulars) + [1.0] * len(one_offs)

        def pick_start() -> datetime:
            for _ in range(50):
                day: date = rng.choices(dates, date_weights)[0]
                hour = rng.choices(hours, hour_weights)[0]
                local = datetime(
                    day.year,
                    day.month,
                    day.day,
                    hour,
                    rng.randint(0, 59),
                    rng.randint(0, 59),
                    tzinfo=tz,
                )
                if local <= now:
                    return local
            return (now - timedelta(minutes=rng.randint(5, 600))).astimezone(tz)

        created = 0
        batch: list[CallRecord] = []
        for _ in range(n_calls):
            op = rng.choices(operators, op_weights)[0]
            profile: OperatorProfile = op["profile"]
            sim: SimCard = rng.choice(op["sims"])
            counterparty = rng.choices(pool, pool_weights)[0]
            counterparty_name = contact_numbers.get(counterparty)
            inbound = rng.random() < op["inbound"]

            answer_rate = op["answer"] if inbound else op["answer"] - 0.12
            if counterparty_name:
                answer_rate += 0.08  # known clients pick up / get picked up more
            if rng.random() < answer_rate:
                status = CallRecord.CallStatus.ANSWERED
                mu = op["mu"] if inbound else op["mu"] - 0.2
                duration = int(min(3600, max(5, rng.lognormvariate(mu, 0.85))))
            else:
                # No "busy": the app does not send it yet (planned) and the
                # reports count only no_answer as missed, so busy rows would
                # make answered + missed ≠ total in front of prospects.
                status = CallRecord.CallStatus.NO_ANSWER
                duration = 0

            start_local = pick_start()
            end_local = start_local + timedelta(seconds=duration)
            if inbound:
                from_number, from_name = counterparty, counterparty_name
                to_number, to_name = sim.number, profile.full_name
            else:
                from_number, from_name = sim.number, profile.full_name
                to_number, to_name = counterparty, counterparty_name
            located = rng.random() < 0.35
            batch.append(
                CallRecord(
                    company=company,
                    operator=profile,
                    device=op["device"],
                    call_id=uuid.UUID(int=rng.getrandbits(128)).hex,
                    call_type=(
                        CallRecord.CallType.INBOUND if inbound else CallRecord.CallType.OUTBOUND
                    ),
                    call_status=status,
                    from_number=from_number,
                    from_name=from_name,
                    to_number=to_number,
                    to_name=to_name,
                    operator_number=sim.number,
                    counterparty_number=counterparty,
                    counterparty_name=counterparty_name,
                    resolved_name=counterparty_name,
                    sim_slot=sim.sim_slot,
                    duration=duration,
                    start_time=start_local,
                    end_time=end_local,
                    start_time_local=start_local.strftime("%Y-%m-%d %H:%M:%S"),
                    end_time_local=end_local.strftime("%Y-%m-%d %H:%M:%S"),
                    latitude=TASHKENT[0] + rng.uniform(-0.06, 0.06) if located else None,
                    longitude=TASHKENT[1] + rng.uniform(-0.08, 0.08) if located else None,
                )
            )
            if len(batch) >= BATCH_SIZE:
                CallRecord.all_objects.bulk_create(batch)
                created += len(batch)
                batch.clear()
        if batch:
            CallRecord.all_objects.bulk_create(batch)
            created += len(batch)
        return created
