# dooCall — Development guide

## Boot

```bash
cp .env.example .env
make up        # full stack; docker compose ps → all healthy
make migrate
make seed      # Ahlan House: 6 operators, 12k calls, admin@ahlan.uz/demo1234
```

No /etc/hosts needed: `localhost`, `app.localhost`, `app.admin.localhost` resolve automatically. Domains are env-driven (`DOMAIN_*` in `.env`) — nginx renders its config from `nginx/templates/` via envsubst.

| Where | URL |
|---|---|
| Landing / cabinet via nginx | http://localhost, http://app.localhost |
| Frontend direct (dev proxy → backend) | http://localhost:3000 |
| Backend direct | http://localhost:8001 (host port; in-network 8000) |
| Django admin (all companies) | http://app.admin.localhost (admin/admin after seed) |
| Swagger | http://localhost:8001/api/docs/ |
| MinIO console / Mailhog | :9001 / :8025 |

## Daily commands

`make test` (all) · `make test-backend` (pytest+coverage) · `make
test-frontend` (vitest) · `make lint` (ruff+mypy+eslint+prettier+tsc) ·
`make logs s=backend` · `make shell`.

E2E (host, against the running stack): `cd frontend && npx playwright test`.
Marked-slow/mutating specs run on the desktop project only. Backend perf
guards: `docker compose exec backend pytest -m perf -s`.

## Code map

```
backend/apps/
  core/       tenancy (ContextVar + TenantManager), phone normalization,
              healthz, check_services, seed_demo, AuditLog
  companies/  Company (status, flags, api_key, webhook, retention override)
  accounts/   User (AUTH_USER_MODEL), Role, OperatorProfile(+api_key),
              OperatorGroup, Device, SimCard
  calls/      CallRecord (CDR, UNIQUE company+call_id), CallAudio,
              Contact(+Phone), AppLog
  billing/    PricingSetting(+history), Subscription state machine,
              Invoice(+lines), Payment, providers/ (manual|payme|click),
              tasks (trial expiry, invoices, audio retention)
  api/        mobile /api/call/v1 (§4–§9 contract), MinIO storage, errors
  web/        cabinet /api/web/v1 + auth + webhooks + public pricing
frontend/
  app/        landing (uz default), auth pages, cabinet/* screens
  components/ shell, DataTable/FilterBar/StatCard/AudioPlayer, charts theme
  lib/        api client+endpoints (typed), format/filters/pricing utils,
              audio state machine, auth context
  messages/   ru / uz / en catalogs
```

## Conventions

* Tenant scoping is manager-level — write `Model.objects…` inside
  `CabinetView`/`tenant_context` and it is company-scoped; `all_objects` is
  the explicit escape hatch (greppable).
* Mobile API responses are byte-compatible with `docs/backend-api-docs.md`;
  change them only with a `v2` prefix.
* Money is integer UZS; durations integer seconds; phones normalized via
  `apps.core.phone.normalize_phone` (§1 rule) at every boundary.
* Frontend numbers use the `.tnum` utility; teal=answered, warm red=missed.
* New backend code must keep `mypy --strict` and the 85% coverage gate green.
