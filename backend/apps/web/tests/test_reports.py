"""EVERY report endpoint asserted against the hand-computed 40-call fixture."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.companies.models import Company

from .fixture_calls import N1, N2, N3, N4, N5, N6, seed_fixture_calls

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(
    company: Company,
    op_a: OperatorProfile,
    op_b: OperatorProfile,
    other_company_noise: Company,
) -> dict[str, OperatorProfile]:
    seed_fixture_calls(company, op_a, op_b)
    return {"A": op_a, "B": op_b}


class TestGeneralReport:
    def test_exact_totals(self, client: APIClient, seeded: dict) -> None:
        report = client.get("/api/web/v1/reports/general").json()["report"]
        assert report == {
            "all": {
                "total": 40,
                "answered": 21,
                "missed": 19,
                "missed_inbound": 9,
                "not_reached": 10,
            },
            "inbound": {
                "total": 19,
                "answered": 10,
                "missed": 9,
                "missed_inbound": 9,
                "not_reached": 0,
            },
            "outbound": {
                "total": 21,
                "answered": 11,
                "missed": 10,
                "missed_inbound": 0,
                "not_reached": 10,
            },
            "total_duration_sec": 1790,
        }


class TestWeekdayMatrix:
    def test_exact_rows(self, client: APIClient, seeded: dict) -> None:
        rows = client.get("/api/web/v1/reports/weekday-matrix").json()["report"]
        keys = ("weekday", "total", "inbound", "outbound", "answered", "missed")
        new = ("missed_inbound", "not_reached")
        assert [tuple(r[k] for k in keys + new) for r in rows] == [
            (1, 10, 6, 4, 5, 5, 3, 2),
            (2, 10, 5, 5, 5, 5, 2, 3),
            (3, 10, 3, 7, 6, 4, 1, 3),
            (4, 10, 5, 5, 5, 5, 3, 2),
        ]
        assert all(len(r) == len(keys + new) for r in rows)


class TestPeriodCounts:
    def test_daily_counts(self, client: APIClient, seeded: dict) -> None:
        body = client.get("/api/web/v1/reports/period-counts?group=day").json()
        assert body["unique_numbers"] is False
        totals = [(r["bucket"], r["total"], r["answered"], r["missed"]) for r in body["report"]]
        assert totals == [
            ("2026-08-03", 10, 5, 5),
            ("2026-08-04", 10, 5, 5),
            ("2026-08-05", 10, 6, 4),
            ("2026-08-06", 10, 5, 5),
        ]
        split = [(r["missed_inbound"], r["not_reached"]) for r in body["report"]]
        assert split == [(3, 2), (2, 3), (1, 3), (3, 2)]

    def test_unique_numbers_flag(self, client: APIClient, seeded: dict) -> None:
        body = client.get("/api/web/v1/reports/period-counts?group=day&unique=true").json()
        assert body["unique_numbers"] is True
        # Every fixture day touches all six numbers → 6, not 10.
        assert [r["total"] for r in body["report"]] == [6, 6, 6, 6]

    def test_month_grouping(self, client: APIClient, seeded: dict) -> None:
        body = client.get("/api/web/v1/reports/period-counts?group=month").json()
        assert [(r["bucket"], r["total"]) for r in body["report"]] == [("2026-08-01", 40)]


class TestPerEmployee:
    def test_exact_rows(self, client: APIClient, seeded: dict) -> None:
        rows = client.get("/api/web/v1/reports/per-employee").json()["report"]
        by_name = {r["user_name"]: r for r in rows}
        a, b = by_name["op-a"], by_name["op-b"]

        assert (a["total"], a["answered"], a["missed"]) == (20, 12, 8)
        assert a["duration_minutes"] == pytest.approx(1055 / 60, abs=0.1)
        assert (b["total"], b["answered"], b["missed"]) == (20, 9, 11)
        assert b["duration_minutes"] == pytest.approx(735 / 60, abs=0.1)
        assert a["inbound"] + a["outbound"] == 20
        assert b["inbound"] + b["outbound"] == 20
        # missed = missed_inbound (client called, no answer) + not_reached.
        assert (a["missed_inbound"], a["not_reached"]) == (2, 6)
        assert (b["missed_inbound"], b["not_reached"]) == (7, 4)


class TestPerClient:
    def test_exact_totals(self, client: APIClient, seeded: dict) -> None:
        rows = client.get("/api/web/v1/reports/per-client").json()["report"]
        totals = {r["counterparty_number"]: r["total"] for r in rows}
        assert totals == {N1: 8, N2: 8, N3: 7, N4: 5, N5: 7, N6: 5}
        answered = {r["counterparty_number"]: r["answered"] for r in rows}
        assert answered == {N1: 5, N2: 7, N3: 3, N4: 0, N5: 6, N6: 0}
        split = {r["counterparty_number"]: (r["missed_inbound"], r["not_reached"]) for r in rows}
        assert split == {N1: (2, 1), N2: (1, 0), N3: (2, 2), N4: (1, 4), N5: (1, 0), N6: (2, 3)}


class TestUnansweredReport:
    """Clients waiting for a call-back: the LAST call is no_answer and the
    client called us (inbound no_answer) since our last answered call."""

    def test_exact_membership_and_attempts(self, client: APIClient, seeded: dict) -> None:
        report = client.get("/api/web/v1/reports/unanswered").json()["report"]
        by_number = {r["counterparty_number"]: r for r in report}

        # N2 and N5 recovered with a successful call → dropped off. N3's last
        # call is no_answer, but only OUR call-backs (#29, #36, outbound)
        # failed since #24 was answered — "not reached", not a client
        # waiting on us → excluded.
        assert set(by_number) == {N1, N4, N6}

        assert by_number[N1]["attempts_since_success"] == 1  # only #37 after #31
        assert by_number[N1]["last_success"] is not None
        # Never answered → all their missed calls count, no last_success. N4's
        # last call is our failed #39, but the client's #32 still waits.
        assert by_number[N4]["attempts_since_success"] == 5
        assert by_number[N4]["last_success"] is None
        assert by_number[N6]["attempts_since_success"] == 5
        assert by_number[N6]["last_success"] is None

    def test_drop_off_after_success(
        self, client: APIClient, seeded: dict, company: Company
    ) -> None:
        """A successful call to N4 must remove it from the report instantly."""
        from datetime import timedelta

        from apps.calls.models import CallRecord

        from .fixture_calls import BASE

        CallRecord.all_objects.create(
            company=company,
            operator=seeded["A"],
            call_id="fx-recovery",
            call_type="outbound",
            call_status="answered",
            from_number="+998990000000",
            to_number=N4,
            counterparty_number=N4,
            duration=20,
            start_time=BASE + timedelta(days=4),
        )
        report = client.get("/api/web/v1/reports/unanswered").json()["report"]
        assert N4 not in {r["counterparty_number"] for r in report}

    def test_only_outbound_misses_never_listed(
        self, client: APIClient, seeded: dict, company: Company
    ) -> None:
        """A number we only called (never reached) is not 'unanswered'; once
        the client calls and nobody answers, it is."""
        from datetime import timedelta

        from apps.calls.models import CallRecord

        from .fixture_calls import BASE

        cold = "+998911119999"
        rows = {"call_type": "outbound", "from_number": "+998990000000", "to_number": cold}
        for i in range(2):
            CallRecord.all_objects.create(
                company=company,
                operator=seeded["A"],
                call_id=f"fx-cold-{i}",
                call_status="no_answer",
                counterparty_number=cold,
                duration=0,
                start_time=BASE + timedelta(days=4, minutes=i),
                **rows,
            )
        url = "/api/web/v1/reports/unanswered"
        assert cold not in {r["counterparty_number"] for r in client.get(url).json()["report"]}

        CallRecord.all_objects.create(
            company=company,
            operator=seeded["A"],
            call_id="fx-cold-back",
            call_type="inbound",
            call_status="no_answer",
            from_number=cold,
            to_number="+998990000000",
            counterparty_number=cold,
            duration=0,
            start_time=BASE + timedelta(days=4, minutes=5),
        )
        report = {r["counterparty_number"]: r for r in client.get(url).json()["report"]}
        assert report[cold]["attempts_since_success"] == 3


class TestLastContact:
    def test_exact_last_calls(self, client: APIClient, seeded: dict) -> None:
        report = client.get("/api/web/v1/reports/last-contact").json()["report"]
        by_number = {r["counterparty_number"]: r for r in report}
        assert len(report) == 6

        # Hand-derived: last call per number is #37/#38/#36/#39/#40/#34.
        assert by_number[N1]["status"] == "no_answer" and by_number[N1]["direction"] == "inbound"
        assert by_number[N2]["status"] == "answered" and by_number[N2]["direction"] == "outbound"
        assert by_number[N3]["status"] == "no_answer" and by_number[N3]["direction"] == "outbound"
        assert by_number[N4]["status"] == "no_answer"
        assert by_number[N5]["status"] == "answered" and by_number[N5]["duration"] == 45
        assert by_number[N6]["status"] == "no_answer" and by_number[N6]["direction"] == "inbound"

        # Ordered by recency: N5 (#40) first, then N4 (#39), N2 (#38), N1 (#37)…
        assert [r["counterparty_number"] for r in report[:4]] == [N5, N4, N2, N1]


class TestTenantIsolationInReports:
    def test_noise_company_never_leaks(self, client: APIClient, seeded: dict) -> None:
        general = client.get("/api/web/v1/reports/general").json()["report"]
        assert general["all"]["total"] == 40  # noise-co has 5 more rows
        clients = client.get("/api/web/v1/reports/per-client").json()["report"]
        assert "+998900000001" not in {r["counterparty_number"] for r in clients}
