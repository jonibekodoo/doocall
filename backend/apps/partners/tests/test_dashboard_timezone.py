"""Admin dashboard day buckets and "today" follow the local day (TIME_ZONE,
Asia/Tashkent = UTC+5), the same zone the DB-side TruncDate groups by —
including the 00:00–05:00 window where the UTC date is still yesterday."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Payment
from apps.calls.models import CallRecord
from apps.companies.models import Company

from .conftest import client_for, make_company

pytestmark = pytest.mark.django_db

TASHKENT = ZoneInfo("Asia/Tashkent")


def freeze(monkeypatch: pytest.MonkeyPatch, local: str) -> datetime:
    """Pin timezone.now() to 2026-10-14 ``local`` Tashkent, UTC-aware like Django's."""
    hour, minute = map(int, local.split(":"))
    frozen = datetime(2026, 10, 14, hour, minute, tzinfo=TASHKENT).astimezone(UTC)
    monkeypatch.setattr(timezone, "now", lambda: frozen)
    return frozen


def add_call(company: Company, at: datetime, n: int) -> None:
    CallRecord.all_objects.create(
        company=company,
        call_id=f"tz-{n}",
        call_type="inbound",
        call_status="answered",
        from_number="+998901111111",
        to_number="+998902222222",
        counterparty_number="+998901111111",
        duration=60,
        start_time=at,
    )


def add_payment(company: Company, at: datetime, amount: int) -> None:
    Payment.all_objects.create(
        company=company,
        provider=Payment.Provider.MANUAL,
        amount_uzs=amount,
        status=Payment.Status.APPROVED,
        approved_at=at,
    )


@pytest.fixture
def local_day_data(superadmin: User) -> Company:
    """Built after the clock is frozen: one call/payment today (local) and two
    yesterday (local) — one of them at 04:00, inside the UTC-shift window."""
    company = make_company("tz-co")
    now = timezone.now()
    local_midnight = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    today = [now - timedelta(minutes=5)]
    yesterday = [local_midnight - timedelta(hours=1), local_midnight - timedelta(hours=20)]
    for n, at in enumerate(today + yesterday):
        add_call(company, at, n)
    add_payment(company, today[0], 100)
    for at in yesterday:
        add_payment(company, at, 10)
    return company


@pytest.mark.parametrize("local", ["00:10", "23:55"])
class TestLocalDayBuckets:
    def test_dashboard_today_and_30_day_series(
        self,
        monkeypatch: pytest.MonkeyPatch,
        superadmin: User,
        local: str,
        request: pytest.FixtureRequest,
    ) -> None:
        freeze(monkeypatch, local)
        request.getfixturevalue("local_day_data")
        kpis = client_for(superadmin).get("/api/admin/v1/dashboard").json()

        assert kpis["calls_today"] == 1
        assert kpis["calls_series"][-1] == 1  # today (local)
        assert kpis["calls_series"][-2] == 2  # yesterday (local), incl. 04:00
        assert sum(kpis["calls_series"]) == 3
        assert kpis["payments_series"][-1] == 100
        assert kpis["payments_series"][-2] == 20

    def test_calls_today_leaderboard(
        self,
        monkeypatch: pytest.MonkeyPatch,
        superadmin: User,
        local: str,
        request: pytest.FixtureRequest,
    ) -> None:
        now = freeze(monkeypatch, local)
        company = request.getfixturevalue("local_day_data")
        board = client_for(superadmin).get("/api/admin/v1/dashboard/calls-today").json()

        assert board["date"] == now.astimezone(TASHKENT).date().isoformat() == "2026-10-14"
        assert board["companies"] == [
            {"id": company.pk, "name": company.name, "total": 3, "today": 1}
        ]

    def test_daily_series_endpoint(
        self,
        monkeypatch: pytest.MonkeyPatch,
        superadmin: User,
        local: str,
        request: pytest.FixtureRequest,
    ) -> None:
        freeze(monkeypatch, local)
        request.getfixturevalue("local_day_data")
        client = client_for(superadmin)

        calls = client.get("/api/admin/v1/dashboard/series?metric=calls&period=daily").json()
        assert calls["series"][-1] == {"label": "10/14", "value": 1}
        assert calls["series"][-2] == {"label": "10/13", "value": 2}

        pays = client.get("/api/admin/v1/dashboard/series?metric=payments&period=daily").json()
        assert pays["series"][-1]["value"] == 100
        assert pays["series"][-2]["value"] == 20

    def test_payment_stats_revenue_series(
        self,
        monkeypatch: pytest.MonkeyPatch,
        superadmin: User,
        local: str,
        request: pytest.FixtureRequest,
    ) -> None:
        freeze(monkeypatch, local)
        request.getfixturevalue("local_day_data")
        stats = client_for(superadmin).get("/api/admin/v1/payments/stats").json()

        assert stats["revenue_series"][-1] == 100
        assert stats["revenue_series"][-2] == 20
