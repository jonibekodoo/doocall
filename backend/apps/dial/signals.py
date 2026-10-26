"""Kick live device sockets the moment their access is withdrawn.

Covers every save()/delete() path: API-key rotation, operator deactivation
or deletion, company suspension. Bulk ``queryset.update()`` paths (e.g. the
Django-admin "suspend" action) bypass signals — the consumer's 25 s
re-check closes those sockets instead. After commit only, and best effort:
a channel-layer outage must never break the save itself.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.accounts.models import OperatorProfile
from apps.companies.models import Company

from . import services

logger = logging.getLogger(__name__)


def _safely(func: Any, *args: Any) -> None:
    try:
        func(*args)
    except Exception:  # noqa: BLE001 - never fail the triggering save
        logger.warning("dial: could not push session.revoke", exc_info=True)


def _after_commit(func: Any, *args: Any) -> None:
    transaction.on_commit(partial(_safely, func, *args))


@receiver(pre_save, sender=OperatorProfile)
def _remember_operator(sender: Any, instance: OperatorProfile, **kwargs: Any) -> None:
    old = (
        OperatorProfile.all_objects.filter(pk=instance.pk).values("api_key", "is_active").first()
        if instance.pk
        else None
    )
    instance._dial_old = old  # type: ignore[attr-defined]


@receiver(post_save, sender=OperatorProfile)
def _operator_changed(sender: Any, instance: OperatorProfile, created: bool, **kwargs: Any) -> None:
    old = getattr(instance, "_dial_old", None)
    if created or not old:
        return
    if old["api_key"] != instance.api_key or (old["is_active"] and not instance.is_active):
        _after_commit(services.revoke_operator, instance.company_id, instance.pk)


@receiver(post_delete, sender=OperatorProfile)
def _operator_deleted(sender: Any, instance: OperatorProfile, **kwargs: Any) -> None:
    _after_commit(services.revoke_operator, instance.company_id, instance.pk)


@receiver(pre_save, sender=Company)
def _remember_company(sender: Any, instance: Company, **kwargs: Any) -> None:
    instance._dial_old_status = (  # type: ignore[attr-defined]
        Company.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        if instance.pk
        else None
    )


@receiver(post_save, sender=Company)
def _company_changed(sender: Any, instance: Company, created: bool, **kwargs: Any) -> None:
    old = getattr(instance, "_dial_old_status", None)
    if not created and old != instance.status and instance.status == Company.Status.SUSPENDED:
        _after_commit(services.revoke_company, instance.pk)
