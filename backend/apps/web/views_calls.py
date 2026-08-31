"""§6.2 Calls list — filters, pagination, detail, export, delete, columns."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.request import Request
from rest_framework.response import Response

from apps.api import storage
from apps.api.errors import ApiError, ErrorCode
from apps.calls.models import CallRecord
from apps.core.phone import normalize_phone

from .models import DEFAULT_CALL_COLUMNS, CallColumnPreference, ExportJob
from .permissions import CabinetView
from .tasks import run_export
from .views_dashboard import call_row

PAGE_SIZE = 30
SORTABLE = {
    "duration": "duration",
    "-duration": "-duration",
    "date": "start_time",
    "-date": "-start_time",
}


def parse_date(value: str | None, *, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(
            ErrorCode.MISSING_FIELD, f"invalid date {value!r} (YYYY-MM-DD)", 400
        ) from None
    tz = ZoneInfo(settings.TIME_ZONE)
    return datetime.combine(day, time.max if end else time.min, tzinfo=tz)


def filtered_calls(params: Any) -> QuerySet[CallRecord]:
    """Apply the §6.2 filter set to the tenant-scoped queryset."""
    qs: QuerySet[CallRecord] = CallRecord.objects.select_related("operator").all()

    employees = params.get("employees", "")
    if employees:
        ids = [int(x) for x in employees.split(",") if x.strip().isdigit()]
        if ids:
            qs = qs.filter(operator_id__in=ids)
    if date_from := parse_date(params.get("date_from")):
        qs = qs.filter(start_time__gte=date_from)
    if date_to := parse_date(params.get("date_to"), end=True):
        qs = qs.filter(start_time__lte=date_to)
    if direction := params.get("direction"):
        qs = qs.filter(call_type=direction)
    if status_f := params.get("status"):
        qs = qs.filter(call_status=status_f)
    if search := params.get("search", "").strip():
        normalized = normalize_phone(search)
        qs = qs.filter(
            Q(counterparty_name__icontains=search)
            | Q(resolved_name__icontains=search)
            | Q(counterparty_number__icontains=normalized or search)
        )
    if (min_duration := params.get("min_duration")) and str(min_duration).isdigit():
        qs = qs.filter(duration__gte=int(min_duration))
    if (sim := params.get("sim_slot")) and str(sim).lstrip("-").isdigit():
        qs = qs.filter(sim_slot=int(sim))
    return qs


class CallsListView(CabinetView):
    @extend_schema(summary="Calls list — §6.2 filters, 30/page, sortable")
    def get(self, request: Request) -> Response:
        qs = filtered_calls(request.query_params)
        ordering = SORTABLE.get(request.query_params.get("ordering", "-date"), "-start_time")
        qs = qs.order_by(ordering)

        try:
            page = max(1, int(request.query_params.get("page", "1")))
        except ValueError:
            page = 1
        total = qs.count()
        pages = max(1, -(-total // PAGE_SIZE))
        offset = (page - 1) * PAGE_SIZE
        rows = [call_row(r) for r in qs[offset : offset + PAGE_SIZE]]

        return Response(
            {
                "success": True,
                "count": total,
                "page": page,
                "pages": pages,
                "page_size": PAGE_SIZE,
                "results": rows,
            }
        )


class CallDetailView(CabinetView):
    @extend_schema(summary="Call detail incl. presigned audio URLs")
    def get(self, request: Request, call_id: int) -> Response:
        record = CallRecord.objects.filter(pk=call_id).first()
        if record is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "call not found", http.HTTP_404_NOT_FOUND)
        audios = [
            {
                "kind": audio.kind,
                "filename": audio.filename,
                "size_bytes": audio.size_bytes,
                "url": storage.presigned_url(audio.object_key),
            }
            for audio in record.audios.all()
        ]
        body = call_row(record)
        body.update(
            {
                "from_number": record.from_number,
                "from_name": record.from_name,
                "to_number": record.to_number,
                "to_name": record.to_name,
                "operator_number": record.operator_number,
                "sim_slot": record.sim_slot,
                "end_time": record.end_time.isoformat() if record.end_time else None,
                "start_time_local": record.start_time_local,
                "latitude": record.latitude,
                "longitude": record.longitude,
                "address": record.address,
                "audios": audios,
            }
        )
        return Response({"success": True, "call": body})


class CallExportView(CabinetView):
    @extend_schema(summary="Start CSV/XLSX export (Celery), poll for link")
    def post(self, request: Request) -> Response:
        fmt = request.data.get("format", "csv")
        if fmt not in (ExportJob.Format.CSV, ExportJob.Format.XLSX):
            raise ApiError(ErrorCode.MISSING_FIELD, "format must be csv|xlsx", 400)
        filters = request.data.get("filters") or {}
        job = ExportJob.all_objects.create(
            company=self.company,
            requested_by=request.user,
            format=fmt,
            filters=filters,
        )
        run_export.delay(job.pk)
        return Response({"success": True, "export_id": job.pk}, status=http.HTTP_202_ACCEPTED)

    @extend_schema(summary="List my exports")
    def get(self, request: Request) -> Response:
        jobs = ExportJob.objects.filter(requested_by=request.user)[:20]
        return Response(
            {
                "success": True,
                "exports": [
                    {
                        "id": j.pk,
                        "status": j.status,
                        "format": j.format,
                        "row_count": j.row_count,
                        "created_at": j.created_at.isoformat(),
                        "url": storage.presigned_url(j.object_key) if j.object_key else None,
                    }
                    for j in jobs
                ],
            }
        )


class CallExportDetailView(CabinetView):
    @extend_schema(summary="Export status + download link")
    def get(self, request: Request, export_id: int) -> Response:
        job = ExportJob.objects.filter(pk=export_id).first()
        if job is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "export not found", 404)
        return Response(
            {
                "success": True,
                "id": job.pk,
                "status": job.status,
                "format": job.format,
                "row_count": job.row_count,
                "error": job.error,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "url": storage.presigned_url(job.object_key) if job.object_key else None,
            }
        )


class CallColumnsView(CabinetView):
    @extend_schema(summary="Get my calls-table column preferences")
    def get(self, request: Request) -> Response:
        pref = CallColumnPreference.objects.filter(user_id=request.user.pk).first()
        return Response(
            {"success": True, "columns": pref.columns if pref else DEFAULT_CALL_COLUMNS}
        )

    @extend_schema(summary="Set my calls-table column preferences")
    def put(self, request: Request) -> Response:
        columns = request.data.get("columns")
        if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
            raise ApiError(ErrorCode.MISSING_FIELD, "columns must be a list of strings", 400)
        CallColumnPreference.objects.update_or_create(
            user_id=request.user.pk, defaults={"columns": columns}
        )
        return Response({"success": True, "columns": columns})
