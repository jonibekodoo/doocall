"""The hand-computed 40-call report fixture.

Layout: 4 days (Mon 2026-08-03 … Thu 2026-08-06, Asia/Tashkent), 10 calls per
day, 2 operators (A, B), 6 counterparty numbers N1…N6. Every expected report
number in ``test_reports.py`` is derived from this table BY HAND — if a report
regresses, the diff points at exact semantics.

Expected key facts (hand-computed):
* totals: 40 calls, 21 answered / 19 missed, 19 in / 21 out, 1790s duration
* inbound: 10 answered / 9 missed · outbound: 11 answered / 10 missed
* weekday: Mon..Thu = 10 calls each; answered 5/5/6/5; inbound 6/5/3/5
* operator A: 20 calls, 12 answered, 8 missed, 1055s
* operator B: 20 calls,  9 answered, 11 missed,  735s
* per-client totals: N1=8, N2=8, N3=7, N4=5, N5=7, N6=5
* unanswered-now (last call missed): N1 (1 attempt since success),
  N3 (2), N4 (5, never answered), N6 (5, never answered);
  N2/N5 recovered → NOT in the list
* last-contact: N1→#37, N2→#38, N3→#36, N4→#39, N5→#40, N6→#34
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apps.accounts.models import OperatorProfile
from apps.calls.models import CallRecord
from apps.companies.models import Company

TZ = ZoneInfo("Asia/Tashkent")
BASE = datetime(2026, 8, 3, 10, 0, 0, tzinfo=TZ)  # Monday

N1, N2, N3, N4, N5, N6 = (
    "+998911110001",
    "+998911110002",
    "+998911110003",
    "+998911110004",
    "+998911110005",
    "+998911110006",
)

# (call#, operator_key, number, call_type, call_status, duration, day_offset)
CALLS = [
    # Monday
    (1, "A", N1, "inbound", "answered", 60, 0),
    (2, "A", N1, "inbound", "no_answer", 0, 0),
    (3, "A", N2, "outbound", "answered", 120, 0),
    (4, "B", N3, "inbound", "no_answer", 0, 0),
    (5, "B", N3, "inbound", "no_answer", 0, 0),
    (6, "B", N3, "inbound", "answered", 30, 0),
    (7, "A", N4, "outbound", "no_answer", 0, 0),
    (8, "B", N5, "inbound", "answered", 300, 0),
    (9, "A", N2, "outbound", "answered", 60, 0),
    (10, "B", N6, "outbound", "no_answer", 0, 0),
    # Tuesday
    (11, "A", N1, "inbound", "answered", 90, 1),
    (12, "A", N4, "outbound", "no_answer", 0, 1),
    (13, "B", N2, "inbound", "no_answer", 0, 1),
    (14, "B", N2, "inbound", "answered", 45, 1),
    (15, "A", N5, "outbound", "answered", 200, 1),
    (16, "B", N6, "outbound", "no_answer", 0, 1),
    (17, "A", N3, "outbound", "answered", 75, 1),
    (18, "B", N1, "outbound", "no_answer", 0, 1),
    (19, "A", N1, "inbound", "answered", 30, 1),
    (20, "B", N5, "inbound", "no_answer", 0, 1),
    # Wednesday
    (21, "A", N4, "outbound", "no_answer", 0, 2),
    (22, "B", N6, "inbound", "no_answer", 0, 2),
    (23, "A", N2, "outbound", "answered", 150, 2),
    (24, "B", N3, "inbound", "answered", 60, 2),
    (25, "A", N5, "outbound", "answered", 90, 2),
    (26, "B", N1, "inbound", "answered", 45, 2),
    (27, "A", N6, "outbound", "no_answer", 0, 2),
    (28, "B", N2, "outbound", "answered", 30, 2),
    (29, "A", N3, "outbound", "no_answer", 0, 2),
    (30, "B", N5, "outbound", "answered", 120, 2),
    # Thursday
    (31, "A", N1, "outbound", "answered", 60, 3),
    (32, "B", N4, "inbound", "no_answer", 0, 3),
    (33, "A", N2, "inbound", "answered", 90, 3),
    (34, "B", N6, "inbound", "no_answer", 0, 3),
    (35, "A", N5, "inbound", "answered", 30, 3),
    (36, "B", N3, "outbound", "no_answer", 0, 3),
    (37, "A", N1, "inbound", "no_answer", 0, 3),
    (38, "B", N2, "outbound", "answered", 60, 3),
    (39, "A", N4, "outbound", "no_answer", 0, 3),
    (40, "B", N5, "outbound", "answered", 45, 3),
]


def seed_fixture_calls(company: Company, op_a: OperatorProfile, op_b: OperatorProfile) -> None:
    operators = {"A": op_a, "B": op_b}
    records = []
    for num, op_key, number, call_type, call_status, duration, day in CALLS:
        start = BASE + timedelta(days=day, minutes=num)  # order == call number
        operator = operators[op_key]
        records.append(
            CallRecord(
                company=company,
                operator=operator,
                call_id=f"fx-{num}",
                call_type=call_type,
                call_status=call_status,
                from_number=number if call_type == "inbound" else "+998990000000",
                to_number="+998990000000" if call_type == "inbound" else number,
                counterparty_number=number,
                counterparty_name=f"Client {number[-1]}",
                sim_slot=0,
                duration=duration,
                start_time=start,
                end_time=start + timedelta(seconds=duration),
            )
        )
    CallRecord.all_objects.bulk_create(records)
