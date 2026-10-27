# dooCall Web Cabinet API (`/api/web/v1/`) — Phase 5

JWT-authenticated (SimpleJWT `Authorization: Bearer <access>`), tenant-scoped:
every endpoint activates the Phase-2 tenant context from the user's company —
cross-tenant rows are unreachable by construction. Company-admin-only
endpoints are marked **[admin]** (`User.is_company_admin`). Interactive docs:
`/api/docs/`.

## Missed vs not reached

Product wording for a `no_answer` call depends on its direction:

| Term | Meaning | Field / filter |
|---|---|---|
| **Missed** — Пропущен / O'tkazib yuborilgan | a CLIENT called us (inbound) and nobody answered | `missed_inbound` · `status=missed` |
| **Not reached** — Не дозвонился / Javob bermadi | WE called the client (outbound) and they didn't answer | `not_reached` · `status=not_reached` |

The older `missed` fields (and `in_missed`/`out_missed` style blocks) are kept
for compatibility and still count `no_answer` in **any** direction
(`missed = missed_inbound + not_reached`); `status=no_answer` likewise.

## Dashboard (§6.1)

`GET /dashboard?period=today|3d|7d&operator=<id>` → `general` (all/in/out ×
total/answered/missed/`missed_inbound`/`not_reached` + duration),
`per_operator` activity (`total`, `answered`, `missed`, `missed_inbound`,
`not_reached`, `duration`), `latest_calls` (last 10 answered),
`unanswered_now` (clients waiting for a call-back — same rule as
`/reports/unanswered` — with attempt counts).

## Calls (§6.2)

| Endpoint | Notes |
|---|---|
| `GET /calls` | Filters: `employees=1,2`, `date_from`/`date_to` (YYYY-MM-DD), `direction`, `status` (`answered`, `no_answer` = any direction, `busy`, `failed`, plus `missed` = inbound no_answer and `not_reached` = outbound no_answer), `search` (name or phone, E.164-normalized), `min_duration`, `sim_slot`. Pagination 30/page (`page`), returns `count`/`pages`. Sort: `ordering=duration|-duration|date|-date`. |
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
| `GET /reports/general` | all/in/out × answered/missed + total duration; every block also has `missed_inbound` and `not_reached` (`inbound.not_reached` and `outbound.missed_inbound` are always 0) |
| `GET /reports/weekday-matrix` | ISO weekday × direction/status counts (+ `missed_inbound`, `not_reached`) |
| `GET /reports/period-counts?group=day\|week\|month&unique=true` | period buckets (`total`, `answered`, `missed`, `missed_inbound`, `not_reached`); `unique` counts distinct client numbers |
| `GET /reports/per-employee` | per-operator distribution, answered/missed (+ `missed_inbound`, `not_reached`), duration minutes |
| `GET /reports/per-client` | per-number totals/answered/missed (+ `missed_inbound`, `not_reached`)/duration/last call (top 500) |
| `GET /reports/unanswered` | **clients waiting for a call-back**: a number appears iff its LAST call is `no_answer` AND the client called us with no answer (inbound `no_answer`) since our last answered call. A failed call-back (outbound `no_answer`) keeps it listed; a number we only called ourselves and never reached never appears; the next answered call removes it. Includes `last_success` and `attempts_since_success` (no_answer calls of any direction since the last success). |
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

## Remote Dial for integrations

The operator's phone places an outgoing call (Remote Dial, see
mobile-api.md) — requested by an external system instead of the cabinet.
Same number validation (digits only, allowed country codes, exact national
length), per-device rate limit (1 per 10 s, 20/h), audit row
(`dial.requested`, `source` api/bitrix24) and "never queued when offline"
rule as the cabinet. On the phone the operator still confirms every dial.

### Public API (`POST /api/v1`, `user_name` + company `api_key`)

Opt-in per company: `GET/PUT /settings/account` → `api_dial_enabled`
(default `false`, company admin). Off → `403 {error_code: "feature_disabled"}`.
The Kotib read-only key can never call these (403).

| Action | Body | Result |
|---|---|---|
| `calls.dial` | `{operator: <operator user_name>, number, device_id?}` | the operator's given device (must be theirs) or their most recently seen **online** device → `200 {success: true, command_id, status: "sent"}` · `409 {success: false, error_code: "device_offline", command_id, status: "offline"}` (not queued) · `400 invalid_number` / `destination_not_allowed` · `404 operator_not_found` / `device_not_found` · `429 rate_limited` · `402 subscription_inactive` — errors as `{success: false, error_code, message}`. `created_by` = the API user (`requested_by` on the phone = their name) |
| `calls.dial.status` | `{command_id}` | `{success: true, command: {command_id, device_id, operator: {id, full_name}, number, status, reject_reason, sim_mode, used_sim_slot, duration_sec, cause, created_at, acked_at, updated_at}}` (company-scoped; 404 otherwise; 400 bad UUID). Poll it — statuses: sent, received, rejected, dialing, active, disconnected, failed, expired, offline |

### CRM call result codes (missed vs not reached)

| DooCall call | Bitrix24 `telephony.externalcall.finish` `STATUS_CODE` | amoCRM `call_status` |
|---|---|---|
| answered | `200` successful call | `4` разговор состоялся |
| inbound no_answer (missed) | `304` missed call (пропущенный) | `6` + `direction: inbound` |
| outbound no_answer (not reached) | `480` temporarily unavailable — **not** 304, so Bitrix24 doesn't show our own unanswered call as "missed" | `6` не дозвонился |
| busy | `486` busy | `7` номер занят |
| failed | `603` declined | `6` |

Bitrix24's code list (apidocs) has no "не дозвонился" entry; 480 is the SIP
answer for a callee who didn't pick up. amoCRM's enum has no "пропущенный"
value, so both directions send 6 and amoCRM tells them apart by `direction`.

### Bitrix24 click-to-call

A Bitrix24 user clicks a phone number in the CRM → Bitrix fires
`ONEXTERNALCALLSTART` → DooCall finds the mapped operator (`user_map`,
Bitrix user → operator) and that operator's phone dials it. The Bitrix24
call registered by Bitrix (`data[CALL_ID]`) is kept on the command; when the
resulting outbound CDR is delivered (same operator + number, ≤ 10 min) it
is **finished** (`telephony.externalcall.finish` + recording) instead of a
new call being registered.

Config (`PUT /settings/integrations/bitrix24`, `config`):
`click_to_call_enabled` (bool) and `b24_app_token` (secret, masked; the
*application token* Bitrix24 shows for the outgoing webhook). GET adds
`click_to_call_url` (full URL with our token, "" until enabled — admin
only), `b24_app_token_set` (bool), `external_line_registered` (bool).
Saving with click-to-call on creates the token and tries
`telephony.externalLine.add` (NUMBER/NAME "DooCall", best effort —
Bitrix24 documents it as application-context only, so a plain inbound
webhook may be refused; the setting still works if the portal routes
clicks to the webhook).

Setup in Bitrix24:
1. Developer resources → Other → **Outgoing webhook**: handler URL =
   `click_to_call_url`, event **ONEXTERNALCALLSTART** (scope telephony);
   copy its *application token* into `b24_app_token`.
2. Map Bitrix users to operators (`user_map`, Bitrix24 users screen).
3. Telephony settings: make the DooCall line / handler the default for
   outgoing calls from the CRM.

Handler `POST /api/public/bitrix24/click-to-call/<token>` (form-encoded as
Bitrix sends, JSON also accepted): unknown token 404; `b24_app_token` set
and `auth[application_token]` wrong → 401; otherwise always 200 —
`{status: "sent"|"offline"|"duplicate"|"refused"|"ignored", …}`. The same
`CALL_ID` (Bitrix resends) never dials twice; an unmapped Bitrix user is
ignored and logged.

## amoCRM: per-operator managers

Same contract as the Bitrix24 mapping below. `config.user_map` =
`{"<OperatorProfile id>": "<amoCRM user id>"}` on the `amocrm` integration
(this company's operators only, positive integers stored as strings, empty
values dropped, omitted = kept, 400 `{message}` otherwise; GET returns it,
`{}` when unset). `responsible_user_id` stays the fallback.

- Sending: the call's `responsible_user_id` and that of a contact created
  for an unknown number = `user_map[operator id]`, else
  `responsible_user_id`, else the field is omitted. If amoCRM rejects the
  mapped user (validation error on `responsible_user_id`), the call is sent
  once more with the fallback (delivery ok, warning logged).
- `GET /settings/integrations/amocrm/users` **[admin]** — `GET
  {base}/api/v4/users?limit=250&page=N&with=role` (our base URL only, max 4
  pages / 500 users, inactive users skipped) → `{success: true, users: [{id,
  name, email, phone: null, position: <role name> | null}], operators: [{id,
  full_name, user_name, phones: [...]}], suggestions: {"<operator id>":
  "<amo id>"}}`. Suggestions: operator's login e-mail == amoCRM e-mail
  first, then exact case-insensitive full name (either word order);
  ambiguous ones are left out. On failure: `200 {success: false, error,
  operators}` — error "amoCRM foydalanuvchilar ro'yxatini olib bo'lmadi —
  token muddati tugagan yoki huquq yetarli emas; ID'larni qo'lda kiriting"
  (other failures append a short generic reason). 400 when amoCRM isn't
  configured. The token and raw bodies are never returned.

## Bitrix24: per-operator users

Calls are registered in Bitrix24 under a user. `config.user_map` maps each
DooCall operator to a Bitrix24 user; `config.user_id` stays the fallback for
unmapped operators (default `1`).

| Endpoint | Notes |
|---|---|
| `PUT /settings/integrations/bitrix24` | `config.user_map`: `{"<OperatorProfile id>": "<Bitrix24 user id>"}`. Keys must be this company's operator ids, values positive integers (sent as string or number, stored as string); empty values are dropped. 400 `{message}` on an unknown/foreign operator id, a non-numeric or non-positive value, or a non-object. Omitting `user_map` keeps the stored one. |
| `GET /settings/integrations` | the `bitrix24` row's `config.user_map` is returned as stored (`{}` when unset; not a secret). |
| `GET /settings/integrations/bitrix24/users` | **[admin]** Live `user.get` (active users, follows `next`, capped at 500) → `{success: true, users: [{id, name, email, phone, position}], operators: [{id, full_name, user_name, phones: [...]}], suggestions: {"<operator id>": "<b24 id>"}}`. Suggestions: normalized phone match (operator SIM numbers vs `PERSONAL_MOBILE` / `WORK_PHONE` / `PERSONAL_PHONE`, company `phone_code`) first, then exact case-insensitive full name (`NAME LAST_NAME` either order); ambiguous matches are left out. If `user.get` fails: `200 {success: false, error, operators}` — for a webhook without the "user" scope the error is "Bitrix24 vebhukida «user» (Foydalanuvchilar) ruxsati yo'q — vebhukka shu ruxsatni qo'shing yoki ID'larni qo'lda kiriting". 400 when Bitrix24 isn't configured. The webhook URL is never returned. |

Sending: `USER_ID` (register and finish) = `user_map[operator id]`, else
`user_id`, else `1`. If Bitrix24 rejects the mapped user on register, the call
is registered once more under the fallback user — the delivery counts as
successful and a warning is logged.

### Bitrix24: calls made outside Bitrix24 and CRM cards (moizvonki-style)

Extra `config` keys of the `bitrix24` integration (non-secret; GET always
returns them, with these defaults for rows saved before they existed):

| Key | Type / values | Default | Meaning |
|---|---|---|---|
| `save_external_calls` | bool (`true`/`false`, also `"1"`/`"0"`, `"yes"`/`"no"`) | `true` | `false` → a call whose number is **not** already in the Bitrix24 CRM is not sent at all (only calls of existing CRM entities are logged) |
| `create_card` | `"auto"` \| `"lead"` \| `"contact"` \| `"deal"` \| `"none"` | `"auto"` | card for an unknown number (see below) |
| `lead_source` | Bitrix24 SOURCE id: `A-Z 0-9 _`, ≤ 50 (upper-cased) | `"CALL"` | `CRM_SOURCE` of the lead / `SOURCE_ID` of a created contact or deal |
| `only_answered` | bool | `false` | `true` → missed calls are not sent |

Invalid values → `400 {message}` naming the key.

Read-only (GET): `crm_mode` — the portal's CRM mode detected via
`crm.settings.mode.get` (1 → `"classic"`, with leads; 2 → `"simple"`, without
leads; `""` = not detected yet), `crm_mode_checked_at` (ISO or null) and
`crm_mode_assumed` (true when detection failed, e.g. no crm scope, and
`"simple"` was assumed so no lead is ever created). Detected on save (when
enabled) and on *test*, cached and refreshed every 24 h (1 h when assumed).

Per call: the number is first looked up with
`telephony.externalcall.searchCrmEntities`.
- **Known number** (any entity): the call is registered bound to that entity
  (`CRM_CREATE=0`, `CRM_ENTITY_TYPE`/`CRM_ENTITY_ID`) — never a duplicate.
- **Unknown number**, `create_card`:
  - `auto` (default) — classic portal → as `lead`; simple-CRM portal → as
    `deal` (contact + deal). Never a lead on a portal without leads.
  - `lead` — `CRM_CREATE=1` + `CRM_SOURCE`; Bitrix24 creates the card itself.
    On a simple-CRM portal no lead is created: a contact is made instead and
    the delivery row / `last_error` carry the note "Bitrix24 portal lidlarsiz
    (oddiy CRM) — lid o'rniga kontakt yaratildi; …" (status stays ok).
  - `contact` — `crm.contact.add` (NAME = contact/caller name or the number,
    PHONE WORK, ASSIGNED_BY_ID, SOURCE_ID), call bound to that contact.
  - `deal` — the contact as above + `crm.deal.add` (TITLE `DooCall: <phone>`,
    CONTACT_ID, ASSIGNED_BY_ID, SOURCE_ID); the call binds to the contact, the
    deal links through it.
  - `none` — `CRM_CREATE=0`: the call stays in Bitrix24 telephony statistics,
    no card.
- Responsible user (`USER_ID`, `ASSIGNED_BY_ID`) = the operator's `user_map`
  entry, else `user_id`, else 1.
- Skipped calls (`save_external_calls=false` + unknown number, or
  `only_answered` + missed) get a delivery row `status: "ok"` with
  `error: "skipped: <reason>"`; the integration's health stays ok.
- Retries: `EXTERNAL_CALL_ID` dedup as before; a retry finds the contact an
  earlier attempt created and binds to it (no second contact/deal). If a
  `deal`-mode attempt created the contact but failed before the deal, the
  retry binds to the contact without creating the deal.

Webhook scopes: **telephony** + **crm** (required); **user** only for
`GET …/bitrix24/users`.

**Leads vs. simple CRM (help text):** Bitrix24 portals work in one of two CRM
modes. *Classic* portals use leads: every new inquiry starts as a lead. In
*simple CRM* (leads switched off), inquiries go straight to a deal plus a
contact. With "Avto" DooCall detects the mode and creates a lead on classic
portals and a contact + deal on portals without leads — it never creates a
lead on a portal without leads. Pick `contact` or `deal` for the same card
on every portal, or `none` to keep only the call in telephony statistics.

## AI analyses (Kotib Analytics results)

Kotib pushes one `analysis.completed` message per analysed call to the
company's secret URL; the cabinet reads the stored results.

### Inbound webhook — `POST /api/public/kotib/analysis/<token>` (no auth)

- URL: `https://<slug>.<DOMAIN_ROOT>/api/public/kotib/analysis/<token>` —
  token is per company (`secrets.token_urlsafe(32)`), created on Kotib
  connect (or lazily when the integrations list is opened), kept across
  re-saves, replaced by *rotate*, wiped by disconnect.
- Signature: once the admin saved the secret Kotib gave them, a valid
  signature is required (no unsigned bypass, no plain token/secret
  equality). Kotib does not name the algorithm, so every safe HMAC-SHA256
  variant over the **exact raw body** is accepted, each compared in
  constant time:
  - header `X-Kotib-Signature` (also `X-Signature`, `X-Webhook-Signature`,
    `X-Hub-Signature-256`);
  - value `<digest>`, `sha256=<digest>` / `SHA256=<digest>`, or
    `t=<ts>,v1=<digest>` (message `<ts>.<body>`);
  - digest hex (any case) or base64 standard/url-safe, with or without `=`
    padding;
  - key: the saved analysis secret, or the `webhook_secret` DooCall sent
    Kotib at connect, as UTF-8 text and also as hex-decoded bytes when it
    looks like hex.

  Before a secret is saved, messages are accepted on the token alone and
  stored with `signature_verified: false`.
- Rejected signatures (diagnostics carry metadata only, never the header
  value, a secret or the body): one `WARNING` per company per 10 min from
  `apps.integrations.kotib_analysis` ("kotib analysis signature mismatch")
  with the signature headers present, each header's length, charset class
  (hex/base64/other), prefix kind, body length, content type and the
  key/encoding names tried. The last 20 rejections per company are kept in
  the Django cache (Redis; key `kotib:analysis:rejects:<company_id>`, 7 days):
  `python manage.py shell -c "from apps.integrations import kotib_analysis
  as ka; print(ka.recent_rejections(<company_id>))"`.
- Responses: `200 {success, status: "stored", matched}` ·
  `200 {status: "ignored"}` for other events · `400` malformed (bad JSON,
  `audio_data_id` not a number, dates without offset) · `401` bad/missing
  signature · `404` unknown token (or a company subdomain that is not the
  token's company) · `410` Kotib integration disabled · `413` body > 2 MB.
- Storage (`integrations.CallAnalysis`): one row per (company,
  `audio_data_id`) — re-sends overwrite it (latest wins).
  `prompt_scores[].comment` is sanitized with nh3 (structural tags only:
  div p br b strong i em u ul ol li span table thead tbody tr td th h4 h5
  small; no attributes, links, images or styles). `audio_file_url` is NOT
  stored (it needs the Kotib key). `client_data.phone_number` is normalized
  with the company `phone_code`. `has_violation` = any `is_violation`
  criterion with a score < 0.
- Matching to our call: same company, `counterparty_number` == normalized
  client phone and |start − Kotib start| ≤ 120 s, nearest wins; when Kotib
  sends start == end, the call's start + duration is compared with the end.
  Unmatched rows keep `call: null` and are matched again on a re-send.

### Cabinet endpoints

Scoping: tenant-scoped; a non-admin cabinet user who is an operator sees
only analyses matched to their own calls (unmatched analyses are hidden from
them).

| Endpoint | Notes |
|---|---|
| `GET /ai/status` | `{success, kotib_connected, has_analyses, is_admin}` |
| `GET /ai/analyses` | `?date_from&date_to` (YYYY-MM-DD, company TZ, on the analysis start) `&employees=1,2&min_score&max_score&violations=1&search=<phone>&page` (30/page) → `{success, count, pages, page, summary: {count, avg_score (1 decimal, null if none), violations}, analyses: [row]}`; row = `{id, call_id (our call id or null), start_time, operator: {id, full_name} \| null, phone, final_score, summary, has_violation}`, newest first |
| `GET /ai/analyses/<id>` | `{success, analysis: {<row>, end_time, conversation_text, prompt_scores: [{key, name, score, comment_html, is_violation}], client_data: {phone_number, summary, answers: [{key, name, value}]}, call: {id, duration, direction, has_audio} \| null, signature_verified, received_at}}`; 404 when not visible |
| `GET /calls`, `GET /calls/<id>` | each call additionally has `ai: {analysis_id, final_score} \| null` (latest analysis) |

### Kotib card settings (company admin)

| Endpoint | Notes |
|---|---|
| `GET /settings/integrations` | the `kotib` row's `config` additionally has `analysis_webhook_url` ("" until a token exists), `analysis_secret` (masked or ""), `analysis_last_received_at` (ISO or null), `analysis_count` |
| `PUT /settings/integrations/kotib/analysis` | `{secret}` (1–256 chars; masked echo = unchanged) — stored only on our side, Kotib connect is not called → `{success, integration}`; 400 when Kotib isn't connected |
| `POST /settings/integrations/kotib/analysis/rotate` | new token → new URL, old URL 404 at once → `{success, integration}` |

Disconnecting Kotib wipes the token and secret (the URL then answers 404)
but keeps every stored analysis. The token, secret and transcripts are
never logged; audit rows carry no secrets.

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
