"""Cabinet AI analysis API — /api/web/v1/ai/* (Kotib analysis results).

Tenant-scoped like every CabinetView. A non-admin cabinet user who is also an
operator only sees analyses of their own (matched) calls; company admins and
other cabinet users see the whole company.
"""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Avg, Count, Q, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import OperatorProfile, User
from apps.api.errors import ApiError, ErrorCode
from apps.core.phone import normalize_phone
from apps.web.permissions import CabinetView
from apps.web.views_calls import parse_date

from .models import CallAnalysis, CrmIntegration

PAGE_SIZE = 30


def own_operator_id(user: User) -> int | None:
    """Operator id a non-admin operator user is limited to, else None."""
    if user.is_company_admin:
        return None
    profile = OperatorProfile.all_objects.filter(user=user).only("id").first()
    return profile.pk if profile else None


def visible_analyses(user: User) -> QuerySet[CallAnalysis]:
    qs: QuerySet[CallAnalysis] = CallAnalysis.objects.select_related("call", "call__operator")
    if (operator_id := own_operator_id(user)) is not None:
        qs = qs.filter(call__operator_id=operator_id)
    return qs


def _score(value: Any) -> float | None:
    return float(value) if value is not None else None


def analysis_row(analysis: CallAnalysis) -> dict[str, Any]:
    call = analysis.call
    operator = call.operator if call else None
    return {
        "id": analysis.pk,
        "call_id": analysis.call_id,
        "start_time": analysis.start_time.isoformat(),
        "operator": {"id": operator.pk, "full_name": operator.full_name or operator.user_name}
        if operator
        else None,
        "phone": analysis.client_phone,
        "final_score": _score(analysis.final_score),
        "summary": analysis.client_summary,
        "has_violation": analysis.has_violation,
    }


class AiStatusView(CabinetView):
    @extend_schema(summary="Is Kotib connected / are there analyses to show")
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        return Response(
            {
                "success": True,
                "kotib_connected": CrmIntegration.objects.filter(
                    provider=CrmIntegration.Provider.KOTIB, is_enabled=True
                ).exists(),
                "has_analyses": visible_analyses(user).exists(),
                "is_admin": bool(user.is_company_admin),
            }
        )


class AiAnalysesView(CabinetView):
    @extend_schema(summary="AI analyses list (filters, 30/page, summary)")
    def get(self, request: Request) -> Response:
        params = request.query_params
        qs = visible_analyses(cast(User, request.user))
        if date_from := parse_date(params.get("date_from")):
            qs = qs.filter(start_time__gte=date_from)
        if date_to := parse_date(params.get("date_to"), end=True):
            qs = qs.filter(start_time__lte=date_to)
        if employees := params.get("employees", ""):
            ids = [int(x) for x in employees.split(",") if x.strip().isdigit()]
            if ids:
                qs = qs.filter(call__operator_id__in=ids)
        for name, lookup in (("min_score", "final_score__gte"), ("max_score", "final_score__lte")):
            if raw := params.get(name):
                try:
                    qs = qs.filter(**{lookup: float(raw)})
                except ValueError:
                    raise ApiError(
                        ErrorCode.MISSING_FIELD, f"{name} must be a number", 400
                    ) from None
        if params.get("violations") in ("1", "true"):
            qs = qs.filter(has_violation=True)
        if search := params.get("search", "").strip():
            number = normalize_phone(search, self.company.phone_code) or search
            qs = qs.filter(Q(client_phone__icontains=number) | Q(client_phone__icontains=search))

        summary = qs.aggregate(
            count=Count("id"),
            avg_score=Avg("final_score"),
            violations=Count("id", filter=Q(has_violation=True)),
        )
        try:
            page = max(1, int(params.get("page", "1")))
        except ValueError:
            page = 1
        total = summary["count"]
        offset = (page - 1) * PAGE_SIZE
        rows = qs.order_by("-start_time", "-id")[offset : offset + PAGE_SIZE]
        return Response(
            {
                "success": True,
                "count": total,
                "pages": max(1, -(-total // PAGE_SIZE)),
                "page": page,
                "summary": {
                    "count": total,
                    "avg_score": round(float(summary["avg_score"]), 1)
                    if summary["avg_score"] is not None
                    else None,
                    "violations": summary["violations"],
                },
                "analyses": [analysis_row(a) for a in rows],
            }
        )


class AiAnalysisDetailView(CabinetView):
    @extend_schema(summary="One AI analysis: scores, comments, transcript, client data")
    def get(self, request: Request, analysis_id: int) -> Response:
        analysis = visible_analyses(cast(User, request.user)).filter(pk=analysis_id).first()
        if analysis is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "analysis not found", http.HTTP_404_NOT_FOUND)
        call = analysis.call
        body = analysis_row(analysis)
        body.update(
            {
                "end_time": analysis.end_time.isoformat(),
                "conversation_text": analysis.conversation_text,
                "prompt_scores": [
                    {
                        "key": item.get("key", ""),
                        "name": item.get("name", ""),
                        "score": item.get("score"),
                        # Sanitized on receipt (nh3, structural tags only).
                        "comment_html": item.get("comment", ""),
                        "is_violation": bool(item.get("is_violation")),
                    }
                    for item in analysis.prompt_scores or []
                ],
                "client_data": {
                    "phone_number": analysis.client_phone,
                    "summary": analysis.client_summary,
                    "answers": analysis.client_answers or [],
                },
                "call": {
                    "id": call.pk,
                    "duration": call.duration,
                    "direction": call.call_type,
                    "has_audio": call.audios.exists(),
                }
                if call
                else None,
                "signature_verified": analysis.signature_verified,
                "received_at": analysis.received_at.isoformat(),
            }
        )
        return Response({"success": True, "analysis": body})
