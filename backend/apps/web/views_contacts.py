"""§6.3 Contacts — CRUD, multi-phone, responsible user, create-from-call."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.api.errors import ApiError, ErrorCode
from apps.calls.models import CallRecord, Contact, ContactPhone
from apps.core.phone import normalize_phone

from .permissions import CabinetView
from .views_dashboard import call_row

PAGE_SIZE = 30


def _resolve_responsible(value: Any) -> User | None:
    if not value:
        return None
    user: User | None = User.tenant_objects.filter(pk=value).first()
    if user is None:
        raise ApiError(ErrorCode.MISSING_FIELD, "responsible user not found", 400)
    return user


def contact_body(contact: Contact) -> dict[str, Any]:
    return {
        "id": contact.pk,
        "name": contact.name,
        "note": contact.note,
        "responsible_id": contact.responsible_id,
        "phones": [p.number for p in contact.phones.all()],
        "created_at": contact.created_at.isoformat(),
    }


def save_phones(contact: Contact, phones: list[str]) -> None:
    normalized = [normalize_phone(p) for p in phones if normalize_phone(p)]
    contact.phones.all().delete()
    ContactPhone.objects.bulk_create(
        ContactPhone(contact=contact, number=n) for n in dict.fromkeys(normalized)
    )


def contact_calls(contact: Contact) -> Any:
    numbers = list(contact.phones.values_list("number", flat=True))
    return CallRecord.objects.filter(counterparty_number__in=numbers).order_by("-start_time")


class ContactsView(CabinetView):
    @extend_schema(summary="List/search contacts")
    def get(self, request: Request) -> Response:
        qs = Contact.objects.prefetch_related("phones").annotate(
            call_count=Count("phones__number", distinct=False)
        )
        if q := request.query_params.get("q", "").strip():
            qs = qs.filter(
                Q(name__icontains=q) | Q(phones__number__icontains=normalize_phone(q) or q)
            ).distinct()
        responsible = request.query_params.get("responsible")
        if responsible and responsible.isdigit():
            qs = qs.filter(responsible_id=int(responsible))
        try:
            page = max(1, int(request.query_params.get("page", "1")))
        except ValueError:
            page = 1
        total = qs.count()
        rows = [contact_body(c) for c in qs[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]]
        return Response({"success": True, "count": total, "page": page, "results": rows})

    @extend_schema(summary="Create contact (multi-phone)")
    def post(self, request: Request) -> Response:
        name = (request.data.get("name") or "").strip()
        phones = request.data.get("phones") or []
        if not name or not isinstance(phones, list):
            raise ApiError(ErrorCode.MISSING_FIELD, "name and phones[] required", 400)
        responsible = self._responsible(request.data.get("responsible_id"))
        with transaction.atomic():
            contact = Contact.all_objects.create(
                company=self.company,
                name=name,
                note=request.data.get("note") or "",
                responsible=responsible,
            )
            save_phones(contact, phones)
        return Response(
            {"success": True, "contact": contact_body(contact)}, status=http.HTTP_201_CREATED
        )

    def _responsible(self, value: Any) -> User | None:
        return _resolve_responsible(value)


class ContactDetailView(CabinetView):
    def _get(self, contact_id: int) -> Contact:
        contact: Contact | None = (
            Contact.objects.prefetch_related("phones").filter(pk=contact_id).first()
        )
        if contact is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "contact not found", 404)
        return contact

    @extend_schema(summary="Contact detail + call history")
    def get(self, request: Request, contact_id: int) -> Response:
        contact = self._get(contact_id)
        calls = [call_row(r) for r in contact_calls(contact)[:50]]
        return Response({"success": True, "contact": contact_body(contact), "calls": calls})

    @extend_schema(summary="Update contact")
    def put(self, request: Request, contact_id: int) -> Response:
        contact = self._get(contact_id)
        if name := (request.data.get("name") or "").strip():
            contact.name = name
        if "note" in request.data:
            contact.note = request.data.get("note") or ""
        if "responsible_id" in request.data:
            contact.responsible = _resolve_responsible(request.data.get("responsible_id"))
        contact.save()
        if isinstance(request.data.get("phones"), list):
            save_phones(contact, request.data["phones"])
            contact.refresh_from_db()
        return Response({"success": True, "contact": contact_body(self._get(contact_id))})

    @extend_schema(summary="Delete contact")
    def delete(self, request: Request, contact_id: int) -> Response:
        self._get(contact_id).delete()
        return Response({"success": True})


class ContactFromCallView(CabinetView):
    @extend_schema(summary="Create contact from a call (prefills + links history)")
    def post(self, request: Request, call_id: int) -> Response:
        record = CallRecord.objects.filter(pk=call_id).first()
        if record is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "call not found", 404)
        name = (request.data.get("name") or "").strip() or (
            record.counterparty_name or record.counterparty_number
        )
        number = normalize_phone(record.counterparty_number)
        existing = ContactPhone.objects.filter(contact__company=self.company, number=number).first()
        if existing is not None:
            raise ApiError(
                ErrorCode.MISSING_FIELD,
                f"number already belongs to contact {existing.contact_id}",
                http.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            contact = Contact.all_objects.create(company=self.company, name=name)
            ContactPhone.objects.create(contact=contact, number=number)
            # Past calls with this number now resolve to the new contact name.
            linked = CallRecord.objects.filter(counterparty_number=number).update(
                resolved_name=name
            )
        return Response(
            {
                "success": True,
                "contact": contact_body(contact),
                "linked_calls": linked,
            },
            status=http.HTTP_201_CREATED,
        )
