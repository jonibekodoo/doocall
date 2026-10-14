# dooCall Mobile API — implemented contract (Phase 3)

Implementation of `docs/backend-api-docs.md` (authoritative). Interactive
docs: **`/api/docs/`** (Swagger UI), schema at **`/api/schema/`**.

## Conventions (§1)

| | |
|---|---|
| Prefix | `api/call/v1/` — trailing slash tolerated, none required |
| Method | POST only, `Content-Type: application/json` |
| Auth | `api_key` in the JSON body **or** `Authorization: Bearer <api_key>` (§10; header wins). `user_name` in the body is cross-checked against the key's operator. |
| Time | Device sends `"yyyy-MM-dd HH:mm:ss"` in device-local time; server stores the raw string verbatim (`*_time_local`) **and** aware UTC (assumes device TZ == server `TZ`, default `Asia/Tashkent`) |
| Numbers | The device sends `from`/`to`/`operator_number`/`counterparty_number` and SIM numbers **raw, exactly as dialled/typed**; the server adds the country code using the company's `phone_code` (default `998`) — see [Phone numbers](#phone-numbers) |
| Dedup | `UNIQUE (company, call_id)` |
| Envelope | success: `{"success": true, …}` · error: `{"success": false, "message", "error_code", …}` |
| Throttling | per-endpoint scopes (env-tunable): auth 30/min, upload 300/min, calls_list 60/min, stats 60/min, log 10/min. 429 → `THROTTLED` envelope |

## Error taxonomy (§9 + one addition)

| `error_code` | HTTP | When |
|---|---|---|
| `INVALID_CREDENTIALS` | 401 | `/auth` bad login/password (body also keeps legacy `"api_key": ""`) |
| `INVALID_API_KEY` | 401 | Missing/unknown api_key, or `user_name` mismatch |
| **`SUBSCRIPTION_INACTIVE`** | **402** | **NEW: company suspended, or trial expired — on every endpoint incl. `/auth`** |
| `DUPLICATE_CALL_ID` | 409 | `/upload` with an existing `call_id` (body: `status: "already_exists"`, `call_id`) |
| `MISSING_FIELD` | 400 | Required field absent/invalid (message lists field names), bad Base64, bad datetime format |
| `AUDIO_TOO_LARGE` | 413 | Decoded audio > `AUDIO_MAX_MB` (default 20MB); no CDR row is created |
| `THROTTLED` | 429 | Rate limit exceeded |
| `SERVER_ERROR` | 500 | Unexpected failure |

## Endpoints

### POST `/api/call/v1/auth` (§4)
Accepts the minimal legacy payload (`username`, `password`, `server`) and the
full one (`phone_numbers[{sim_slot,number}]`, `full_name`, `device{…}`).
Upserts SimCards (per slot, numbers normalized), Device (per `device_id`,
`last_seen_at` bumped) and `full_name` on every login. Success:
`{"success": true, "api_key": "<permanent key>", "phone_code": "998"}` —
the legacy client reads only `success`/`api_key`; `phone_code` is an additive
field (ADR-0002).

`phone_code` is optional and informational: the company's default country
calling code — digits only, no `+` (e.g. `"998"` Uzbekistan, `"992"`
Tajikistan, `"7"` Kazakhstan/Russia). The app does not need it — it keeps
sending numbers raw and the server normalizes them (below).

### POST `/api/call/v1/upload` (§5)
Full CDR + optional Base64 audio (`audio_file`) + optional second source
(`audio_file_realtime`, §5.3). Audio goes to MinIO
(`<company>/<call_id>/<kind>/<filename>`); response returns a **presigned URL**
(7-day expiry; host from `MINIO_PUBLIC_ENDPOINT`). `resolved_name` comes from
the company Contact catalogue by normalized counterparty number, else `null`
(device-sent `counterparty_name` is stored separately for audit). Success body
(§5.4): `success, status:"received", call_id, server_id ("srv_…"),
received_at (ISO-8601 UTC "…Z"), resolved_name, audio{stored,url,size_bytes}`.

### POST `/api/call/v1/calls/list` (§6)
`{user_name, api_key, call_ids[]}` → `{"success": true, "calls":[
{"call_id","exists",("server_id" only when exists)]}`. Scoped to the
operator's company — other tenants' call_ids read as `exists: false`.

### POST `/api/call/v1/stats/summary` (§7)
Aggregates the calling operator's own records:
`total_duration_sec, total_count, inbound_count, outbound_count, missed_count`.

### POST `/api/call/v1/log` (§8)
`{user_name, api_key, hours, log_text}` → stores an `AppLog` row →
`{"success": true}`.

## Verified by contract tests (`backend/apps/api/tests/`)

Literal §4/§5.1/§6/§7/§8 example payloads replay against fixtures using the
doc's own credentials; response field sets asserted snapshot-style; MinIO
round-trip integration test streams the returned presigned URL; 402/401/400/
409/413/429 paths all covered. `apps/api` coverage: 95%.

## Phone numbers

The app sends every number (`from`, `to`, `operator_number`,
`counterparty_number`, `phone_numbers[].number` on `/auth`) **exactly as the
user dialled or typed it** — it does not add a country code. The server
normalizes each one with `apps.core.phone.normalize_phone(raw,
company.phone_code)` after stripping spaces, dashes, dots and parentheses:

| Raw (after cleanup) | Stored | Example (company `phone_code`) |
|---|---|---|
| starts with `+` | as sent | `+998901234567` → `+998901234567` (any company) |
| national length (9 for 998/992/996) | `+{code}{digits}` | `921234567` → `+992921234567` (992) |
| `{code}` + national length | `+{digits}` | `992921234567` → `+992921234567` (992) |
| `998` only: any 12 digits | `+{digits}` | `998901234567` → `+998901234567` |
| `7` only: 11 digits starting `8` | `+7` + last 10 | `87012345678` → `+77012345678` (7) |
| TJ/KG only: `0` + national length | `+{code}` + digits without the `0` | `0921234567` → `+992921234567` (992) |
| shorter than the national length, short codes, anything else | as sent (cleaned), **never prefixed** | `2212345`, `1234`, `*100#` |

Short numbers (local landlines without an area code, service codes) are kept
as-is because the server cannot know the missing digits. Uzbek companies get
no trunk-`0` rule (`0901234567` stays as sent).
