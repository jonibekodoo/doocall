"""§6.1 Dashboard — period stats, per-operator activity, latest/unanswered."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q, Sum
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import OperatorProfile
from apps.calls.models import CallRecord

from . import queries
from .permissions import CabinetView


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def call_row(record: CallRecord) -> dict[str, Any]:
    return {
        "id": record.pk,
        "call_id": record.call_id,
        "direction": record.call_type,
        "status": record.call_status,
        "operator_id": record.operator_id,
        "operator_name": (
            (record.operator.full_name or record.operator.user_name) if record.operator else None
        ),
        "operator_number": record.operator_number,
        "counterparty_number": record.counterparty_number,
        "counterparty_name": record.resolved_name or record.counterparty_name,
        "duration": record.duration,
        "start_time": record.start_time.isoformat(),
    }


class DashboardView(CabinetView):
    @extend_schema(summary="Dashboard stats (period=today|3d|7d, operator=<id>)")
    def get(self, request: Request) -> Response:
        period = request.query_params.get("period", "today")
        operator_id = _int_or_none(request.query_params.get("operator"))
        since = queries.period_start(period)
        qs = queries.scoped_calls(operator_id=operator_id, since=since)

        general = queries.direction_status_matrix(qs)

        per_operator = list(
            OperatorProfile.objects.filter(is_active=True)
            .annotate(
                total=Count("call_records", filter=Q(call_records__start_time__gte=since)),
                answered=Count(
                    "call_records",
                    filter=Q(call_records__start_time__gte=since) & queries.ANSWERED_REL,
                ),
                missed=Count(
                    "call_records",
                    filter=Q(call_records__start_time__gte=since) & queries.MISSED_REL,
                ),
                duration=Sum(
                    "call_records__duration",
                    filter=Q(call_records__start_time__gte=since),
                ),
            )
            .values("id", "user_name", "full_name", "total", "answered", "missed", "duration")
            .order_by("-total")
        )
        for row in per_operator:
            row["duration"] = row["duration"] or 0

        latest = [
            call_row(r)
            for r in qs.filter(call_status=CallRecord.CallStatus.ANSWERED).order_by("-start_time")[
                :10
            ]
        ]
        unanswered_rows = list(queries.unanswered_now(qs)[:10])
        _, attempts = queries.unanswered_enrichment(unanswered_rows)
        unanswered = [
            {**call_row(r), "total_missed": attempts.get(r.counterparty_number, 0)}
            for r in unanswered_rows
        ]

        return Response(
            {
                "success": True,
                "period": period,
                "general": general,
                "per_operator": per_operator,
                "latest_calls": latest,
                "unanswered_now": unanswered,
            }
        )
