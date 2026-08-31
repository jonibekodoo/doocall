# PHASE 3 — Mobile API /api/call/v1 (completed)

## Phase 2 verification (session start)

`make up` (all healthy) · `make test` (35 backend + 2 frontend, 90% cov) ·
`make seed` (12k records) — all green before new work.

## Delivered

**New app `apps.api`** — five endpoints, POST-only, per contract:

| Endpoint | § | Notes |
|---|---|---|
| `POST /api/call/v1/auth` | §4 | minimal + full payload; SimCard/Device/full_name upsert; legacy-compatible bodies (success: `{success, api_key}`; 401 keeps `"api_key": ""` + `INVALID_CREDENTIALS`) |
| `POST /api/call/v1/upload` | §5 | full CDR; §1 number normalization (Phase-2 util); local time string + aware UTC both stored (new `start_time_local`/`end_time_local`, migration `calls.0002`); Base64 primary + realtime audio → MinIO; presigned URL in §5.4-shaped response; `resolved_name` from company Contact catalogue; 409 already_exists; 413 `AUDIO_TOO_LARGE` (no partial rows); 400 invalid Base64/datetime |
| `POST /api/call/v1/calls/list` | §6 | dedup pre-check, `server_id` only on hits, tenant-scoped |
| `POST /api/call/v1/stats/summary` | §7 | per-operator aggregates |
| `POST /api/call/v1/log` | §8 | AppLog storage |

**Cross-cutting**: api_key from body AND `Authorization: Bearer` (header
wins, `user_name` cross-checked); uniform §9 envelope via DRF exception
handler (`apps/api/errors.py`) incl. 500 handler; **NEW 402
`SUBSCRIPTION_INACTIVE`** (suspended company / expired trial, all endpoints
incl. auth — documented in `docs/mobile-api.md`); `ScopedRateThrottle`
per-endpoint rates (env-tunable); `MINIO_PUBLIC_ENDPOINT` so presigned URLs
are reachable from outside compose; drf-spectacular schema at `/api/schema/`
+ Swagger UI at `/api/docs/` (verified 200 direct and through nginx).

## Tests — 69 backend passed, `apps/api` 95% / total 92% coverage

- **Literal payload replays**: fixtures use the doc's own credentials
  (`operator1`/`••••••••`/`b7e2f1c9-....`) so §4 minimal + full, §5.1 CDR,
  §6, §7, §8 example JSONs replay byte-for-byte.
- **Snapshot-style shape asserts**: §5.4 success body exact key set
  (incl. `audio{stored,url,size_bytes}`), §4 success exactly
  `{success, api_key}`, §6 `server_id` omitted on misses.
- **Error taxonomy**: duplicate 409 (exact §5.4 body), bad api_key 401,
  oversized audio 413 (row-free), missing field 400 (names the field),
  invalid Base64/datetime 400, throttle 429, suspended/expired 402,
  live-trial allowed.
- **MinIO integration** (runs in compose, skips without infra): object bytes
  verified via S3 API **and** the returned presigned URL streamed via HTTP.
- Isolation guards: per-test locmem cache (throttle counters can't leak),
  storage client caches cleared, cross-tenant call_ids invisible in §6.

## Verification evidence

- `make test` → exit 0 (69 + 2, coverage report printed, api app 95%).
- `make lint` → backend ruff + format + strict mypy clean (64 files).
- Swagger UI title "dooCall Mobile API" renders; schema valid OpenAPI 3.0.3.
- Live smoke through nginx (`app.doocall.local`): auth → api_key issued.

## Notes / carry-over

- Device-local→UTC conversion assumes device TZ == server `TZ`
  (Asia/Tashkent). If devices roam, §4 could carry a `tz` field in a future
  phase — flagged in docs.
- Master spec (`CLAUDE_CODE_PROMPT_dooCall.md`) still absent; §5 was executed
  from backend-api-docs.md alone per standing ruling.
- Dev DB re-seeded after smoke testing; nginx reload needed after backend
  container recreation (dev-only quirk of static upstream IPs — a
  `resolver`-based upstream can address this in Phase 9).
