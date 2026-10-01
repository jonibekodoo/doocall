"""Sales-manager portal API — /api/sales/v1 (role=sales_manager).

A sales manager owns integrators and earns a commission on those integrators'
companies' payments. Commercial + aggregate data only (no company PII)."""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Count, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import OperatorProfile, User
from apps.api.errors import ApiError, ErrorCode
from apps.billing import services as billing
from apps.companies.models import Company

from . import crm, services
from .models import (
    CrmTask,
    Integrator,
    Lead,
    Pipeline,
    PipelineStage,
    PlatformNotification,
    SalesCommission,
    SalesManager,
    SalesPayoutRequest,
    ensure_global_pipelines,
    get_offer_document,
)
from .permissions import IsSalesManager


class SalesView(APIView):
    permission_classes = [IsSalesManager]

    @property
    def sales_manager(self) -> SalesManager:
        return cast(User, self.request.user).sales_manager_profile


def _manager_companies(manager: SalesManager):
    return Company.objects.filter(integrator__sales_manager=manager)


class SalesDashboardView(SalesView):
    @extend_schema(summary="Sales manager dashboard")
    def get(self, request: Request) -> Response:
        m = self.sales_manager
        integrators = Integrator.objects.filter(sales_manager=m)
        companies = _manager_companies(m)

        status_counts = dict(
            companies.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )
        now = timezone.now()
        expired = companies.filter(
            status=Company.Status.TRIAL, trial_ends_at__lt=now
        ).count()
        operators = OperatorProfile.all_objects.filter(
            company__integrator__sales_manager=m, is_active=True
        ).count()

        # Commission summary.
        accrued = (
            SalesCommission.objects.filter(
                sales_manager=m, status=SalesCommission.Status.ACCRUED
            ).aggregate(s=Sum("amount_uzs"))["s"]
            or 0
        )
        lifetime = (
            SalesCommission.objects.filter(sales_manager=m)
            .exclude(status=SalesCommission.Status.REVERSED)
            .aggregate(s=Sum("amount_uzs"))["s"]
            or 0
        )

        # Companies going offline within 3 days (trial end / balance out).
        expiring = services.expiring_companies(companies, now=now)

        return Response(
            {
                "success": True,
                "integrators": integrators.count(),
                "companies": companies.count(),
                "operators": operators,
                "commission_percent": str(m.commission_percent),
                "balance_uzs": m.balance_uzs,
                "accrued_uzs": int(accrued),
                "lifetime_uzs": int(lifetime),
                "company_status": {
                    "active": status_counts.get(Company.Status.ACTIVE, 0),
                    "trial": max(status_counts.get(Company.Status.TRIAL, 0) - expired, 0),
                    "expired": expired,
                    "suspended": status_counts.get(Company.Status.SUSPENDED, 0),
                },
                "expiring_soon": expiring,
            }
        )


class SalesIntegratorsView(SalesView):
    @extend_schema(summary="My integrators + their companies/status")
    def get(self, request: Request) -> Response:
        m = self.sales_manager
        rows = []
        for i in Integrator.objects.filter(sales_manager=m):
            comps = Company.objects.filter(integrator=i)
            status_counts = dict(
                comps.values_list("status").annotate(n=Count("id")).values_list("status", "n")
            )
            now = timezone.now()
            expired = comps.filter(status=Company.Status.TRIAL, trial_ends_at__lt=now).count()
            rows.append(
                {
                    "id": i.pk,
                    "name": i.name,
                    "company_name": i.company_name,
                    "logo_url": f"/api/public/integrator-logo/{i.pk}" if i.logo_key else None,
                    "status": i.status,
                    "companies": comps.count(),
                    "company_status": {
                        "active": status_counts.get(Company.Status.ACTIVE, 0),
                        "trial": max(status_counts.get(Company.Status.TRIAL, 0) - expired, 0),
                        "expired": expired,
                        "suspended": status_counts.get(Company.Status.SUSPENDED, 0),
                    },
                }
            )
        return Response({"success": True, "integrators": rows})

    @extend_schema(summary="Create an integrator (linked to me)")
    def post(self, request: Request) -> Response:
        m = self.sales_manager
        email = (request.data.get("email") or "").strip().lower()
        name = (request.data.get("name") or "").strip()
        password = request.data.get("password") or ""
        if not email or not name or len(password) < 8:
            raise ApiError(ErrorCode.MISSING_FIELD, "email, name, password(≥8) required", 400)
        if User.objects.filter(username=email).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "email already registered", 400)
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            role=services.get_platform_role("integrator"),
        )
        integrator = Integrator.objects.create(
            user=user,
            name=name,
            company_name=(request.data.get("company_name") or "").strip(),
            phone=request.data.get("phone") or "",
            sales_manager=m,
        )
        return Response(
            {
                "success": True,
                "integrator": {"id": integrator.pk, "referral_code": integrator.referral_code},
            },
            status=201,
        )


class SalesIntegratorDetailView(SalesView):
    @extend_schema(summary="My integrator detail (commercial + companies)")
    def get(self, request: Request, integrator_id: int) -> Response:
        m = self.sales_manager
        integrator = Integrator.objects.filter(pk=integrator_id, sales_manager=m).first()
        if integrator is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "integrator not found", 404)
        companies = [
            {
                "id": c.pk,
                "name": c.name,
                "status": c.status,
                "created_at": c.created_at.isoformat(),
                "trial_ends_at": c.trial_ends_at.isoformat() if c.trial_ends_at else None,
                "seats": billing.seat_count(c),
            }
            for c in Company.objects.filter(integrator=integrator).order_by("-created_at")
        ]
        lifetime = (
            SalesCommission.objects.filter(sales_manager=m, integrator=integrator)
            .exclude(status=SalesCommission.Status.REVERSED)
            .aggregate(s=Sum("amount_uzs"))["s"]
            or 0
        )
        return Response(
            {
                "success": True,
                "integrator": {
                    "id": integrator.pk,
                    "name": integrator.name,
                    "company_name": integrator.company_name,
                    "logo_url": f"/api/public/integrator-logo/{integrator.pk}"
                    if integrator.logo_key
                    else None,
                    "email": integrator.user.email,
                    "phone": integrator.phone,
                    "status": integrator.status,
                    "referral_code": integrator.referral_code,
                    "companies": companies,
                    "my_commission_uzs": int(lifetime),
                },
            }
        )


class SalesPayoutsView(SalesView):
    @extend_schema(summary="List / request payouts")
    def get(self, request: Request) -> Response:
        m = self.sales_manager
        payouts = [
            {
                "id": p.pk,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "note": p.note,
                "requested_at": p.requested_at.isoformat(),
                "processed_at": p.processed_at.isoformat() if p.processed_at else None,
            }
            for p in m.payout_requests.all()[:50]
        ]
        return Response(
            {
                "success": True,
                "payouts": payouts,
                "balance_uzs": m.balance_uzs,
                "min_payout_uzs": services.get_platform_settings().min_payout_uzs,
            }
        )

    @extend_schema(summary="Request a payout")
    def post(self, request: Request) -> Response:
        m = self.sales_manager
        try:
            amount = int(request.data.get("amount_uzs", 0))
        except (TypeError, ValueError):
            raise ApiError(ErrorCode.MISSING_FIELD, "amount_uzs invalid", 400) from None
        try:
            payout = services.request_sales_payout(m, amount, note=request.data.get("note", ""))
        except services.PayoutError as exc:
            raise ApiError(ErrorCode.MISSING_FIELD, str(exc), 400) from None
        return Response({"success": True, "payout_id": payout.pk, "balance_uzs": m.balance_uzs})


def _profile_body(m: SalesManager) -> dict[str, Any]:
    offer = get_offer_document()
    return {
        "success": True,
        "name": m.name,
        "company_name": m.company_name,
        "logo_url": f"/api/public/sales-logo/{m.pk}" if m.logo_key else None,
        "phone": m.phone,
        "email": m.user.email,
        "commission_percent": str(m.commission_percent),
        "bank_card": m.bank_card,
        "bank_mfo": m.bank_mfo,
        "bank_inn": m.bank_inn,
        "bank_transit": m.bank_transit,
        "offer": {
            "content": offer.content,
            "version": offer.version,
            "accepted": m.offer_accepted_version >= offer.version and offer.version > 0,
            "accepted_at": m.offer_accepted_at.isoformat() if m.offer_accepted_at else None,
        },
    }


class SalesProfileView(SalesView):
    @extend_schema(summary="Profile (bank details, offer)")
    def get(self, request: Request) -> Response:
        return Response(_profile_body(self.sales_manager))

    @extend_schema(summary="Update profile / accept offer")
    def put(self, request: Request) -> Response:
        m = self.sales_manager
        for field in ("name", "company_name", "phone", "bank_card", "bank_mfo", "bank_inn", "bank_transit"):
            if field in request.data:
                setattr(m, field, (request.data[field] or "").strip())
        if request.data.get("accept_offer"):
            offer = get_offer_document()
            m.offer_accepted_version = offer.version
            m.offer_accepted_at = timezone.now()
        m.save()
        return Response(_profile_body(m))


class SalesLogoView(SalesView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary="Upload own logo")
    def post(self, request: Request) -> Response:
        import io
        import uuid

        from django.conf import settings as dj

        from apps.api import storage

        m = self.sales_manager
        upload = request.FILES.get("logo")
        if upload is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo file required", 400)
        if upload.size > 2 * 1024 * 1024:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo too large (max 2MB)", 400)
        types = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg", "image/webp": "webp"}
        content_type = getattr(upload, "content_type", "") or ""
        if content_type not in types:
            raise ApiError(ErrorCode.MISSING_FIELD, "logo must be png/jpeg/svg/webp", 400)
        key = f"sales-logos/{uuid.uuid4().hex}.{types[content_type]}"
        payload = upload.read()
        storage.ensure_bucket()
        storage.client().put_object(
            dj.MINIO_BUCKET, key, io.BytesIO(payload), length=len(payload), content_type=content_type
        )
        m.logo_key = key
        m.save(update_fields=["logo_key", "updated_at"])
        return Response({"success": True, "logo_url": f"/api/public/sales-logo/{m.pk}"})


class SalesNotificationsView(SalesView):
    @extend_schema(summary="My notifications")
    def get(self, request: Request) -> Response:
        qs = PlatformNotification.objects.filter(user=request.user)
        rows = [
            {
                "id": n.pk,
                "kind": n.kind,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in qs[:50]
        ]
        return Response(
            {"success": True, "unread": qs.filter(is_read=False).count(), "notifications": rows}
        )

    @extend_schema(summary="Mark all read")
    def post(self, request: Request) -> Response:
        PlatformNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"success": True})


# ── CRM: funnels (read-only) / leads / tasks ────────────────────────────────
def _pipeline_body(p) -> dict[str, Any]:
    return {
        "id": p.pk,
        "name": p.name,
        "order": p.order,
        "stages": [
            {"id": s.pk, "name": s.name, "order": s.order, "color": s.color}
            for s in p.stages.all()
        ],
    }


class SalesPipelinesView(SalesView):
    @extend_schema(summary="Global funnels (read-only for sales managers)")
    def get(self, request: Request) -> Response:
        ensure_global_pipelines()
        pipes = Pipeline.objects.filter(sales_manager__isnull=True).prefetch_related("stages")
        return Response({"success": True, "pipelines": [_pipeline_body(p) for p in pipes]})


class SalesLeadsView(SalesView):
    @extend_schema(summary="My leads")
    def get(self, request: Request) -> Response:
        qs = crm.apply_lead_filters(
            Lead.objects.filter(sales_manager=self.sales_manager), request.query_params
        ).prefetch_related("tags", "tasks").select_related("source")
        return Response({"success": True, "leads": [crm.lead_card(x) for x in qs[:1000]]})

    @extend_schema(summary="Create a lead")
    def post(self, request: Request) -> Response:
        m = self.sales_manager
        pipe = ensure_global_pipelines()
        name = (request.data.get("full_name") or "").strip()
        if len(name) < 2:
            raise ApiError(ErrorCode.MISSING_FIELD, "full_name required", 400)
        crm.check_duplicates(phone=request.data.get("phone"), company=request.data.get("company"))
        lead = Lead.objects.create(
            sales_manager=m,
            pipeline=pipe,
            stage=pipe.stages.first(),
            full_name=name,
            phone=(request.data.get("phone") or "").strip(),
            company=(request.data.get("company") or "").strip(),
        )
        crm.log_event(lead, "created", cast(User, request.user), text=name)
        return Response({"success": True, "lead": crm.lead_card(lead)}, status=201)


class SalesBoardStatsView(SalesView):
    @extend_schema(summary="CRM board metrics")
    def get(self, request: Request) -> Response:
        m = self.sales_manager
        leads = Lead.objects.filter(sales_manager=m)
        tasks = CrmTask.objects.filter(sales_manager=m)
        return Response({"success": True, **crm.board_stats(leads, tasks)})


class SalesLeadDetailView(SalesView):
    def _get(self, lead_id: int) -> Lead:
        lead = Lead.objects.filter(pk=lead_id, sales_manager=self.sales_manager).first()
        if lead is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "lead not found", 404)
        return lead

    @extend_schema(summary="Lead detail (fields + chatter)")
    def get(self, request: Request, lead_id: int) -> Response:
        return Response({"success": True, "lead": crm.lead_detail(self._get(lead_id))})

    @extend_schema(summary="Update / move a lead")
    def patch(self, request: Request, lead_id: int) -> Response:
        lead = self._get(lead_id)
        actor = cast(User, request.user)
        if "stage_id" in request.data:
            stage = PipelineStage.objects.filter(
                pk=request.data["stage_id"], pipeline=lead.pipeline
            ).first()
            if stage is None:
                raise ApiError(ErrorCode.MISSING_FIELD, "stage not found", 400)
            crm.move_to_stage(lead, stage, actor)
        crm.apply_fields(lead, request.data, actor)
        return Response({"success": True, "lead": crm.lead_detail(lead)})


class SalesLeadNoteView(SalesView):
    @extend_schema(summary="Add a chatter note to a lead")
    def post(self, request: Request, lead_id: int) -> Response:
        lead = Lead.objects.filter(pk=lead_id, sales_manager=self.sales_manager).first()
        if lead is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "lead not found", 404)
        text = (request.data.get("text") or "").strip()
        if not text:
            raise ApiError(ErrorCode.MISSING_FIELD, "text required", 400)
        e = crm.add_note(lead, cast(User, request.user), text)
        return Response({"success": True, "event": crm.event_body(e)}, status=201)


class SalesLeadTaskView(SalesView):
    @extend_schema(summary="Add a task to a lead")
    def post(self, request: Request, lead_id: int) -> Response:
        lead = Lead.objects.filter(pk=lead_id, sales_manager=self.sales_manager).first()
        if lead is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "lead not found", 404)
        crm.add_task(
            lead,
            cast(User, request.user),
            request.data.get("title"),
            request.data.get("due_at"),
            request.data.get("type_id"),
        )
        return Response({"success": True, "lead": crm.lead_detail(lead)}, status=201)


class SalesTasksView(SalesView):
    @extend_schema(summary="My tasks (Kanban buckets)")
    def get(self, request: Request) -> Response:
        m = self.sales_manager
        qs = CrmTask.objects.filter(sales_manager=m).select_related("lead", "type")
        tasks = []
        for tk in qs[:500]:
            tasks.append(
                {
                    "id": tk.pk,
                    "title": tk.title,
                    "due_at": tk.due_at.isoformat() if tk.due_at else None,
                    "is_done": tk.is_done,
                    "is_cancelled": tk.is_cancelled,
                    "auto": tk.auto,
                    "lead_id": tk.lead_id,
                    "lead_name": tk.lead.full_name if tk.lead else None,
                    "type": {"name": tk.type.name, "icon": tk.type.icon} if tk.type_id else None,
                    "bucket": crm.task_bucket(tk),
                    "created_at": tk.created_at.isoformat(),
                }
            )
        return Response(
            {
                "success": True,
                "tasks": tasks,
                "open_count": CrmTask.objects.filter(sales_manager=m, is_done=False).count(),
            }
        )

    @extend_schema(summary="Create a standalone task")
    def post(self, request: Request) -> Response:
        m = self.sales_manager
        title = (request.data.get("title") or "").strip()
        if len(title) < 2:
            raise ApiError(ErrorCode.MISSING_FIELD, "title required", 400)
        due = crm._parse_due(request.data.get("due_at"))
        from .models import CrmTaskType

        tt = CrmTaskType.objects.filter(pk=request.data.get("type_id")).first()
        CrmTask.objects.create(
            sales_manager=m, title=title, due_at=due, type=tt, created_by=cast(User, request.user)
        )
        return Response({"success": True})


class SalesTaskDetailView(SalesView):
    def _get(self, task_id: int) -> CrmTask:
        task = CrmTask.objects.filter(pk=task_id, sales_manager=self.sales_manager).first()
        if task is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "task not found", 404)
        return task

    @extend_schema(summary="Complete / cancel / edit a task (no delete)")
    def patch(self, request: Request, task_id: int) -> Response:
        task = self._get(task_id)
        actor = cast(User, request.user)
        action = request.data.get("action")
        if action == "complete" or request.data.get("is_done"):
            crm.complete_task(task, actor)
        elif action == "cancel":
            crm.cancel_task(task, actor, (request.data.get("reason") or "").strip())
        else:
            crm.edit_task(task, request.data)
        return Response({"success": True})


class SalesCrmMetaView(SalesView):
    @extend_schema(summary="Tags, sources and task types for CRM selects")
    def get(self, request: Request) -> Response:
        from .models import CrmTaskType, LeadSource, LeadTag

        return Response(
            {
                "success": True,
                "tags": [{"id": t.pk, "name": t.name, "color": t.color} for t in LeadTag.objects.all()],
                "sources": [{"id": s.pk, "name": s.name} for s in LeadSource.objects.all()],
                "task_types": [{"id": t.pk, "name": t.name, "icon": t.icon} for t in CrmTaskType.objects.all()],
            }
        )
