"""Performance guard: dashboard + every report < 300ms against a 12k-row seed.

Marked ``perf`` and skipped when the CI env var is set (timing on shared
runners is flaky) — run locally via
``docker compose exec backend pytest -m perf -s``.
"""

from __future__ import annotations

import os
import random
import time
import uuid
from collections.abc import Generator
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.calls.models import CallRecord
from apps.companies.models import Company

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.perf,
    pytest.mark.skipif(bool(os.environ.get("CI")), reason="timing-flaky on CI runners"),
]

N_CALLS = 12_000
BUDGET_SEC = 0.300

ENDPOINTS = [
    "/api/web/v1/dashboard?period=7d",
    "/api/web/v1/reports/general",
    "/api/web/v1/reports/weekday-matrix",
    "/api/web/v1/reports/period-counts?group=day",
    "/api/web/v1/reports/period-counts?group=week&unique=true",
    "/api/web/v1/reports/per-employee",
    "/api/web/v1/reports/per-client",
    "/api/web/v1/reports/unanswered",
    "/api/web/v1/reports/last-contact",
    "/api/web/v1/calls?page=1",
]


@pytest.fixture(scope="class")
def big_seed(django_db_setup: object, django_db_blocker: object) -> Generator[dict]:
    """12k calls across 6 operators / 800 numbers / 30 days (class-scoped)."""
    with django_db_blocker.unblock():  # type: ignore[attr-defined]
        from apps.accounts.models import User

        rng = random.Random(7)
        company = Company.objects.create(name="Perf Co", slug="perf-co")
        admin = User.objects.create_user(
            username="admin@perf-co", company=company, is_company_admin=True
        )
        operators = []
        for i in range(6):
            user = User.objects.create_user(username=f"perf-op{i}@perf-co", company=company)
            operators.append(
                OperatorProfile.all_objects.create(
                    company=company, user=user, user_name=f"perf-op{i}"
                )
            )
        numbers = [f"+9989{rng.randint(10000000, 99999999)}" for _ in range(800)]
        now = timezone.now()
        batch: list[CallRecord] = []
        for _ in range(N_CALLS):
            answered = rng.random() < 0.68
            start = now - timedelta(minutes=rng.uniform(0, 30 * 24 * 60))
            batch.append(
                CallRecord(
                    company=company,
                    operator=rng.choice(operators),
                    call_id=uuid.UUID(int=rng.getrandbits(128)).hex,
                    call_type="inbound" if rng.random() < 0.55 else "outbound",
                    call_status="answered" if answered else "no_answer",
                    from_number=rng.choice(numbers),
                    to_number="+998990000000",
                    counterparty_number=rng.choice(numbers),
                    duration=rng.randint(15, 600) if answered else 0,
                    start_time=start,
                )
            )
            if len(batch) >= 2000:
                CallRecord.all_objects.bulk_create(batch)
                batch.clear()
        if batch:
            CallRecord.all_objects.bulk_create(batch)
        yield {"company": company, "admin": admin}
        with django_db_blocker.unblock():  # type: ignore[attr-defined]
            company.delete()


@pytest.mark.usefixtures("big_seed")
class TestPerformance:
    @pytest.fixture
    def perf_client(self, big_seed: dict) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=big_seed["admin"])
        return client

    @pytest.mark.parametrize("url", ENDPOINTS)
    def test_endpoint_under_budget(self, perf_client: APIClient, url: str) -> None:
        # Warm-up request (connection setup, query-plan cache).
        assert perf_client.get(url).status_code == 200

        start = time.perf_counter()
        response = perf_client.get(url)
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        print(f"\n  PERF {url} -> {elapsed * 1000:.1f}ms")
        assert elapsed < BUDGET_SEC, f"{url} took {elapsed * 1000:.0f}ms (budget 300ms)"
