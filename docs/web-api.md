# dooCall Web Cabinet API (`/api/web/v1/`) — Phase 5

JWT-authenticated (SimpleJWT `Authorization: Bearer <access>`), tenant-scoped:
every endpoint activates the Phase-2 tenant context from the user's company —
cross-tenant rows are unreachable by construction. Company-admin-only
endpoints are marked **[admin]** (`User.is_company_admin`). Interactive docs:
`/api/docs/`.

## Dashboard (§6.1)

`GET /dashboard?period=today|3d|7d&operator=<id>` → `general` (all/in/out ×
total/answered/missed + duration), `per_operator` activity, `latest_calls`
(last 10 answered), `unanswered_now` (numbers whose LAST call is missed, with
attempt counts).

## Calls (§6.2)

| Endpoint | Notes |
|---|---|
| `GET /calls` | Filters: `employees=1,2`, `date_from`/`date_to` (YYYY-MM-DD), `direction`, `status`, `search` (name or phone, E.164-normalized), `min_duration`, `sim_slot`. Pagination 30/page (`page`), returns `count`/`pages`. Sort: `ordering=duration|-duration|date|-date`. |
| `GET /calls/<id>` | Full CDR + presigned audio URLs (primary/realtime). |
| `DELETE /calls/<id>/delete` | **[admin]** |
| `POST /calls/export` | `{format: csv\|xlsx, filters:{…}}` → 202 + `export_id`; Celery task streams `values()` rows to MinIO. |
| `GET /calls/export/<id>` | status + `row_count` + presigned download URL. |
| `GET/PUT /calls/columns` | Per-user column preferences for the calls table. |

## Contacts (§6.3)

CRUD at `/contacts[/<id>]` — multi-phone (normalized + deduplicated),
`responsible_id`, `q` search (name or phone), pagination. Detail includes call
history matched by E.164. `POST /contacts/from-call/<call_id>` prefills the
counterparty number, back-fills `resolved_name` on all past calls with that
number (409 if the number already belongs to a contact).

## Reports (§6.4) — all aggregation in SQL

All accept the same filter params as `/calls`.

| Endpoint | Report |
|---|---|
| `GET /reports/general` | all/in/out × answered/missed + total duration |
| `GET /reports/weekday-matrix` | ISO weekday × direction/status counts |
| `GET /reports/period-counts?group=day\|week\|month&unique=true` | period buckets; `unique` counts distinct client numbers |
| `GET /reports/per-employee` | per-operator distribution, answered/missed, duration minutes |
| `GET /reports/per-client` | per-number totals/answered/missed/duration/last call (top 500) |
| `GET /reports/unanswered` | **exact drop-off semantic**: a client appears iff their LAST call is missed; disappears on the next successful call. Includes `last_success` and `attempts_since_success`. |
| `GET /reports/last-contact` | latest call per client (`DISTINCT ON`) |

Performance guard (12k rows, local run): every endpoint 2–97ms, budget 300ms
(`pytest -m perf -s`; auto-skipped when `CI` is set).

## Settings (§6.5)

| Endpoint | Notes |
|---|---|
| `GET/POST /settings/groups`, `PUT/DELETE /settings/groups/<id>` | operator groups |
| `GET/POST /settings/users` | create operator → returns `{user_name, password, api_key}` **once**, never retrievable again |
| `PATCH/DELETE /settings/users/<id>` | **[admin]** — `is_active` toggle changes billable seats **immediately** and disables the operator's mobile api_key |
| `GET /settings/devices` | devices + SIMs + `online` (last_seen < 5min) |
| `PATCH /settings/sims/<id>` | **[admin]** per-SIM `recording_enabled` toggle, set number |
| `DELETE /settings/devices/<id>` | **[admin]** |
| `GET/PUT /settings/account` | **[admin]** toggles: `contact_import_enabled`, `recording_enabled`, `pin_enabled` |
| `GET/POST /settings/api-key` | **[admin]** company API key: masked view / generate+rotate (returned once) |
| `GET/PUT /settings/webhook` | **[admin]** webhook URL; HMAC secret generated on first set (returned once) |
| `POST /settings/webhook/test` | **[admin]** signed test delivery |
| `GET /settings/license` | trial countdown OR period dates, live `seats × price = total_uzs`, payment history |

## Call webhook

When `webhook_url` is set, every accepted mobile upload enqueues a signed
POST (after DB commit): JSON body `{event: "call.received", call_id,
server_id, …}` with header **`X-Doocall-Signature`** =
HMAC-SHA256(webhook_secret, raw body). 3 retries with backoff.

---

# Phase 10 additions — three-portal architecture

Login (`POST /api/web/v1/auth/login`) now returns `user.role` and
`user.portal` (`admin` | `partner` | `cabinet`) for frontend routing.
Public registration accepts an optional `ref` (integrator referral code);
an invalid/suspended code silently falls back to `self_signup`.

## Admin portal — `/api/admin/v1/` (roles: superadmin, platform_admin)

| Endpoint | Access | Notes |
|---|---|---|
| `GET /dashboard` | staff | platform KPIs: companies by status, MRR, payments 30d, integrators, pending payouts |
| `GET /companies?status&q` · `GET /companies/<id>` | staff | list/detail with seats, subscription, acquisition |
| `POST /companies/<id>/suspend\|activate\|extend-trial` | staff | lifecycle actions (audited) |
| `POST /companies/<id>/reassign` | **superadmin** | rebind integrator; old accruals stay with previous owner |
| `POST /payments/<id>/approve` | staff | manual approval — **fires cashback accrual**, returns accrued amount |
| `GET/POST /integrators` · `PATCH /integrators/<id>` | staff | CRUD + suspend; `cashback_percent_override` field is **superadmin-only** (403 otherwise) |
| `GET/PUT /settings/cashback` | **superadmin** | default % + months limit (history-tracked) |
| `GET/POST /admins` · `PATCH /admins/<id>` | **superadmin** | platform-admin user CRUD |
| `GET /payouts?status` · `POST /payouts/<id>/approve\|reject\|mark-paid` | **superadmin** | payout queue; state machine enforced |
| `GET /audit?action&company&date_from` | staff | audit-log query |
| `POST /impersonate/<company_id>` · `POST /impersonate/stop` | **superadmin** | 15-min access token with `impersonated: true` claim (frontend banner); start/stop audited |

## Partner portal — `/api/partner/v1/` (role: integrator, active only)

| Endpoint | Notes |
|---|---|
| `GET /dashboard` | referral code, effective %, company counts, balance, paid-out total, **12-month accrual series** |
| `GET /companies` · `GET /companies/<id>` | **commercial fields only** — never calls/contacts/users/devices |
| `POST /companies` | register a client on my behalf → trial company bound `integrator_manual` |
| `GET /accruals?status&company&date_from` | accrual ledger |
| `GET/POST /payouts` | list / request (≤ available balance) |
| `GET/PUT /profile` | name, phone, payout details |
