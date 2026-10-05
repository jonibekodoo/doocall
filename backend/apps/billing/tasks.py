"""Celery beat jobs for billing (schedules in settings.CELERY_BEAT_SCHEDULE).

Each task is a thin wrapper over a pure service function that takes ``now`` —
tests freeze time by calling the service directly (or passing ``now_iso``).
"""

from __future__ import annotations

import logging
from datetime import datetime

from celery import shared_task
from django.utils import timezone

from apps.companies.models import Company
from apps.core.models import AuditLog

from . import services
from .models import Subscription

logger = logging.getLogger(__name__)


def _resolve_now(now_iso: str | None) -> datetime:
    return datetime.fromisoformat(now_iso) if now_iso else timezone.now()


def run_trial_expiry(now: datetime) -> int:
    """Suspend every company whose trial has lapsed. Returns count suspended."""
    expired = Company.objects.filter(status=Company.Status.TRIAL, trial_ends_at__lt=now)
    count = 0
    for company in expired:
        subscription = Subscription.all_objects.filter(company=company).first()
        if subscription is not None and subscription.status == Subscription.Status.TRIAL:
            services.suspend(subscription, reason="trial_expired")
        else:
            company.status = Company.Status.SUSPENDED
            company.save(update_fields=["status", "updated_at"])
            AuditLog.objects.create(
                company=company,
                action="subscription.suspended",
                target_model="companies.Company",
                target_id=str(company.pk),
                changes={"reason": "trial_expired"},
            )
        count += 1
    return count


def run_invoice_generation(now: datetime) -> int:
    """Superseded by the daily-billing cycle model (see ``run_monthly_settlement``):
    cycles are settled from the prepaid balance, no invoices are issued."""
    return 0


def run_daily_accrual(now: datetime) -> int:
    """Write yesterday's operator-day charges for every active company."""
    from datetime import timedelta

    day = (now - timedelta(hours=6)).date()  # 00:30 run bills the finished day
    total = 0
    for company in Company.objects.filter(status=Company.Status.ACTIVE):
        total += services.accrue_company_day(company, day)
        # Prepaid: take the finished day (and any backlog) from the balance now;
        # suspends the company the day the money runs out.
        services.deduct_pending_charges(company, now=now, upto=day)
        if company.status == Company.Status.ACTIVE:
            services.warn_low_balance(company, now=now)
    return total


def run_monthly_settlement(now: datetime) -> int:
    """Daily sweep: settle every subscription whose billing cycle (payment date →
    same day next month) has ended — deducts the cycle's usage from the balance
    and starts the next cycle. (Task name kept for the beat schedule.)"""
    return services.run_cycle_settlement(now)


@shared_task(name="apps.billing.tasks.accrue_daily_charges")
def accrue_daily_charges(now_iso: str | None = None) -> int:
    now = _resolve_now(now_iso)
    count = run_daily_accrual(now)
    logger.info("daily accrual: %d operator-day charge(s)", count)
    # Auto-payment runs in the SAME task, strictly after the deduction, so it
    # sees the real post-deduction balance (and can lift a fresh suspension).
    try:
        from . import autopay

        logger.info("autopay: %s", autopay.run_autopay(now))
    except Exception:  # noqa: BLE001 - never let auto-pay break the accrual task
        logger.exception("autopay sweep failed")
    return count


@shared_task(name="apps.billing.tasks.settle_monthly_statements")
def settle_monthly_statements(now_iso: str | None = None) -> int:
    count = run_monthly_settlement(_resolve_now(now_iso))
    logger.info("monthly settlement: %d statement(s) processed", count)
    return count


@shared_task(name="apps.billing.tasks.enforce_overdue_payments")
def enforce_overdue_payments(now_iso: str | None = None) -> int:
    count = services.run_overdue_enforcement(_resolve_now(now_iso))
    logger.info("overdue enforcement: blocked %d company(ies)", count)
    return count


@shared_task(name="apps.billing.tasks.suspend_expired_trials")
def suspend_expired_trials(now_iso: str | None = None) -> int:
    count = run_trial_expiry(_resolve_now(now_iso))
    logger.info("trial expiry sweep: suspended %d company(ies)", count)
    return count


@shared_task(name="apps.billing.tasks.generate_due_invoices")
def generate_due_invoices(now_iso: str | None = None) -> int:
    count = run_invoice_generation(_resolve_now(now_iso))
    logger.info("invoice sweep: generated %d invoice(s)", count)
    return count


def run_audio_retention(now: datetime) -> int:
    """Delete call audio older than the company's retention window.

    Per-company override (``Company.audio_retention_days``), global default
    ``settings.AUDIO_RETENTION_DAYS`` (30). Removes BOTH the MinIO object and
    the CallAudio row; the CDR itself is never touched.
    """
    from datetime import timedelta

    from django.conf import settings as dj_settings

    from apps.api import storage
    from apps.calls.models import CallAudio

    default_days = int(dj_settings.AUDIO_RETENTION_DAYS)
    deleted = 0
    for company in Company.objects.all():
        days = company.audio_retention_days or default_days
        cutoff = now - timedelta(days=days)
        expired = CallAudio.objects.filter(
            call__company=company, created_at__lt=cutoff
        ).select_related("call")
        for audio in expired:
            try:
                storage.client().remove_object(dj_settings.MINIO_BUCKET, audio.object_key)
            except Exception:  # noqa: BLE001 - object may already be gone
                logger.warning("retention: object %s missing in MinIO", audio.object_key)
            audio.delete()
            deleted += 1
        if deleted:
            AuditLog.objects.create(
                company=company,
                action="audio.retention_cleanup",
                changes={"deleted": deleted, "retention_days": days},
            )
    return deleted


@shared_task(name="apps.billing.tasks.cleanup_expired_audio")
def cleanup_expired_audio(now_iso: str | None = None) -> int:
    count = run_audio_retention(_resolve_now(now_iso))
    logger.info("audio retention: deleted %d object(s)", count)
    return count


@shared_task(name="apps.billing.tasks.purge_company_storage")
def purge_company_storage(company_pk: int) -> int:
    """Remove every MinIO object of a deleted company (keys are ``<pk>/…``).

    Fired AFTER the DB cascade, so it works purely off the key prefix.
    """
    from django.conf import settings as dj_settings

    from apps.api import storage

    minio = storage.client()
    removed = 0
    for obj in minio.list_objects(dj_settings.MINIO_BUCKET, prefix=f"{company_pk}/", recursive=True):
        try:
            minio.remove_object(dj_settings.MINIO_BUCKET, obj.object_name)
            removed += 1
        except Exception:  # noqa: BLE001 - object may already be gone
            logger.warning("purge: could not remove %s", obj.object_name)
    logger.info("purge company %d storage: removed %d object(s)", company_pk, removed)
    return removed


def run_balance_warning(now: datetime, *, threshold_days: int = 3) -> int:
    """Warn the responsible sales manager when a company's prepaid balance will
    run out within ``threshold_days``. One notification per company per day."""
    from apps.partners.models import CrmTask, PlatformNotification

    warned = 0
    companies = Company.objects.filter(status=Company.Status.ACTIVE).exclude(
        integrator__sales_manager=None
    )
    today = now.date()
    for company in companies.select_related("integrator__sales_manager__user"):
        left = services.days_of_balance_left(company, day=today)
        if left is None or left > threshold_days:
            continue
        manager = company.integrator.sales_manager
        msg = f"{company.name}: balans {left} kundan so'ng tugaydi"
        already = PlatformNotification.objects.filter(
            user=manager.user, kind=PlatformNotification.Kind.BALANCE_WARNING,
            message=msg, created_at__date=today,
        ).exists()
        if already:
            continue
        PlatformNotification.objects.create(
            user=manager.user, kind=PlatformNotification.Kind.BALANCE_WARNING, message=msg
        )
        # Auto CRM task so the manager follows up with the client.
        task_title = f"Balansni to'ldirish: {company.name} ({left} kun)"
        if not CrmTask.objects.filter(
            sales_manager=manager, title=task_title, is_done=False
        ).exists():
            CrmTask.objects.create(sales_manager=manager, title=task_title, auto=True)
        warned += 1
    return warned


@shared_task(name="apps.billing.tasks.balance_warning")
def balance_warning(now_iso: str | None = None) -> int:
    count = run_balance_warning(_resolve_now(now_iso))
    logger.info("balance warning: notified %d company(ies)", count)
    return count
