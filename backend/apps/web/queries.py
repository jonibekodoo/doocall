"""Shared SQL-side query helpers for dashboard/calls/reports.

EVERYTHING aggregates in the database (annotate/aggregate/window) — no
Python loops over full querysets (Phase-5 hard requirement).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count, Max, Q, QuerySet, Sum
from django.utils import timezone

from apps.calls.models import CallRecord
from apps.core.tz import company_tz

ANSWERED = Q(call_status=CallRecord.CallStatus.ANSWERED)
MISSED = Q(call_status=CallRecord.CallStatus.NO_ANSWER)
INBOUND = Q(call_type=CallRecord.CallType.INBOUND)
OUTBOUND = Q(call_type=CallRecord.CallType.OUTBOUND)
# Same predicates spelled from a related model (OperatorProfile.call_records).
ANSWERED_REL = Q(call_records__call_status=CallRecord.CallStatus.ANSWERED)
MISSED_REL = Q(call_records__call_status=CallRecord.CallStatus.NO_ANSWER)

PERIODS = {"today": 0, "3d": 3, "7d": 7}


def period_start(period: str, now: datetime | None = None) -> datetime:
    now = now or timezone.now()
    days = PERIODS.get(period, 0)
    if days == 0:
        # "Today" begins at midnight in the COMPANY's zone, not UTC.
        return now.astimezone(company_tz()).replace(hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=days)


def scoped_calls(
    *, operator_id: int | None = None, since: datetime | None = None
) -> QuerySet[CallRecord]:
    # TenantManager → company-scoped in CabinetView.
    qs: QuerySet[CallRecord] = CallRecord.objects.all()
    if operator_id is not None:
        qs = qs.filter(operator_id=operator_id)
    if since is not None:
        qs = qs.filter(start_time__gte=since)
    return qs


def direction_status_matrix(qs: QuerySet[CallRecord]) -> dict[str, Any]:
    """all/in/out × total/answered/missed — one aggregate query."""
    agg = qs.aggregate(
        total=Count("id"),
        answered=Count("id", filter=ANSWERED),
        missed=Count("id", filter=MISSED),
        in_total=Count("id", filter=INBOUND),
        in_answered=Count("id", filter=INBOUND & ANSWERED),
        in_missed=Count("id", filter=INBOUND & MISSED),
        out_total=Count("id", filter=OUTBOUND),
        out_answered=Count("id", filter=OUTBOUND & ANSWERED),
        out_missed=Count("id", filter=OUTBOUND & MISSED),
        duration=Sum("duration"),
    )
    return {
        "all": {
            "total": agg["total"],
            "answered": agg["answered"],
            "missed": agg["missed"],
        },
        "inbound": {
            "total": agg["in_total"],
            "answered": agg["in_answered"],
            "missed": agg["in_missed"],
        },
        "outbound": {
            "total": agg["out_total"],
            "answered": agg["out_answered"],
            "missed": agg["out_missed"],
        },
        "total_duration_sec": agg["duration"] or 0,
    }


def latest_call_per_number(qs: QuerySet[CallRecord]) -> QuerySet[CallRecord]:
    """Rows that ARE the most recent call of their counterparty number.

    Postgres ``DISTINCT ON`` — one index-ordered scan instead of a correlated
    per-row subquery (the subquery version blew the 300ms perf budget at 12k
    rows).
    """
    # Materialize the id list (one id per distinct client — bounded the same
    # way as the per-client report). A nested `pk IN (DISTINCT ON …)` subquery
    # is planner-fragile: fast with fresh stats, ~30× slower once they drift.
    latest_ids = list(
        qs.order_by("counterparty_number", "-start_time")
        .distinct("counterparty_number")
        .values_list("pk", flat=True)
    )
    return qs.filter(pk__in=latest_ids)


def unanswered_now(qs: QuerySet[CallRecord]) -> QuerySet[CallRecord]:
    """The §6.4 semantic: a number is 'unanswered' iff its LAST call is
    no_answer — it drops off the list as soon as a successful call happens.

    Returns plain rows (no per-row subquery annotations — those blow the perf
    budget at 12k rows). Use :func:`unanswered_enrichment` on the bounded
    result page for last-success / attempt counts.
    """
    return (
        latest_call_per_number(qs)
        .filter(call_status=CallRecord.CallStatus.NO_ANSWER)
        .order_by("-start_time")
    )


def unanswered_enrichment(
    rows: list[CallRecord],
) -> tuple[dict[str, Any], dict[str, int]]:
    """last-success timestamp + attempts-since-success per number.

    Two grouped queries over ONLY the page's numbers — SQL aggregation on a
    bounded set, never a full-table Python loop.
    """
    numbers = [r.counterparty_number for r in rows]
    last_success = dict(
        CallRecord.objects.filter(
            counterparty_number__in=numbers,
            call_status=CallRecord.CallStatus.ANSWERED,
        )
        .values("counterparty_number")
        .annotate(last=Max("start_time"))
        .values_list("counterparty_number", "last")
    )
    since_q = Q(pk=None)
    for number in numbers:
        cond = Q(counterparty_number=number, call_status=CallRecord.CallStatus.NO_ANSWER)
        if number in last_success:
            cond &= Q(start_time__gt=last_success[number])
        since_q |= cond
    attempts = dict(
        CallRecord.objects.filter(since_q)
        .values("counterparty_number")
        .annotate(n=Count("id"))
        .values_list("counterparty_number", "n")
    )
    return last_success, attempts
