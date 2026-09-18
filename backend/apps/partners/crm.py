"""Shared CRM helpers used by both the sales-manager and admin portals."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

import re

from apps.accounts.models import User
from apps.api.errors import ApiError, ErrorCode
from apps.core.phone import normalize_phone

from .models import CrmTask, Lead, LeadEvent, PipelineStage


def _phone_key(raw: str | None) -> str:
    """Duplicate key for a phone: digits only, last 9 (UZ national number).

    "+998 90 123-45-67", "998901234567" and "90 123 45 67" all map to
    "901234567", so separators / country-code presence never hide a duplicate.
    """
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", normalize_phone(raw) or raw)
    return digits[-9:] if len(digits) >= 9 else digits


def check_duplicates(
    phone: str | None = None, company: str | None = None, *, exclude_pk: int | None = None
) -> None:
    """Reject a lead whose phone or company name already exists in the CRM.

    Phone is compared in normalized (E.164-like) form; company case-insensitively.
    Pass only the fields being written — empty/None values are skipped.
    """
    qs = Lead.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if phone and phone.strip():
        key = _phone_key(phone)
        if key:
            # Stored phones are free-text (spaces/dashes), so a DB substring
            # prefilter is unreliable — compare normalised keys in Python.
            for other in qs.exclude(phone="").only("pk", "full_name", "phone"):
                if _phone_key(other.phone) == key:
                    raise ApiError(
                        ErrorCode.MISSING_FIELD,
                        f"Bu telefon raqam CRM'da allaqachon mavjud: {other.full_name}",
                        400,
                    )
    if company and company.strip():
        other = qs.filter(company__iexact=company.strip()).only("pk", "full_name").first()
        if other is not None:
            raise ApiError(
                ErrorCode.MISSING_FIELD,
                f"Bu kompaniya CRM'da allaqachon mavjud: {other.full_name}",
                400,
            )

# Lead text fields a user may edit inline (logged individually).
EDITABLE_FIELDS = ("full_name", "contact_name", "phone", "email", "company", "note")


def _actor_name(user: User | None) -> str:
    if user is None:
        return "System"
    return user.get_full_name() or user.email or user.username


def log_event(
    lead: Lead,
    kind: str,
    actor: User | None,
    *,
    text: str = "",
    task: CrmTask | None = None,
) -> LeadEvent:
    return LeadEvent.objects.create(lead=lead, kind=kind, actor=actor, text=text, task=task)


def _task_body(task: CrmTask) -> dict[str, Any]:
    return {
        "id": task.pk,
        "title": task.title,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "is_done": task.is_done,
        "auto": task.auto,
        "responsible": task.sales_manager.name if task.sales_manager_id else None,
        "type": {"id": task.type_id, "name": task.type.name, "icon": task.type.icon}
        if task.type_id
        else None,
    }


def event_body(e: LeadEvent) -> dict[str, Any]:
    return {
        "id": e.pk,
        "kind": e.kind,
        "text": e.text,
        "actor": _actor_name(e.actor),
        "created_at": e.created_at.isoformat(),
        "task": _task_body(e.task) if e.task_id else None,
    }


def lead_task_state(lead: Lead, *, now: datetime | None = None) -> dict[str, Any]:
    """Nearest open task's due state for the card badge."""
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    task = (
        lead.tasks.filter(is_done=False, is_cancelled=False)
        .order_by("due_at")
        .only("due_at")
        .first()
    )
    if task is None:
        return {"kind": "none", "days": 0}
    if task.due_at is None:
        return {"kind": "nodue", "days": 0}
    delta = (timezone.localtime(task.due_at).date() - today).days
    if delta == 0:
        return {"kind": "today", "days": 0}
    if delta > 0:
        return {"kind": "left", "days": delta}
    return {"kind": "overdue", "days": -delta}


def lead_card(lead: Lead) -> dict[str, Any]:
    return {
        "id": lead.pk,
        "full_name": lead.full_name,
        "company": lead.company,
        "phone": lead.phone,
        "stage_id": lead.stage_id,
        "priority": lead.priority,
        "source": {"id": lead.source_id, "name": lead.source.name} if lead.source_id else None,
        "tags": [{"id": t.pk, "name": t.name, "color": t.color} for t in lead.tags.all()],
        "sales_manager": lead.sales_manager.name if lead.sales_manager_id else None,
        "sales_manager_id": lead.sales_manager_id,
        "task_state": lead_task_state(lead),
    }


def lead_detail(lead: Lead) -> dict[str, Any]:
    body = lead_card(lead)
    body.update(
        {
            "contact_name": lead.contact_name,
            "email": lead.email,
            "source_id": lead.source_id,
            "tag_ids": list(lead.tags.values_list("id", flat=True)),
            "note": lead.note,
            "pipeline_id": lead.pipeline_id,
            "created_at": lead.created_at.isoformat(),
            "events": [event_body(e) for e in lead.events.select_related("actor", "task__sales_manager")],
            "open_tasks": [
                _task_body(t)
                for t in lead.tasks.filter(is_done=False, is_cancelled=False).select_related(
                    "sales_manager", "type"
                )
            ],
        }
    )
    return body


FIELD_LABELS = {
    "full_name": "Nomi",
    "contact_name": "Kontakt",
    "phone": "Telefon",
    "email": "Email",
    "company": "Kompaniya",
    "note": "Izoh",
    "priority": "Muhimlik",
    "source": "Manba",
    "tags": "Teglar",
}


def _fmt(v: Any) -> str:
    v = (str(v).strip() if v is not None else "")
    return v or "—"


def apply_fields(lead: Lead, data: dict[str, Any], actor: User | None) -> None:
    """Set fields, logging a 'was → became' change line per field."""
    # No duplicate phone / company across the CRM (only for the fields being changed).
    check_duplicates(
        phone=data.get("phone") if "phone" in data else None,
        company=data.get("company") if "company" in data else None,
        exclude_pk=lead.pk,
    )
    changes: list[str] = []
    for f in EDITABLE_FIELDS:
        if f in data:
            new = (data[f] or "").strip()
            old = getattr(lead, f)
            if new != old:
                setattr(lead, f, new)
                changes.append(f"{FIELD_LABELS.get(f, f)}: {_fmt(old)} → {_fmt(new)}")
    if "priority" in data:
        try:
            p = max(0, min(3, int(data["priority"])))
            if p != lead.priority:
                changes.append(f"{FIELD_LABELS['priority']}: {lead.priority} → {p}")
                lead.priority = p
        except (TypeError, ValueError):
            pass
    if "source_id" in data:
        from .models import LeadSource

        sid = data["source_id"]
        new_source = LeadSource.objects.filter(pk=sid).first() if sid else None
        if (new_source.pk if new_source else None) != lead.source_id:
            old_name = lead.source.name if lead.source_id else "—"
            changes.append(f"{FIELD_LABELS['source']}: {old_name} → {new_source.name if new_source else '—'}")
            lead.source = new_source
    if changes:
        lead.save()
    if "tag_ids" in data:
        from .models import LeadTag

        old_tags = set(lead.tags.values_list("name", flat=True))
        ids = data["tag_ids"] or []
        new_qs = LeadTag.objects.filter(pk__in=ids)
        new_tags = {t.name for t in new_qs}
        if new_tags != old_tags:
            lead.tags.set(new_qs)
            changes.append(
                f"{FIELD_LABELS['tags']}: {', '.join(sorted(old_tags)) or '—'} → {', '.join(sorted(new_tags)) or '—'}"
            )
    for line in changes:
        log_event(lead, LeadEvent.Kind.FIELD, actor, text=line)


def move_to_stage(lead: Lead, stage: PipelineStage, actor: User | None) -> None:
    if lead.stage_id == stage.pk:
        return
    old_name = lead.stage.name if lead.stage_id else "—"
    lead.stage = stage
    lead.save(update_fields=["stage", "updated_at"])
    log_event(lead, LeadEvent.Kind.STAGE, actor, text=f"{old_name} → {stage.name}")


def add_note(lead: Lead, actor: User | None, text: str) -> LeadEvent:
    return log_event(lead, LeadEvent.Kind.NOTE, actor, text=text)


def _parse_due(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def add_task(
    lead: Lead, actor: User | None, title: str, due_raw: Any = None, type_id: Any = None
) -> CrmTask:
    from .models import CrmTaskType

    task_type = CrmTaskType.objects.filter(pk=type_id).first() if type_id else None
    title = (title or "").strip() or (task_type.name if task_type else "Topshiriq")
    task = CrmTask.objects.create(
        sales_manager=lead.sales_manager,
        lead=lead,
        title=title,
        due_at=_parse_due(due_raw),
        type=task_type,
        created_by=actor,
    )
    log_event(lead, LeadEvent.Kind.TASK, actor, text=title, task=task)
    return task


def complete_task(task: CrmTask, actor: User | None) -> None:
    if task.is_done:
        return
    task.is_done = True
    task.save(update_fields=["is_done"])
    if task.lead_id:
        log_event(task.lead, LeadEvent.Kind.TASK_DONE, actor, text=task.title, task=task)


def cancel_task(task: CrmTask, actor: User | None, reason: str) -> None:
    if task.is_cancelled or task.is_done:
        return
    task.is_cancelled = True
    task.cancel_reason = reason
    task.save(update_fields=["is_cancelled", "cancel_reason"])
    if task.lead_id:
        log_event(
            task.lead,
            LeadEvent.Kind.TASK_CANCELLED,
            actor,
            text=f"{task.title}: {reason}" if reason else task.title,
            task=task,
        )


def edit_task(task: CrmTask, data: dict[str, Any]) -> None:
    from .models import CrmTaskType

    changed = False
    if "title" in data and (data["title"] or "").strip():
        task.title = data["title"].strip()
        changed = True
    if "due_at" in data:
        task.due_at = _parse_due(data["due_at"])
        changed = True
    if "type_id" in data:
        task.type = CrmTaskType.objects.filter(pk=data["type_id"]).first()
        changed = True
    if changed:
        task.save()


def apply_lead_filters(qs, params):
    """Shared lead search/filters for the CRM board (q, source, tag, priority, stage)."""
    from django.db.models import Q as _Q

    if pid := params.get("pipeline"):
        qs = qs.filter(pipeline_id=pid)
    if stage := params.get("stage"):
        qs = qs.filter(stage_id=stage)
    if src := params.get("source"):
        qs = qs.filter(source_id=src)
    if tag := params.get("tag"):
        qs = qs.filter(tags__id=tag)
    if prio := params.get("priority"):
        qs = qs.filter(priority=prio)
    if q := (params.get("q") or "").strip():
        qs = qs.filter(
            _Q(full_name__icontains=q) | _Q(company__icontains=q) | _Q(phone__icontains=q)
        )
    return qs.distinct()


def board_stats(leads_qs, tasks_qs, *, now: datetime | None = None) -> dict[str, int]:
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    yesterday = today - timedelta(days=1)
    open_tasks = tasks_qs.filter(is_done=False, is_cancelled=False)
    total_leads = leads_qs.count()
    with_open_task = leads_qs.filter(tasks__is_done=False, tasks__is_cancelled=False).distinct().count()
    return {
        "today_tasks": open_tasks.filter(due_at__date=today).count(),
        "no_task_leads": max(total_leads - with_open_task, 0),
        "overdue_tasks": open_tasks.filter(due_at__date__lt=today).count(),
        "leads_today": leads_qs.filter(created_at__date=today).count(),
        "leads_yesterday": leads_qs.filter(created_at__date=yesterday).count(),
    }


# ── Task Kanban buckets (overdue / today / tomorrow / planned) ──────────────
def task_bucket(task: CrmTask, *, now: datetime | None = None) -> str:
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    if task.due_at is None:
        return "planned"
    due = timezone.localtime(task.due_at).date()
    if due < today:
        return "overdue"
    if due == today:
        return "today"
    if due == today + timedelta(days=1):
        return "tomorrow"
    return "planned"
