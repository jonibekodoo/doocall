# dooCall (CallCloud)

Call-recording SaaS for teams that sell by phone. Operators install an
Android app; every call is recorded, uploaded and turned into dashboards,
reports and billing — multi-tenant, per-operator seat pricing (UZS,
Payme/Click/manual).

**Status: feature-complete (Phases 1–12 — core SaaS + admin & partner portals with cashback).** Backend contract, billing engine,
web cabinet, public landing, hardening & packaging are all implemented and
tested. The API contract lives in [`docs/backend-api-docs.md`](docs/backend-api-docs.md).

| Layer | Tech |
|---|---|
| Backend | Django 5 · DRF · SimpleJWT · Celery · gunicorn |
| Frontend | Next.js 15 (App Router) · TypeScript · Tailwind v4 · TanStack Query · next-intl (ru/uz/en) · Recharts |
| Data | PostgreSQL 16 · Redis 7 · MinIO (audio, presigned ≤1h) |
| Ops | Docker Compose (dev+prod) · nginx · Mailhog (dev) · GitHub Actions CI · Sentry hooks |

## Quickstart (new dev, <10 commands)

```bash
git clone <repo> doocall && cd doocall   # 1
cp .env.example .env                      # 2
make up                                   # 3  full stack, healthchecked
make migrate                              # 4
make seed                                 # 5  demo tenant + 12k calls
make test                                 # 6  169 backend + 53 frontend tests
make lint                                 # 7  ruff·mypy·eslint·prettier·tsc
```

Hosts: `*.localhost` works out of the box (no /etc/hosts needed). Legacy `doocall.local` aliases still resolve if configured.

**Logins after `make seed`** — cabinet: `admin@ahlan.uz` / `demo1234` ·
Django admin: `admin` / `admin` · mobile operators: `aziz`…/`demo1234`.

| URL | What |
|---|---|
| http://localhost | Public landing (uz default) |
| http://app.localhost | Cabinet (`/` → `/cabinet`) |
| http://app.admin.localhost | Django platform admin — ALL companies (`/` → `/admin/`) |
| http://app.localhost/admin | Admin portal SPA (superadmin/platform_admin; `super@doocall.uz`/demo1234) |
| http://app.localhost/partner | Partner portal SPA (integrators; `partner1@demo.uz`/demo1234) |
| http://localhost:8001/api/docs/ | Swagger UI |

Screenshots: [`docs/screenshots/`](docs/screenshots/) — cabinet
(light/dark, 3 breakpoints), landing, paywall.

## Documentation

| Doc | Contents |
|---|---|
| [architecture.md](docs/architecture.md) | system diagram (mermaid), tenancy pattern, identity model |
| [mobile-api.md](docs/mobile-api.md) | implemented device contract §4–§9 (+402) |
| [web-api.md](docs/web-api.md) | cabinet API surface |
| [billing.md](docs/billing.md) | seat pricing, state machine, providers, jobs |
| [deployment.md](docs/deployment.md) | prod compose, DNS/TLS/certbot, backups, monitoring |
| [development.md](docs/development.md) | dev loop, code map, conventions |
| [decisions/](docs/decisions/) | ADRs 0001–0005 |
| [COMPLIANCE_CHECKLIST.md](docs/COMPLIANCE_CHECKLIST.md) | requirement → implementation → test map |
| [progress/](docs/progress/) | per-phase build logs (PHASE-1 … PHASE-9) |

## Production

```bash
cp .env.example .env   # real secrets!
docker compose -f docker-compose.prod.yml up -d --build
```

gunicorn workers, Next standalone build, collectstatic → nginx volume,
healthchecks + restart policies + resource limits on every service. Full
runbook: [docs/deployment.md](docs/deployment.md).
