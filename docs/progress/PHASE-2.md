# PHASE 2 — Data model, tenancy, admin, seed (completed)

## Models (all migrated, `0001_initial` per app, clean)

| App | Models |
|---|---|
| `apps.companies` | `Company` (status: trial/active/suspended, `trial_ends_at`) |
| `apps.accounts` | `User` (custom `AUTH_USER_MODEL`, `company` FK, `role` FK), `Role` (JSON permission codes, per-company or platform), `OperatorProfile` (`user_name` + UNIQUE `api_key`), `Device`, `SimCard` (UNIQUE (operator, sim_slot)) |
| `apps.calls` | `CallRecord` (every CDR field of contract §5.1/§5.2, **UNIQUE (company, call_id)**, `server_id` UUID), `CallAudio` (primary/realtime per §5.3, UNIQUE (call, kind)), `Contact` + `ContactPhone`, `AppLog` (§8) |
| `apps.billing` | `PricingSetting` (single global row enforced, **history-tracked** via `PricingSettingHistory` appended on every change), `Subscription` (1/company, price snapshot), `Invoice` + `InvoiceLine`, `Payment` (payme/click/manual, manual-approval flow) |
| `apps.core` | `AuditLog` (append-only; written by admin actions) |

Composite indexes on `CallRecord`: (company, -start_time), (company,
operator, -start_time), (company, counterparty_number), (company, call_type,
call_status); plus invoice/payment/audit indexes. *(Master spec §13 is not on
this machine — these are documented placeholders for the obvious access
paths; reconcile when the spec lands.)*

## Tenancy layer — `apps/core/tenancy.py` (+ `docs/architecture.md` w/ mermaid)

- `ContextVar`-based request-scoped tenant context (`tenant_context()`,
  `set_current_company()`), bound per-request by
  `apps.core.middleware.TenantMiddleware` from `request.user.company_id`.
- `TenantManager` (default manager of every `TenantModel`) force-filters by
  the active company; `all_objects` is the explicit cross-tenant escape hatch.
- `User.tenant_objects` provides the same guarantee for users (default
  `objects` stays global for auth machinery).

## Phone normalization — `apps/core/phone.py`

Exactly contract §1: `+…` kept; 9 digits → `+998…`; 12 digits → `+…`;
separators stripped; everything else passed through. 16 table-driven tests.

## Django admin (app.admin.doocall.local)

- Themed (`templates/admin/base_site.html`, indigo header, dooCall branding).
- Companies: status / trial_ends_at / operator-count columns; actions
  **suspend / activate / extend-trial (+7d)** — all writing `AuditLog` rows.
- PricingSetting: editable, history inline (read-only), `updated_by` stamped.
- Payments: **manual-approval action** (approves pending, stamps
  approver/time, marks linked invoice paid, writes `AuditLog`), reject action.
- CallRecords: strictly **read-only** (no add/change/delete), audio inline.
- Verified: all changelists HTTP 200 with seeded data; served through nginx
  at `app.admin.doocall.local` (302→login anonymous, static 200).

## seed_demo v1 (`make seed`)

Company **"Ahlan House"**, 6 operators (names are placeholders — master spec
§10 absent), 6 devices, 9 SIMs (half dual-SIM), 5 contacts, **12,000
CallRecords** over 30 days (~68% answered, ~55% inbound, missed = 0s
duration), deterministic (seed 42), **idempotent by reset** (deletes and
rebuilds the demo company). Creates dev superuser `admin/admin`.

## Tests — 35 passed, coverage 90% (target ≥85%)

- `test_phone.py` — 16 table-driven cases incl. edge cases.
- `test_tenancy.py` — hard isolation: A cannot see B's calls/contacts/
  operators/users; nesting/reset; explicit escape hatch.
- `test_constraints.py` — duplicate (company, call_id) raises; same call_id
  across companies allowed; UNIQUE api_key; pricing history on change; no
  history on no-op save; single global pricing row.
- `test_seed_demo.py` — counts, realistic ratios, idempotency-by-reset.
- Plus Phase 1 smoke tests (healthz, check_services unit + live integration).

## Verification evidence

- `make lint` → exit 0 · `make test` → exit 0 (35 backend + 2 frontend).
- `make seed` → 12,000 records seeded.
- `docker compose ps` → all healthchecked services healthy.

## Notes / carry-over

- Master spec still missing → §4/§8/§10/§13 details executed from the task
  message; placeholders flagged inline (`seed_demo.py`, indexes, .env).
- Phase 3 hook points ready: `normalize_phone`, `OperatorProfile.api_key`,
  `CallRecord` dedup constraint, `CallAudio.object_key` (MinIO), §9 error
  envelope still to be built as DRF layer.
