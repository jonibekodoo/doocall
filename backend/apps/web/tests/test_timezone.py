"""Per-company country/timezone: settings roundtrip + time math."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db

UTC = ZoneInfo("UTC")


class TestAccountLocaleSettings:
    def test_roundtrip_and_validation(self, client: APIClient, company: Company) -> None:
        body = client.get("/api/web/v1/settings/account").json()["settings"]
        assert body["country"] == "UZ"
        assert body["timezone"] == "Asia/Tashkent"

        saved = client.put(
            "/api/web/v1/settings/account",
            {"country": "kz", "timezone": "Asia/Almaty"},
            format="json",
        ).json()["settings"]
        assert saved["country"] == "KZ"
        assert saved["timezone"] == "Asia/Almaty"
        company.refresh_from_db()
        assert company.timezone == "Asia/Almaty"

        assert (
            client.put(
                "/api/web/v1/settings/account",
                {"timezone": "Mars/Olympus"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.put(
                "/api/web/v1/settings/account",
                {"country": "KAZ"},
                format="json",
            ).status_code
            == 400
        )


class TestCompanyTimeMath:
    def test_upload_parse_uses_company_zone(self) -> None:
        from apps.api.views import _parse_local

        moscow = _parse_local("2026-01-01 10:00:00", ZoneInfo("Europe/Moscow"))  # UTC+3
        tashkent = _parse_local("2026-01-01 10:00:00", ZoneInfo("Asia/Tashkent"))  # UTC+5
        assert moscow == datetime(2026, 1, 1, 7, 0, tzinfo=UTC)
        assert tashkent == datetime(2026, 1, 1, 5, 0, tzinfo=UTC)

    def test_date_filters_and_today_follow_company_zone(self, company: Company) -> None:
        from apps.web.queries import period_start
        from apps.web.views_calls import parse_date

        company.timezone = "Europe/Moscow"
        company.save(update_fields=["timezone"])
        with tenant_context(company.pk):
            day_start = parse_date("2026-01-01")
            assert day_start is not None
            assert day_start.utcoffset() == timedelta(hours=3)

            today = period_start("today", now=datetime(2026, 1, 1, 22, 30, tzinfo=UTC))
            # 22:30 UTC = 01:30 next day in Moscow → local midnight of Jan 2.
            assert today.astimezone(UTC) == datetime(2026, 1, 1, 21, 0, tzinfo=UTC)
