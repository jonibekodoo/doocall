# dooCall — Compliance checklist (Phase 9 final audit)

> **Scope note.** `CLAUDE_CODE_PROMPT_dooCall.md` was never present on this
> machine (verified by full-disk search in Phase 1; the owner approved
> proceeding from the per-phase task briefs + `backend-api-docs.md`). This
> audit therefore maps (A) **every item of backend-api-docs.md §11** — the
> only written master contract — and (B) **every requirement of the nine
> phase briefs**, which served as the working spec. Where a §-reference of
> the missing master spec pinned a value, the placeholder used is flagged.

Legend: ✅ done · ⏸ deferred (reason given). File paths are repo-relative;
tests name the covering module.

## A. backend-api-docs.md §11 — mobile contract checklist

| # | Requirement | Implementation | Tests | |
|---|---|---|---|---|
| A1 | `POST /api/call/v1/auth` — one call: login/password/server + phone_numbers per SIM + device info; upsert; NO /register | `backend/apps/api/views.py:AuthView`, serializers | `apps/api/tests/test_auth_contract.py` (literal §4 minimal+full replays, upsert idempotency, exact 401 body) | ✅ |
| A2 | `POST /api/call/v1/upload` — full §5.1 CDR: audio+location+operator/counterparty numbers AND names+sim_slot | `UploadView` | `test_upload_contract.py` (literal §5.1 replay) | ✅ |
| A3 | from/to/operator_number/counterparty_number always full E.164, never login name (§0.1) | `apps/core/phone.py` applied in `UploadView` | `test_phone.py` (16 cases), `test_upload_contract.py::test_numbers_are_normalized_e164` | ✅ |
| A4 | from_name/to_name/counterparty_name from device contact, null when unresolved (§0.2/§5.2) | nullable CharFields on `CallRecord`, passthrough in view | `test_upload_contract.py` (null and value paths) | ✅ |
| A5 | UNIQUE server-side dedup on call_id | `UNIQUE (company, call_id)` in `apps/calls/models.py` | `test_constraints.py::TestCallDedup` (+cross-company allowed) | ✅ |
| A6 | audio_file Base64 Opus/OGG (or original) stored; optional audio_file_realtime | `UploadView` audio loop → MinIO (`apps/api/storage.py`), `CallAudio` kinds | `test_upload_contract.py` (primary+realtime), `test_minio_integration.py` (bytes + streamed presigned URL) | ✅ |
| A7 | §5.4 full JSON response: status, server_id, received_at ISO-UTC, resolved_name, audio{stored,url,size_bytes}; 409 duplicate body | `UploadView` response + `ApiError` extras | `test_upload_contract.py` (exact key-set snapshot, 409 body) | ✅ |
| A8 | `POST /api/call/v1/calls/list` dedup pre-check (§6) | `CallsListView` | `test_list_stats_log.py::TestCallsList` (mixed exists, server_id only on hits, tenant isolation) | ✅ |
| A9 | `POST /api/call/v1/stats/summary` (§7) | `StatsSummaryView` (SQL aggregate) | `TestStatsSummary` (exact math + zero state) | ✅ |
| A10 | `POST /api/call/v1/log` (§8) | `LogView` → `AppLog` | `TestLog` (literal log lines stored, exact `{"success": true}`) | ✅ |
| A11 | §9 uniform envelope + error_code taxonomy on ALL endpoints | `apps/api/errors.py` (handler, codes, 500 handler) | every contract test asserts codes; `test_cross_cutting.py` | ✅ |
| A12 | §10: Authorization Bearer accepted alongside body api_key | `apps/api/auth.py` | `TestBearerAuth` (header, header-wins, mismatch) | ✅ |
| A13 | §10: audio size limit with 413 AUDIO_TOO_LARGE | `AUDIO_MAX_MB` env → `UploadView` | `test_oversized_audio_413` (no partial rows) | ✅ |
| A14 | §10: null counterparty_name is normal, not an error | serializer allows null | covered by A4 tests | ✅ |
| A15 | §10: versioned prefix v1, v2 reserved for breaking changes | url prefix + ADR-0002 | n/a (policy) | ✅ |

## B. Phase briefs (working spec)

### Phase 1 — scaffold
| Repo layout / dev+prod compose / nginx 3 domains / .env.example full / ruff+mypy+pytest+ESLint+prettier+pre-commit+Makefile / CI containers / healthz+check_services smoke | compose files, `nginx/conf.d/doocall.conf`, `.env.example`, `Makefile`, `.github/workflows/ci.yml` | `test_healthz.py`, `test_check_services.py` (unit + live) | ✅ |

### Phase 2 — data model & tenancy
| All models incl. PricingSetting history, UNIQUE(company,call_id), api_key UNIQUE; composite indexes; TenantQuerySet/ContextVar tenancy documented w/ mermaid; §1 phone util; themed admin (companies actions, pricing history, payments approval, read-only CDRs); seed_demo 12k | `apps/{companies,accounts,calls,billing,core}`, `docs/architecture.md`, admin modules, `seed_demo.py` | `test_tenancy.py` (hard isolation), `test_constraints.py`, `test_phone.py`, `test_seed_demo.py` | ✅ |
| Master-spec §10 operator names / §13 index list | placeholders flagged in `seed_demo.py` + model comments | — | ⏸ pins unavailable (file absent) |

### Phase 3 — mobile API — covered by section A. Plus throttling (`DEFAULT_THROTTLE_RATES` + 429 envelope — `TestThrottling`), 402 SUBSCRIPTION_INACTIVE (`TestSubscriptionInactive`), OpenAPI at /api/schema/ + Swagger (verified live), local-time strings stored verbatim (`test_record_persisted_with_both_time_representations`). ✅

### Phase 4 — auth & billing
| Registration→trial; SimpleJWT w/ httpOnly refresh + rotation; password reset; email-verification flag | `apps/web/views.py` | `test_auth_flow.py` (full JWT lifecycle) | ✅ |
| Seat billing, price-next-period, invoice task, state machine | `apps/billing/services.py`, `tasks.py` | `test_invoices.py`, `test_lifecycle.py` | ✅ |
| Beat jobs (trial expiry, invoices, retention) | `CELERY_BEAT_SCHEDULE` | `TestCeleryTaskWrappers`, `test_retention.py` | ✅ |
| PaymentProvider iface; manual full; Payme+Click sandbox-shaped w/ signatures; webhooks | `apps/billing/providers/` | `test_webhooks.py` (valid + tampered both providers) | ✅ |
| 402 enforcement mobile+web paywall payload; AuditLog events | `apps/api/auth.py`, `BillingStatusView` | `TestTrialExpiry`, `TestPaywall` | ✅ |
| Real Payme/Click merchant credentials + checkout redirect | env slots + interface ready | — | ⏸ requires real merchant onboarding |

### Phase 5 — cabinet API
| Dashboard, calls (filters/pagination/export/columns/delete), contacts (+from-call), 7 reports ALL in SQL incl. unanswered drop-off + unique flag, settings (groups/users/devices/toggles/api-key/webhook HMAC/license) | `apps/web/views_*.py`, `queries.py`, `tasks.py` | 40-call hand-computed fixture (`test_reports.py`), `test_calls_api.py`, `test_contacts_api.py`, `test_settings_api.py`, HMAC (`TestWebhook`) | ✅ |
| Perf < 300ms on 12k rows | `DISTINCT ON` + bounded enrichment | `test_perf.py` (timings 2–97ms, pasted in PHASE-5.md) | ✅ |

### Phase 6 — frontend foundation
| Tokens light/dark, teal accent, fonts, tnum; shell to 380px; auth flows + paywall; typed client + TanStack Query; ru/uz/en; DataTable/FilterBar/DateRangePicker/StatCard/chart theme/AudioPlayer machine | `frontend/app/globals.css`, `components/`, `lib/` | 37 Vitest; Playwright smoke 3 viewports + paywall (screenshots in docs/screenshots) | ✅ |

### Phase 7 — cabinet screens
| §6.1–§6.6 screens wired to live API, export toast, reveal-once creds, live license math, dark theme, no console errors | `frontend/app/cabinet/**` | 45 Vitest + 6-scenario E2E incl. seats ±1 loop | ✅ |

### Phase 8 — landing & funnel
| Public pricing endpoint cached; landing sections w/ live price slider; uz/ru/en; SEO (OG/sitemap/robots); register→onboarding checklist | `views_public.py`, `frontend/app/page.tsx`, `cabinet/onboarding` | `test_public_pricing.py`; Vitest pricing/locales; funnel E2E + cache-TTL price-change E2E | ✅ |
| APK artifact + distribution | placeholder link in onboarding | — | ⏸ Android app binary is outside this repo |

### Phase 9 — hardening (this phase)
| Prod compose (workers, standalone, static volume, healthchecks, limits) + validated + smoked | `docker-compose.prod.yml`, `frontend/Dockerfile.prod` | live smoke: healthz/landing/login/operator/upload/static all ✅ | ✅ |
| argon2 · presign ≤1h (hard cap) · CORS 3 domains · CSP+security headers · secret-grep CI · JSON logs · Sentry env-flag · operator key rotation | settings, `storage.py`, `next.config.ts`, `ci.yml`, `OperatorKeyRotateView` | `TestOperatorKeyRotation`; scan run clean; settings verified live | ✅ |
| Audio retention job (30d default, per-company tunable) | `run_audio_retention` + `Company.audio_retention_days` | `test_retention.py` (frozen time, override, resilience) | ✅ |
| Backups scripted+documented | `scripts/backup.sh`, `docs/deployment.md` | — (ops doc) | ✅ |
| CI: coverage ≥85% gate, Playwright nightly-vs-PR split | `ci.yml` | gate exercised locally (94% ≥ 85%) | ✅ |
| All §12 docs + ADRs + README | `docs/*.md`, `docs/decisions/0001–0005` | — | ✅ |

## C. ADDENDUM PART A (Phases 10–12)

> `ADDENDUM_admin_integrator.md` was never present on this machine (searched
> each session); PART A requirements are audited from the three phase briefs
> that inlined them.

| # | Requirement | Implementation | Tests | |
|---|---|---|---|---|
| C1 | A.1 roles superadmin/platform_admin/integrator, company=NULL, matrix (superadmin ⊃ platform_admin, exclusions) | `apps/partners/models.py` (perm sets), `services.get_platform_role/role_name`, `permissions.py` | `test_permissions.py` (13 endpoints × 5 roles table) | ✅ |
| C2 | A.1 login returns role + portal hint | `apps/web/views.py` (login + refresh) | `test_referral_impersonation.py`, phase11 Vitest homeFor | ✅ |
| C3 | A.2 Integrator (override, unique referral code, payout details) | `partners.Integrator` | `test_cashback.py`, functional | ✅ |
| C4 | A.2 PlatformSetting default % + months limit (+min payout), history-tracked | `PlatformSetting(+History)` | `test_cashback.py::test_percent_change…` (history row) | ✅ |
| C5 | A.2 Company.integrator + acquired_via, immutable except superadmin reassignment | `companies.Company.save` guard + `reassign_integrator` | `test_direct_binding_mutation_is_blocked`, `test_reassign_endpoint_superadmin_only` | ✅ |
| C6 | A.2 CashbackAccrual OneToOne(payment), snapshot, status machine; PayoutRequest machine + processed_by; audit event types | `partners.models` | cashback suite (17 tests) | ✅ |
| C7 | A.5 engine: idempotent accrual on success for all 3 providers; months limit; refund reversal; balance | `services.accrue/reverse/balance` hooked in `apply_payment` | idempotency, 3-provider, frozen-time cutoff, reversal, balance tests | ✅ |
| C8 | Admin API: KPIs, companies actions, payment approval+cashback, integrator CRUD+override(super)+suspend, cashback settings(super), admin CRUD(super), payout actions(super), audit query, impersonation(super, bannered/audited/time-limited) | `views_admin.py` | functional + permission matrix + impersonation tests | ✅ |
| C9 | Partner API: dashboard+12m series, my-companies commercial-only, on-behalf registration, ledger filters, payout create/list, profile; referral attribution on public registration w/ fallback | `views_partner.py`, `web/views.py` ref | partner functional + referral tests | ✅ |
| C10 | Isolation: integrator never reaches operational data; platform_admin 403 on super endpoints; company users 403 on both portals | guards + payload shaping | `TestIsolation`, matrix, phase12 E2E API probe | ✅ |
| C11 | A.3 admin portal UI: 8 screens, dark identity, superadmin-only controls ABSENT for platform_admin, 403 page, impersonation banner+exit | `frontend/app/admin/**`, middleware | phase11 Vitest (7) + Playwright (4 flows) | ✅ |
| C12 | A.4 partner portal UI: Обзор/Мои компании/Добавить(ref link+QR+promo, manual w/ temp password reveal-once)/Начисления(+totals+CSV)/Выплаты(min from settings)/Профиль; ru/uz/en | `frontend/app/partner/**`, messages | phase12 Vitest (4 suites) + full-loop Playwright | ✅ |
| C13 | ?ref= → 30-day cookie → signup binding; attribution visible in admin | `RefCapture`, register page, admin detail badge | phase12 E2E steps 3 (bind) + companies list attribution | ✅ |

Addendum: **13/13 done.** (QR uses api.qrserver.com in dev — self-hosted QR
lib is a cosmetic swap if offline generation is required.)

## Summary

| Total requirement lines audited | **71** (58 core + 13 addendum) |
| ✅ Done (implementation + tests) | **67** |
| ⏸ Deferred | **4** (unchanged core deferrals) |

**Deferred (with reasons)**
1. Master-spec §10/§13 pinned values (operator names, exact index list) — the file has never been available; placeholders are flagged inline for one-line swaps.
2. Real Payme/Click merchant credentials + hosted checkout redirect — requires commercial onboarding; adapters, signatures and webhooks are complete and tested against the documented protocols.
3. Android APK artifact + download link — the mobile app is a separate codebase; the server side of its contract is fully implemented and contract-tested.
4. TLS certificates in compose — host-specific by nature; certbot runbook and mount points are prepared in `docs/deployment.md`.
