"""Aggregate call statistics for a company.

Returns only NON-PII aggregates (counts, sums, daily series) so the same
figures can safely feed both the admin console and the partner portal — the
partner boundary (no CallRecords/Users/operators exposed) is respected by
keeping ``include_operators`` off for integrators.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.companies.models import Company

from .models import CallRecord


def company_call_stats(company: Company, *, include_operators: bool = False) -> dict[str, Any]:
    now = timezone.now()
    qs = CallRecord.all_objects.filter(company=company)

    agg = qs.aggregate(
        total=Count("id"),
        answered=Count("id", filter=Q(call_status=CallRecord.CallStatus.ANSWERED)),
        inbound=Count("id", filter=Q(call_type=CallRecord.CallType.INBOUND)),
        outbound=Count("id", filter=Q(call_type=CallRecord.CallType.OUTBOUND)),
        total_duration=Sum("duration"),
        avg_duration=Avg("duration", filter=Q(call_status=CallRecord.CallStatus.ANSWERED)),
    )
    total = agg["total"] or 0
    answered = agg["answered"] or 0

    # 30-day daily volume (answered vs missed split for a stacked chart).
    since = now - timedelta(days=30)
    day_rows = (
        qs.filter(start_time__gte=since)
        .annotate(day=TruncDate("start_time"))
        .values("day")
        .annotate(
            n=Count("id"),
            ok=Count("id", filter=Q(call_status=CallRecord.CallStatus.ANSWERED)),
        )
        .values_list("day", "n", "ok")
    )
    by_day = {row[0]: (row[1], row[2]) for row in day_rows}
    daily_series: list[dict[str, Any]] = []
    for offset in range(29, -1, -1):
        day = (now - timedelta(days=offset)).date()
        n, ok = by_day.get(day, (0, 0))
        daily_series.append(
            {"date": day.isoformat(), "total": int(n), "answered": int(ok), "missed": int(n - ok)}
        )

    first_at = qs.aggregate(first=Min("start_time"))["first"]

    stats: dict[str, Any] = {
        "total_calls": total,
        "answered": answered,
        "missed": total - answered,
        "answer_rate": round(answered / total * 100) if total else 0,
        "inbound": agg["inbound"] or 0,
        "outbound": agg["outbound"] or 0,
        "total_duration_sec": int(agg["total_duration"] or 0),
        "avg_duration_sec": int(agg["avg_duration"] or 0),
        "calls_30d": sum(d["total"] for d in daily_series),
        "operator_count": qs.filter(operator__isnull=False)
        .values("operator")
        .distinct()
        .count(),
        "first_call_at": first_at.isoformat() if first_at else None,
        "daily_series": daily_series,
    }

    if include_operators:
        top = (
            qs.filter(operator__isnull=False)
            .values("operator", "operator__full_name", "operator__user_name")
            .annotate(
                calls=Count("id"),
                answered=Count("id", filter=Q(call_status=CallRecord.CallStatus.ANSWERED)),
            )
            .order_by("-calls")[:5]
        )
        stats["top_operators"] = [
            {
                "id": row["operator"],
                "name": row["operator__full_name"] or row["operator__user_name"] or "—",
                "calls": row["calls"],
                "answered": row["answered"],
            }
            for row in top
        ]

    return stats
