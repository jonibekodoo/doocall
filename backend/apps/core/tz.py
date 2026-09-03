"""Per-company timezone resolution.

Every company stores an IANA zone name (``Company.timezone``); this module
turns it into a ``ZoneInfo`` with a safe fallback to the global
``settings.TIME_ZONE`` for blank/invalid values.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings

from .tenancy import get_current_company_id


@lru_cache(maxsize=256)
def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - any bad name falls back to the default
        return ZoneInfo(settings.TIME_ZONE)


def company_tz(company: Any | None = None) -> ZoneInfo:
    """Zone of ``company``, or of the ACTIVE TENANT when omitted.

    Works anywhere a tenant context is set (CabinetView requests, export
    jobs inside ``tenant_context``); with no context the global default
    applies.
    """
    if company is None:
        from apps.companies.models import Company

        company_id = get_current_company_id()
        company = (
            Company.objects.filter(pk=company_id).only("timezone").first()
            if company_id
            else None
        )
    return zone(getattr(company, "timezone", "") or settings.TIME_ZONE)


def is_valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except Exception:  # noqa: BLE001
        return False
