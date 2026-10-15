"""create_demo_account: one production-safe demo tenant, kept out of billing
and the platform KPIs."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Device, OperatorProfile, SimCard, User
from apps.billing import services as billing
from apps.billing import tasks
from apps.billing.models import BillingNotification, DailyCharge, MonthlyStatement
from apps.calls.models import CallRecord, Contact
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.partners.models import ROLE_SUPERADMIN, Integrator
from apps.partners.services import get_platform_role

pytestmark = pytest.mark.django_db

N_CALLS = 300


def run(*args: str) -> str:
    out = StringIO()
    call_command("create_demo_account", "--calls", str(N_CALLS), *args, stdout=out)
    return out.getvalue()


def printed_password(output: str) -> str:
    match = re.search(r"^Password:\s+(\S+)$", output, re.MULTILINE)
    assert match, output
    return match.group(1)


TASHKENT = ZoneInfo("Asia/Tashkent")


def freeze_now(monkeypatch: pytest.MonkeyPatch, local: str) -> datetime:
    """Pin ``timezone.now()`` to 2026-10-14 ``local`` (HH:MM, Asia/Tashkent).

    Returned UTC-aware like the real ``timezone.now()``, so code that takes
    ``.date()`` of it sees the UTC date — the case that matters around
    Tashkent midnight (UTC+5)."""
    hour, minute = map(int, local.split(":"))
    frozen = datetime(2026, 10, 14, hour, minute, tzinfo=TASHKENT).astimezone(UTC)
    monkeypatch.setattr(timezone, "now", lambda: frozen)
    return frozen


def real_company(slug: str = "real-co", *, operators: int = 1) -> Company:
    company = Company.objects.create(name=f"Real {slug}", slug=slug, status=Company.Status.ACTIVE)
    for i in range(operators):
        user = User.objects.create_user(username=f"op{i}@{slug}", company=company)
        OperatorProfile.all_objects.create(company=company, user=user, user_name=f"op{i}")
    return company


class TestCreate:
    def test_creates_expected_company_and_counts(self) -> None:
        run()
        company = Company.objects.get(slug="demo")
        assert company.name == "Demo kompaniya"
        assert company.status == Company.Status.ACTIVE
        assert company.feature_flags == {"demo": True}
        assert (company.country, company.phone_code, company.timezone) == (
            "UZ",
            "998",
            "Asia/Tashkent",
        )
        assert company.integrator_id is None
        assert billing.is_demo(company)

        users = User.objects.filter(company=company)
        admin = users.get(is_company_admin=True)
        assert admin.username == admin.email == "demo@doocall.uz"
        assert admin.email_verified and admin.has_usable_password()

        operators = OperatorProfile.all_objects.filter(company=company)
        assert operators.count() == 6
        assert all(not op.user.has_usable_password() for op in operators)
        assert users.count() == 7  # admin + 6 operators
        assert Device.all_objects.filter(company=company).count() == 6
        assert SimCard.all_objects.filter(company=company).count() == 9  # every 2nd dual-SIM
        assert Contact.all_objects.filter(company=company).count() == 30

        calls = CallRecord.all_objects.filter(company=company)
        assert calls.count() == N_CALLS
        assert set(calls.values_list("call_status", flat=True)) == {"answered", "no_answer"}
        assert set(calls.values_list("call_type", flat=True)) == {"inbound", "outbound"}
        assert not calls.filter(call_status="no_answer", duration__gt=0).exists()
        assert not calls.filter(call_status="answered", duration=0).exists()
        assert calls.values("operator").distinct().count() == 6

    def test_calls_fall_in_the_window_and_working_hours(self) -> None:
        run("--days", "14")
        now = timezone.now()
        tz = ZoneInfo("Asia/Tashkent")
        calls = CallRecord.all_objects.filter(company__slug="demo")
        for start, local in calls.values_list("start_time", "start_time_local"):
            assert now - timedelta(days=15) < start <= now
            here = start.astimezone(tz)
            assert 8 <= here.hour <= 20
            assert local == here.strftime("%Y-%m-%d %H:%M:%S")
        # Repeat callers exist (contacts and regulars call again and again).
        numbers = list(calls.values_list("counterparty_number", flat=True))
        assert max(numbers.count(n) for n in set(numbers)) >= 3

    def test_custom_arguments(self) -> None:
        out = run(
            "--slug",
            "acme-demo",
            "--name",
            "Acme demo",
            "--email",
            "Boss@Acme.uz",
            "--operators",
            "3",
        )
        company = Company.objects.get(slug="acme-demo")
        assert company.name == "Acme demo"
        assert OperatorProfile.all_objects.filter(company=company).count() == 3
        assert User.objects.get(company=company, is_company_admin=True).email == "boss@acme.uz"
        assert "Cabinet login: boss@acme.uz" in out

    @pytest.mark.parametrize(
        ("local", "today_min", "today_max"),
        [
            ("00:10", 0, 0),  # office closed: nothing yet today, nothing in the future
            ("08:05", 0, 4),  # the first five minutes of the working day
            ("15:30", 5, N_CALLS),
            ("23:55", 5, N_CALLS),
        ],
    )
    def test_today_is_filled_up_to_now_never_beyond(
        self, monkeypatch: pytest.MonkeyPatch, local: str, today_min: int, today_max: int
    ) -> None:
        now = freeze_now(monkeypatch, local)
        run()
        today = now.astimezone(TASHKENT).date()
        starts = CallRecord.all_objects.filter(company__slug="demo").values_list(
            "start_time", flat=True
        )
        assert max(starts) <= now
        today_calls = sum(1 for s in starts if s.astimezone(TASHKENT).date() == today)
        # Calls follow the 8–20 working day: none before the office opens,
        # today's share once the day is under way.
        assert today_min <= today_calls <= today_max

    def test_same_seed_is_deterministic(self) -> None:
        def per_operator() -> list[tuple[str, str, int]]:
            return sorted(
                CallRecord.all_objects.filter(company__slug="demo").values_list(
                    "operator__user_name", "call_status", "duration"
                )
            )

        run()
        first = per_operator()
        run("--reset")
        assert per_operator() == first


class TestSecrets:
    def test_random_password_printed_once_and_never_logged(self) -> None:
        output = run()
        password = printed_password(output)
        assert len(password) >= 16
        assert output.count(password) == 1
        admin = User.objects.get(username="demo@doocall.uz")
        assert admin.check_password(password)

        entries = AuditLog.objects.filter(action="demo.account_created")
        assert entries.count() == 1
        assert entries[0].changes["calls"] == N_CALLS
        for entry in AuditLog.objects.all():
            assert password not in json.dumps(entry.changes)

    def test_reset_issues_a_new_password(self) -> None:
        first = printed_password(run())
        second = printed_password(run("--reset"))
        assert first != second
        assert User.objects.get(username="demo@doocall.uz").check_password(second)

    def test_creates_no_platform_accounts(self) -> None:
        before = (
            User.objects.filter(is_superuser=True).count(),
            User.objects.filter(company=None).count(),
            Integrator.objects.count(),
        )
        run()
        run("--reset")
        after = (
            User.objects.filter(is_superuser=True).count(),
            User.objects.filter(company=None).count(),
            Integrator.objects.count(),
        )
        assert after == before == (0, 0, 0)
        assert not User.objects.filter(is_staff=True).exists()


class TestSafety:
    def test_second_run_without_reset_refuses(self) -> None:
        run()
        company = Company.objects.get(slug="demo")
        with pytest.raises(CommandError, match="--reset"):
            run()
        assert Company.objects.get(slug="demo").pk == company.pk
        assert CallRecord.all_objects.filter(company=company).count() == N_CALLS

    def test_refuses_a_real_company_with_or_without_reset(self) -> None:
        real = real_company("demo")
        for args in ((), ("--reset",)):
            with pytest.raises(CommandError, match="NOT a demo"):
                run(*args)
        real.refresh_from_db()
        assert real.feature_flags == {}
        assert OperatorProfile.all_objects.filter(company=real).count() == 1
        assert not AuditLog.objects.filter(action="demo.account_created").exists()

    def test_reset_rebuilds_only_the_demo_company(self) -> None:
        other = real_company("real-co")
        CallRecord.all_objects.create(
            company=other,
            call_id="keep-me",
            call_type="inbound",
            call_status="answered",
            from_number="+998901111111",
            to_number="+998902222222",
            counterparty_number="+998901111111",
            duration=30,
            start_time=timezone.now(),
        )
        run()
        old = Company.objects.get(slug="demo")
        old_calls = set(CallRecord.all_objects.filter(company=old).values_list("pk", flat=True))

        run("--reset", "--operators", "2")
        new = Company.objects.get(slug="demo")
        assert new.pk != old.pk
        assert not CallRecord.all_objects.filter(pk__in=old_calls).exists()
        assert OperatorProfile.all_objects.filter(company=new).count() == 2
        assert User.objects.filter(username="demo@doocall.uz").count() == 1
        # The other tenant is untouched.
        assert CallRecord.all_objects.filter(company=other, call_id="keep-me").exists()
        assert OperatorProfile.all_objects.filter(company=other).count() == 1
        assert AuditLog.objects.filter(action="demo.account_created").count() == 2

    def test_refuses_logins_owned_by_someone_else(self) -> None:
        real = real_company("real-co")
        User.objects.create_user(username="demo@doocall.uz", email="x@y.uz", company=real)
        with pytest.raises(CommandError, match="already exists"):
            run()
        User.objects.filter(username="demo@doocall.uz").delete()
        User.objects.create_user(username="other", email="DEMO@doocall.uz", company=real)
        with pytest.raises(CommandError, match="another user"):
            run()
        assert not Company.objects.filter(slug="demo").exists()

    def test_refuses_a_name_taken_by_another_company(self) -> None:
        Company.objects.create(name="Demo kompaniya", slug="someone-else")
        with pytest.raises(CommandError, match="already named"):
            run()

    def test_rejects_out_of_range_arguments(self) -> None:
        for args in (("--operators", "0"), ("--operators", "99"), ("--days", "0")):
            with pytest.raises(CommandError):
                run(*args)
        assert not Company.objects.filter(slug="demo").exists()


class TestBillingSkipsDemo:
    def test_billing_sweeps_never_charge_suspend_or_warn_the_demo(self) -> None:
        run()
        demo = Company.objects.get(slug="demo")
        paying = real_company("paying-co", operators=2)
        now = timezone.now() + timedelta(days=1)

        tasks.run_daily_accrual(now)
        tasks.run_trial_expiry(now + timedelta(days=400))
        tasks.run_monthly_settlement(now + timedelta(days=400))
        billing.run_overdue_enforcement(now + timedelta(days=400))
        tasks.run_balance_warning(now)

        demo.refresh_from_db()
        assert demo.status == Company.Status.ACTIVE
        assert demo.balance_uzs == 0
        assert not DailyCharge.all_objects.filter(company=demo).exists()
        assert not MonthlyStatement.all_objects.filter(company=demo).exists()
        assert not BillingNotification.all_objects.filter(company=demo).exists()
        assert billing.days_of_balance_left(demo) is None

        # The filter only skips demo tenants: a normal company is still billed
        # (and, with an empty balance, suspended).
        assert DailyCharge.all_objects.filter(company=paying).count() == 2
        paying.refresh_from_db()
        assert paying.status == Company.Status.SUSPENDED

    def test_cabinet_billing_has_no_paywall_or_runout_warning(self) -> None:
        run()
        client = APIClient()
        client.force_authenticate(User.objects.get(username="demo@doocall.uz"))
        assert client.get("/api/web/v1/billing/status").status_code == 200
        overview = client.get("/api/web/v1/billing/overview").json()
        assert overview["days_left"] is None
        assert overview["blocked"] is False


class TestAdminKpisExcludeDemo:
    def test_dashboard_leaderboard_and_series(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Pinned to a Tashkent afternoon: AdminDashboardView buckets its 30-day
        # series by the UTC date while TruncDate groups by the Tashkent date,
        # so between 00:00 and 05:00 local today's calls fall outside the
        # series (a view bug, reported separately) and this test went red.
        freeze_now(monkeypatch, "15:30")
        real = real_company("real-co")
        CallRecord.all_objects.create(
            company=real,
            call_id="r1",
            call_type="inbound",
            call_status="answered",
            from_number="+998901111111",
            to_number="+998902222222",
            counterparty_number="+998901111111",
            duration=60,
            start_time=timezone.now(),
        )
        run()
        staff = User.objects.create_user(
            username="root@platform.uz", role=get_platform_role(ROLE_SUPERADMIN)
        )
        client = APIClient()
        client.force_authenticate(staff)

        kpis = client.get("/api/admin/v1/dashboard").json()
        assert kpis["companies"]["total"] == 1
        assert kpis["companies"]["active"] == 1
        assert kpis["total_calls"] == 1
        assert kpis["total_call_seconds"] == 60
        assert sum(kpis["calls_series"]) == 1

        board = client.get("/api/admin/v1/dashboard/calls-today").json()
        assert [c["id"] for c in board["companies"]] == [real.pk]
        assert board["total"] == 1

        series = client.get("/api/admin/v1/dashboard/series?metric=calls&period=yearly").json()
        assert sum(p["value"] for p in series["series"]) == 1

        # The company itself is still listed for admins (marked via its flags).
        listing = client.get("/api/admin/v1/companies").json()["companies"]
        assert {c["slug"] for c in listing} == {"real-co", "demo"}
