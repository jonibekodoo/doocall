"""Multi-tenancy primitives — request-scoped tenant context + force-filtered managers.

Pattern (documented in docs/architecture.md):

* A ``ContextVar`` holds the "current company" for the duration of a request
  (set by :class:`TenantMiddleware`) or a ``tenant_context(...)`` block.
* Every tenant-owned model inherits :class:`TenantModel`, whose default
  manager (:class:`TenantManager`) transparently filters by the current
  company whenever a tenant context is active.
* When NO context is active (migrations, management commands, Django admin
  used by platform superusers) the managers are unfiltered — cross-tenant
  access must always be an explicit, visible choice (``all_objects`` inside
  a tenant context, or code running with no context at all).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from django.db import models

if TYPE_CHECKING:
    from apps.companies.models import Company

_current_company_id: ContextVar[int | None] = ContextVar("current_company_id", default=None)


def get_current_company_id() -> int | None:
    return _current_company_id.get()


def _company_pk(company: Company | int | None) -> int | None:
    if company is None or isinstance(company, int):
        return company
    return company.pk


def set_current_company(company: Company | int | None) -> None:
    _current_company_id.set(_company_pk(company))


@contextmanager
def tenant_context(company: Company | int | None) -> Iterator[None]:
    """Scope all TenantManager queries to ``company`` inside the block."""
    token = _current_company_id.set(_company_pk(company))
    try:
        yield
    finally:
        _current_company_id.reset(token)


class TenantQuerySet(models.QuerySet):  # type: ignore[type-arg]
    def for_company(self, company: Company | int) -> TenantQuerySet:
        return self.filter(company_id=_company_pk(company))


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Default manager for tenant models: force-filters by the active tenant."""

    def get_queryset(self) -> TenantQuerySet:
        qs = cast(TenantQuerySet, super().get_queryset())
        company_id = get_current_company_id()
        if company_id is not None:
            qs = qs.filter(company_id=company_id)
        return qs


class TenantModel(models.Model):
    """Abstract base for every row owned by a single company."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects: Any = TenantManager()
    all_objects: Any = models.Manager()  # explicit cross-tenant escape hatch

    class Meta:
        abstract = True
        # Keep the escape hatch out of the "default" position.
        default_manager_name = "objects"
        base_manager_name = "all_objects"
