# PHASE 5 — Web cabinet API (completed)

## Phase 4 verification (session start)

`make test` green; live curl E2E: register → company trial (+14d) → JWT
login with httpOnly refresh cookie. All passed before new work.

## Delivered (all `/api/web/v1/`, JWT + tenant-scoped via `CabinetView`)

1. **Dashboard** — period (today/3d/7d) general matrix, per-operator
   activity, latest answered, unanswered-now — each with operator filter.
2. **Calls** — §6.2 filter set (employees[], date range, direction, status,
   name-or-phone search with E.164 normalization, min duration, SIM), 30/page
   with total count, duration/date sort, detail with presigned audio,
   admin-only delete, CSV/XLSX export as Celery task (streaming `values()` →
   MinIO → presigned link, `ExportJob` status polling), per-user column
   preferences.
3. **Contacts** — CRUD, multi-phone (normalized/deduplicated), responsible
   user, search, create-from-call (prefills number, back-fills
   `resolved_name` on all matching history, 409 on duplicate number), detail
   with call history.
4. **Reports** — 7 endpoints (general, weekday matrix, period counts with
   unique-numbers flag, per-employee, per-client, **unanswered with the exact
   last-call-missed / drops-off-after-success semantic**, last-contact). All
   aggregation in SQL (single-query aggregates, `DISTINCT ON` latest-per-
   number, bounded-set enrichment queries — no Python loops over full
   querysets).
5. **Settings** — groups CRUD; users CRUD (operator creation returns mobile
   credentials exactly once; deactivate toggle hits billable seats + kills the
   operator api_key instantly); devices list with online status, per-SIM
   recording toggle + number set, device delete; account-wide toggles;
   company API-key generate/rotate; webhook URL config with HMAC-SHA256
   signing (secret shown once, test-delivery endpoint, fires on every upload
   via `transaction.on_commit` → Celery with retries); license endpoint
   (trial countdown/period, live seats × price, payment history).

## Schema additions (migrations clean)

`OperatorGroup`, `OperatorProfile.group`, `User.is_company_admin`,
`SimCard.recording_enabled`, `Company.feature_flags/api_key/webhook_url/
webhook_secret`, `Contact.responsible`, `web.CallColumnPreference`,
`web.ExportJob`. Registration now marks the first user `is_company_admin`.

## Tests — 166 backend passed, total coverage **94%**

- **Report correctness**: 40-call hand-computed fixture (4 days × 2 operators
  × 6 numbers, every expected number derived by hand in `fixture_calls.py`);
  exact assertions for ALL 7 report endpoints incl. the unanswered drop-off
  (N2/N5 recovered → excluded; N4/N6 never answered → 5 attempts, null
  last_success; live drop-off re-check after a fresh successful call) and the
  unique-numbers flag (6 vs 10 per day).
- **Calls list**: filter combinations, pagination totals (40→2 pages),
  search by name/number fragment, sort, admin-only delete (403 for members),
  column prefs, CSV export (valid file, 21 filtered rows) + XLSX (41 rows).
- **Seat count**: deactivate toggle → license seats 2→1 and total price drop
  in the SAME request sequence; operator's mobile key 401s.
- **Webhook**: fires on upload (on-commit), HMAC-SHA256 signature verified
  independently against the company secret; secret returned exactly once.
- **Contacts**: normalization/dedup, search, update/delete, history by E.164,
  from-call linking (8 past calls back-filled), duplicate → 409.
- **Perf guard** (marked `perf`, CI-skipped, run locally on the 12k seed):

  | Endpoint | ms |
  |---|---|
  | dashboard?period=7d | 22.0 |
  | reports/general | 4.6 |
  | reports/weekday-matrix | 8.3 |
  | reports/period-counts (day) | 6.3 |
  | reports/period-counts (week+unique) | 17.6 |
  | reports/per-employee | 7.9 |
  | reports/per-client | 17.6 |
  | reports/unanswered | 97.0 |
  | reports/last-contact | 31.3 |
  | calls?page=1 | 2.0 |

  All < 300ms budget. (Perf work: correlated-subquery latest-per-number was
  1.7s; replaced with materialized `DISTINCT ON` id list + bounded enrichment
  queries.)

## Notes / carry-over

- Master spec §6 still absent — endpoint set built from the task message's
  screen list; reconcile §6.4 report names when the spec lands.
- `recording_enabled` / account toggles are stored + exposed; the mobile
  contract gains a "config" response for them in a later phase (device app
  doesn't poll config yet).
- Rollup tables not needed at 12k-row scale (all endpoints <100ms); revisit
  if per-client/report latency grows past the budget at production volume.
