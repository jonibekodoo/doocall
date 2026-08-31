"""§6.4 Reports — one endpoint per report, ALL aggregation in SQL."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, F, Max, Sum
from django.db.models.functions import (
    ExtractIsoWeekDay,
    Round,
    TruncDay,
    TruncMonth,
    TruncWeek,
)
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from . import queries
from .permissions import CabinetView
from .views_calls import filtered_calls

TRUNC = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}


def base_qs(request: Request) -> Any:
    """Tenant-scoped queryset honouring the shared filter params."""
    return filtered_calls(request.query_params)


class GeneralReportView(CabinetView):
    @extend_schema(summary="General stats (all/in/out × answered/missed + duration)")
    def get(self, request: Request) -> Response:
        return Response(
            {"success": True, "report": queries.direction_status_matrix(base_qs(request))}
        )


class WeekdayMatrixView(CabinetView):
    @extend_schema(summary="Weekday matrix (ISO weekday × direction/status)")
    def get(self, request: Request) -> Response:
        rows = list(
            base_qs(request)
            .annotate(weekday=ExtractIsoWeekDay("start_time"))
            .values("weekday")
            .annotate(
                total=Count("id"),
                inbound=Count("id", filter=queries.INBOUND),
                outbound=Count("id", filter=queries.OUTBOUND),
                answered=Count("id", filter=queries.ANSWERED),
                missed=Count("id", filter=queries.MISSED),
            )
            .order_by("weekday")
        )
        return Response({"success": True, "report": rows})


class PeriodCountsView(CabinetView):
    @extend_schema(summary="Counts grouped by day|week|month (+unique numbers flag)")
    def get(self, request: Request) -> Response:
        group = request.query_params.get("group", "day")
        trunc = TRUNC.get(group, TruncDay)
        unique = request.query_params.get("unique", "").lower() in ("1", "true", "yes")

        qs = (
            base_qs(request)
            .annotate(bucket=trunc("start_time"))
            .values("bucket")
            .annotate(
                total=Count("counterparty_number", distinct=True) if unique else Count("id"),
                answered=Count("id", filter=queries.ANSWERED),
                missed=Count("id", filter=queries.MISSED),
            )
            .order_by("bucket")
        )
        rows = [
            {
                "bucket": row["bucket"].date().isoformat(),
                "total": row["total"],
                "answered": row["answered"],
                "missed": row["missed"],
            }
            for row in qs
        ]
        return Response({"success": True, "group": group, "unique_numbers": unique, "report": rows})


class PerEmployeeView(CabinetView):
    @extend_schema(summary="Per-employee distribution / answered-missed / duration minutes")
    def get(self, request: Request) -> Response:
        rows = list(
            base_qs(request)
            .exclude(operator=None)
            .values(
                "operator_id",
                user_name=F("operator__user_name"),
                full_name=F("operator__full_name"),
            )
            .annotate(
                total=Count("id"),
                inbound=Count("id", filter=queries.INBOUND),
                outbound=Count("id", filter=queries.OUTBOUND),
                answered=Count("id", filter=queries.ANSWERED),
                missed=Count("id", filter=queries.MISSED),
                duration_minutes=Round(Sum("duration") / 60.0, 1),
            )
            .order_by("-total")
        )
        return Response({"success": True, "report": rows})


class PerClientView(CabinetView):
    @extend_schema(summary="Per-client call distribution")
    def get(self, request: Request) -> Response:
        rows = list(
            base_qs(request)
            .values("counterparty_number")
            .annotate(
                name=Max(F("resolved_name")),
                device_name=Max(F("counterparty_name")),
                total=Count("id"),
                answered=Count("id", filter=queries.ANSWERED),
                missed=Count("id", filter=queries.MISSED),
                duration=Sum("duration"),
                last_call=Max("start_time"),
            )
            .order_by("-total")[:500]
        )
        for row in rows:
            row["name"] = row["name"] or row.pop("device_name", None)
            row["last_call"] = row["last_call"].isoformat()
        return Response({"success": True, "report": rows})


class UnansweredReportView(CabinetView):
    @extend_schema(summary="Unanswered clients — last call missed; drops off after a success")
    def get(self, request: Request) -> Response:
        page_rows = list(queries.unanswered_now(base_qs(request))[:200])
        last_success, attempts = queries.unanswered_enrichment(page_rows)

        report = [
            {
                "counterparty_number": row.counterparty_number,
                "name": row.resolved_name or row.counterparty_name,
                "last_attempt": row.start_time.isoformat(),
                "last_success": last_success[row.counterparty_number].isoformat()
                if row.counterparty_number in last_success
                else None,
                "attempts_since_success": attempts.get(row.counterparty_number, 0),
                "operator_id": row.operator_id,
            }
            for row in page_rows
        ]
        return Response({"success": True, "report": report})


class LastContactView(CabinetView):
    @extend_schema(summary="Last contact per client")
    def get(self, request: Request) -> Response:
        rows = queries.latest_call_per_number(base_qs(request)).order_by("-start_time")[:500]
        report = [
            {
                "call_record_id": row.pk,  # playback link for the cabinet UI
                "counterparty_number": row.counterparty_number,
                "name": row.resolved_name or row.counterparty_name,
                "last_call": row.start_time.isoformat(),
                "direction": row.call_type,
                "status": row.call_status,
                "operator_id": row.operator_id,
                "duration": row.duration,
            }
            for row in rows
        ]
        return Response({"success": True, "report": report})
