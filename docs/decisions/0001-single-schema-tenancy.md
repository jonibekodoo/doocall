# ADR-0001: Single-schema multi-tenancy via manager-level filtering

**Status**: accepted (Phase 2)

**Context**: Every business row belongs to one company; the mobile contract
requires `UNIQUE (company, call_id)` dedup and platform billing needs
cross-tenant aggregation.

**Decision**: one Postgres schema; every tenant model carries a `company` FK;
the *default* manager (`TenantManager`) force-filters by a request-scoped
`ContextVar` set by middleware (session) or `CabinetView.initial()` (JWT).
`all_objects` is the explicit, greppable escape hatch.

**Consequences**: queries are tenant-safe by construction and migrations stay
trivial; the trade-off is discipline around `all_objects` (reviewed in code
review) and a single-database scale ceiling that is far above expected load
(call metadata is small; audio lives in MinIO).

**Alternatives rejected**: schema-per-tenant (migration fan-out, cross-tenant
billing pain), separate databases (operational cost far above product needs).
