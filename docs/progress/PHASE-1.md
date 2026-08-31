# PHASE 1 — Scaffold (completed)

> Written retroactively at the start of the Phase 2 session: the Phase 1
> session ended while images were still building, so final verification and
> this document were completed here.

## What exists

- **Repo layout**: `backend/` (Django 5 project `doocall`, `apps/` folder),
  `frontend/` (Next.js 15 App Router + TS + Tailwind v4 + shadcn/ui init),
  `nginx/`, `docs/`, `.github/workflows/`, `Makefile`.
- **docker-compose.yml (dev)**: backend, frontend, db (postgres 16 + volume),
  redis, minio (+console, + one-shot bucket-create), celery-worker,
  celery-beat, nginx, mailhog. `docker-compose.prod.yml` skeleton with
  healthchecks (finalize in Phase 9).
- **Nginx**: `doocall.local` / `app.doocall.local` / `app.admin.doocall.local`
  server block; `/api/`, `/healthz/`, `/admin/`, `/static/` → backend, rest →
  frontend; wildcard per-tenant block stubbed. `/etc/hosts` lines in README.
- **.env.example**: every variable (DB, Redis, Celery, MinIO, JWT,
  Payme/Click placeholders, domains, DEBUG, AUDIO_MAX_MB, TRIAL_DAYS,
  DEFAULT_PRICE_PER_OPERATOR_UZS, email, frontend).
- **Tooling**: ruff + strict mypy (django-stubs), pytest + pytest-django +
  coverage, ESLint + Prettier + tsc, pre-commit, Makefile (up/down/test/
  test-backend/test-frontend/lint/migrate/seed/logs/ps/shell).
- **CI**: `.github/workflows/ci.yml` — lint + typecheck + tests for both
  sides, run in containers, with live infra for backend integration tests.
- **Smoke tests**: `/healthz/` endpoint + pytest; `check_services` management
  command (Postgres/Redis/MinIO probes) + unit & live-integration tests;
  Vitest rendering `HealthBadge`.

## Definition-of-done evidence (verified this session)

- `make up` → all services start; `docker compose ps`: backend, db, frontend,
  mailhog, minio, nginx, redis **healthy**; celery-worker/beat Up (no
  healthcheck yet — Phase 9).
- `make lint` → exit 0 (ruff, ruff format, mypy strict, ESLint, Prettier, tsc).
- `make test` → exit 0 (backend 35 passed, 90% cov; frontend 2 passed).

## Deviations / notes

- **Master spec missing**: `CLAUDE_CODE_PROMPT_dooCall.md` is not on this
  machine. Phase 1 was executed from the task message + `backend-api-docs.md`
  (user-approved). Placeholder values are marked in `.env.example`.
- **Host ports**: db binds host **5433** (`POSTGRES_HOST_PORT`), backend binds
  host **8001** (`BACKEND_HOST_PORT`) — 5432/8000 were taken by other local
  stacks (amoncrm, local postgres). In-network ports unchanged.
- **Fixes made during verification**: Tailwind pinned to 4.1.11 (4.0.0 had an
  oxide-scanner incompatibility breaking `next dev`); nginx healthcheck uses
  `127.0.0.1` (alpine resolves `localhost` to `::1`).
