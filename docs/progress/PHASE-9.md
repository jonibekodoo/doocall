# PHASE 9 — Hardening, packaging, audit (FINAL — completed)

## Phase 8 verification
`make test` green (169+53) and the funnel E2E passed before new work.

## 1. Production packaging
`docker-compose.prod.yml` finalized: gunicorn (workers/threads env-tunable,
auto migrate+collectstatic), **Next standalone** multi-stage image
(`Dockerfile.prod`, non-root, `HOSTNAME=0.0.0.0` fix for the Docker-injected
hostname), collectstatic volume served by nginx with backend fallback,
healthchecks (incl. celery-worker ping) + `restart: unless-stopped` +
resource limits on every service. `config -q` validates.

**Prod smoke (local, real run)** — all green:
healthz `{"status":"ok"}` · landing uz hero served · register → JWT login →
operator created (credentials once) → mobile `/auth` → `/upload` `received`
· admin static 200 via the nginx volume · `docker compose ps`: 8/8 healthy.
Two real bugs found and fixed by the smoke: YAML folded-scalar newlines made
gunicorn ignore `--bind` (loopback-only), and Next standalone bound to the
container hostname.

## 2. Security pass
Argon2id first hasher · presigned audio URLs **≤1h hard cap**
(`AUDIO_PRESIGN_EXPIRY_SECONDS`, `min(…, 3600)`) · CORS locked to the three
product domains (+localhost in DEBUG) · CSP + nosniff/referrer/permissions
headers on Next (dev-only eval carve-out) · **secret-grep CI job** (key
patterns + committed-.env guard; run locally: clean) · structured JSON logs
(prod) · Sentry behind `SENTRY_DSN` flag · company API-key rotation existed;
**operator api_key rotation endpoint added** (`…/users/<id>/rotate-key`,
old key 401s immediately — tested) · DRF throttle rates env-tunable and
documented.

## 3. Audio retention
`cleanup_expired_audio` is now real: per-company window
(`Company.audio_retention_days`, migration `companies.0003`) with global
default 30d; deletes MinIO object + CallAudio row, keeps the CDR, writes an
AuditLog. 5 frozen-time tests (default window, per-company override,
task-wrapper `now_iso`, missing-object resilience).

## 4. Backups
`scripts/backup.sh` (pg_dump custom-format + MinIO mirror + 14-day
rotation); cron + restore + off-site notes in `docs/deployment.md`.

## 5. CI
`pytest --cov --cov-fail-under=85` gate (actual: **94%**) · secrets-scan job
· Playwright job: PR = desktop smoke, **nightly schedule = full matrix**
(seeded stack in CI).

## 6. Documentation
architecture (mermaid) · mobile-api · web-api · billing · **deployment**
(DNS/TLS certbot/backups/monitoring/env knobs) · **development** (boot, code
map, conventions) · **ADRs 0001–0005** (tenancy, contract compatibility,
postpaid billing, JWT cookie split, MinIO presign) · polished README with
quickstart, logins, doc index, screenshot links.

## 7. Final audit
`docs/COMPLIANCE_CHECKLIST.md`: every backend-api-docs.md §11 item and every
phase-brief requirement mapped to implementation files + covering tests.
**58 audited · 54 done · 4 deferred** (master-spec pinned values — file never
existed on this machine; real Payme/Click merchant credentials; Android APK
artifact; host-specific TLS certs). Gap found during the audit — operator
key rotation — was implemented and tested in this phase rather than
deferred.

## Final outputs

```
make lint  → exit 0   (ruff · ruff-format · mypy --strict 100 files ·
                       ESLint · Prettier · tsc)
make test  → exit 0
  backend : 174 passed, coverage TOTAL 94% (gate ≥85%)
  frontend: 53 passed (9 files)
E2E        : 21 passed / 8 by-design skips (3 viewports; mutation suites
             desktop-scoped)
prod smoke : healthz ✓ landing ✓ cabinet login ✓ operator ✓ mobile upload ✓
             static ✓ — 8/8 services healthy
compliance : 58 items · 54 ✅ · 4 ⏸
```

dooCall is feature-complete per the available specifications. 🏁
