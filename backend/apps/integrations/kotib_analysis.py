"""Kotib AI analysis results (``analysis.completed`` webhook) — parsing,
sanitizing, matching to our CallRecord and storage.

The webhook is reached through a per-company secret URL
(``/api/public/kotib/analysis/<token>``, token in the Kotib integration's
``config["analysis_token"]``) and, once the company saved the secret Kotib
gave them (``config["analysis_secret"]``), must carry a valid
``X-Kotib-Signature``. Kotib's spec does not name the algorithm; we assume
hex HMAC-SHA256 of the raw request body (optionally prefixed ``sha256=``) —
the convention of DooCall's own X-Doocall-Signature.

Nothing here logs the token, the secret or any transcript text.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import nh3
from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core.phone import normalize_phone

from .models import CallAnalysis, CrmIntegration

EVENT = "analysis.completed"
MAX_BODY_BYTES = 2 * 1024 * 1024
MATCH_WINDOW = timedelta(seconds=120)

# Kotib's comment "HTML card": structure only — no attributes, links, images
# or styles survive.
ALLOWED_TAGS = {
    "div", "p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li", "span",
    "table", "thead", "tbody", "tr", "td", "th", "h4", "h5", "small",
}  # fmt: skip


class PayloadError(ValueError):
    """The body is not a usable analysis.completed message (→ 400)."""


def new_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_token(integration: CrmIntegration) -> str:
    """The integration's webhook token, created (and saved) if missing."""
    token = str(integration.config.get("analysis_token") or "")
    if not token:
        token = new_token()
        integration.config = {**integration.config, "analysis_token": token}
        integration.save(update_fields=["config", "updated_at"])
    return token


def webhook_url(company: Company, token: str) -> str:
    scheme = getattr(settings, "URL_SCHEME", "https")
    return f"{scheme}://{company.slug}.{settings.DOMAIN_ROOT}/api/public/kotib/analysis/{token}"


def find_integration(token: str) -> CrmIntegration | None:
    """Kotib integration (any state) owning ``token`` — constant-time check."""
    if not token:
        return None
    integration = (
        CrmIntegration.all_objects.filter(
            provider=CrmIntegration.Provider.KOTIB, config__analysis_token=token
        )
        .select_related("company")
        .first()
    )
    if integration is None:
        return None
    stored = str(integration.config.get("analysis_token") or "")
    if not stored or not hmac.compare_digest(stored.encode(), token.encode()):
        return None
    found: CrmIntegration = integration
    return found


def signature_ok(secret: str, body: bytes, header: str) -> bool:
    given = (header or "").strip()
    if given.lower().startswith("sha256="):
        given = given[len("sha256=") :]
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(given) and hmac.compare_digest(expected, given.lower())


def sanitize_html(value: Any) -> str:
    return nh3.clean(str(value or ""), tags=ALLOWED_TAGS, attributes={}, link_rel=None)


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _when(value: Any, field: str) -> datetime:
    parsed = parse_datetime(str(value or ""))
    if parsed is None or parsed.tzinfo is None:
        raise PayloadError(f"{field} must be an ISO-8601 date-time with offset")
    return parsed


def _optional_int(value: Any, field: str) -> int | None:
    return None if value is None else _int(value, field)


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise PayloadError(f"{field} must be a number")
    try:
        return int(value)
    except ValueError:
        raise PayloadError(f"{field} must be a number") from None


def _prompt_scores(raw: Any) -> list[dict[str, Any]]:
    rows = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        score = _number(item.get("score"))
        rows.append(
            {
                "key": str(item.get("key") or ""),
                "name": str(item.get("name") or ""),
                "score": float(score) if score is not None else None,
                "comment": sanitize_html(item.get("comment")),
                "is_violation": bool(item.get("is_violation")),
            }
        )
    return rows


def _answers(raw: Any) -> list[dict[str, Any]]:
    return [
        {"key": str(a.get("key") or ""), "name": str(a.get("name") or ""), "value": a.get("value")}
        for a in (raw if isinstance(raw, list) else [])
        if isinstance(a, dict)
    ]


def match_call(company: Company, phone: str, start: datetime, end: datetime) -> CallRecord | None:
    """Our call with the same counterparty within ±120 s of Kotib's start
    (nearest wins). When Kotib only knows the end (start == end), the call's
    start + duration is compared with the end instead."""
    if not phone:
        return None
    end_only = start == end
    since = start - (timedelta(hours=6) if end_only else MATCH_WINDOW)
    candidates = CallRecord.all_objects.filter(
        company=company,
        counterparty_number=phone,
        start_time__gte=since,
        start_time__lte=start + MATCH_WINDOW,
    ).only("id", "start_time", "duration")

    def distance(record: CallRecord) -> float:
        by_start = abs((record.start_time - start).total_seconds())
        if not end_only:
            return by_start
        call_end = record.start_time + timedelta(seconds=record.duration or 0)
        return min(by_start, abs((call_end - end).total_seconds()))

    best = min(candidates, key=distance, default=None)
    if best is None or distance(best) > MATCH_WINDOW.total_seconds():
        return None
    match: CallRecord = best
    return match


def store(company: Company, payload: dict[str, Any], *, verified: bool) -> CallAnalysis:
    """Upsert the analysis for (company, audio_data_id) — latest wins."""
    audio_data_id = _int(payload.get("audio_data_id"), "audio_data_id")
    start = _when(payload.get("start_time"), "start_time")
    end = _when(payload.get("end_time") or payload.get("start_time"), "end_time")
    raw_client = payload.get("client_data")
    client: dict[str, Any] = raw_client if isinstance(raw_client, dict) else {}
    phone = normalize_phone(str(client.get("phone_number") or ""), company.phone_code)
    scores = _prompt_scores(payload.get("prompt_scores"))
    fields = {
        "audio_file_id": _optional_int(payload.get("audio_file_id"), "audio_file_id"),
        "start_time": start,
        "end_time": end,
        "final_score": _number(payload.get("final_score")),
        "conversation_text": str(payload.get("conversation_text") or ""),
        "prompt_scores": scores,
        "client_phone": phone[:32],
        "client_summary": str(client.get("summary") or ""),
        "client_answers": _answers(client.get("answers")),
        "has_violation": any(
            s["is_violation"] and s["score"] is not None and s["score"] < 0 for s in scores
        ),
        "signature_verified": verified,
    }
    analysis: CallAnalysis | None = CallAnalysis.all_objects.filter(
        company=company, audio_data_id=audio_data_id
    ).first()
    if analysis is None:
        analysis = CallAnalysis(company=company, audio_data_id=audio_data_id)
    for name, value in fields.items():
        setattr(analysis, name, value)
    if analysis.call_id is None:
        analysis.call = match_call(company, phone, start, end)
    analysis.save()
    return analysis


def ai_marks(call_ids: list[int]) -> dict[int, dict[str, Any]]:
    """call id → ``{"analysis_id", "final_score"}`` of its latest analysis
    (for the calls list/detail ``ai`` field)."""
    marks: dict[int, dict[str, Any]] = {}
    rows = (
        CallAnalysis.objects.filter(call_id__in=call_ids)
        .order_by("call_id", "-updated_at", "-id")
        .values_list("call_id", "id", "final_score")
    )
    for call_id, analysis_id, score in rows:
        marks.setdefault(
            call_id,
            {
                "analysis_id": analysis_id,
                "final_score": float(score) if score is not None else None,
            },
        )
    return marks
