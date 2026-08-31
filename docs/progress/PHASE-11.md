# PHASE 11 — Admin portal frontend (completed)

## Phase 10 verification (session start)
`make test` green (233+53); live curls with the seeded superadmin JWT:
dashboard KPIs (33 companies, MRR 300k) and a payout approve — both worked.
NOTE: `ADDENDUM_admin_integrator.md` remains absent from the repo — A.1/A.3
executed from the brief, consistent with prior rulings.

## Backend additions (the A.3 screens needed them)
Dashboard KPIs extended with `calls_today` + 30-day `payments_series`/
`calls_series`; `GET /api/admin/v1/payments` (provider/status filters, shows
fired cashback per payment) + `POST /payments/<id>/refund` (marks refund,
**reverses cashback**, audited, double-refund blocked); superadmin
`GET/PUT /settings/pricing` with history; `GET /integrators/<id>` full
detail (profile, effective %, per-company totals, accrual ledger, payouts).
Refresh response now also returns `user{role, portal}` so full-page reloads
recover the role. 4 new backend tests (63 partners total).

## Delivered (frontend)

1. **Routing & guard (A.1)** — single `/login`; post-auth redirect by
   `portal` (`homeFor`); `doocall_portal` routing-hint cookie +
   **Next middleware** rewriting wrong-portal `/admin/*` hits to a `/403`
   page (real security stays API-side, verified by 403 assertions);
   `/api/admin` + `/api/partner` dev-proxy rewrites added.
2. **Admin identity** — near-black sidebar variant (`#141817`), amber
   **Admin badge**, user email + role in the footer, shared Phase-6 tokens.
3. **Screens (A.3)**: Dashboard (6 KPI cards + two 30-day sparklines, SVG,
   dependency-free); Companies (search/status filter → detail with
   subscription/seats/operators/payments, integrator badge,
   suspend/activate with confirm, **extend-trial dialog with required
   reason ≥3 chars**, **impersonate button — superadmin only**); Payments
   (provider/status filters, confirm-dialog approval whose success toast
   names the fired cashback amount, refund marking); Pricing (superadmin:
   editor + history + «applies next period» notice); Integrators (list with
   code/companies/override/balance, create dialog incl. optional override %,
   detail with effective-% editor showing `override ?? default`, per-company
   totals, accrual ledger, payout approve/reject/mark-paid, suspend toggle);
   Cashback settings (superadmin: % + months limit + live worked example
   «100 000 UZS × 20% = 20 000 UZS»); Platform admins (superadmin CRUD);
   Audit (action/date filters).
4. **platform_admin vs superadmin** — superadmin-only nav items are
   **absent** (filtered out, not disabled); override editing inside the
   integrator endpoint is separately 403-gated server-side.
5. **Impersonation UX** — button → 15-min token stored in sessionStorage →
   cabinet opens with a **persistent amber banner** («Режим просмотра …») →
   exit restores the admin session via the refresh cookie, fires the
   audited stop call, returns to `/admin`.

## Tests

- **Vitest: 69 passed** (7 new): homeFor redirect table, KPI card mapping
  (money formatting + status hint), effective-% display (override vs
  default), worked cashback example incl. rounding, payout-action state
  machine availability, extend-trial validation, superadmin-only nav
  filtering.
- **Playwright: 4 passed** on the seeded stack:
  1. superadmin — KPIs render (zero console errors) → create integrator
     with **25% override** → detail shows «25.00 (override)» → approve a
     pending payout → change global cashback % (worked example updates) →
     **audit shows both** `payout.approved` and `admin.integrator_created`;
  2. platform_admin (provisioned via API) — superadmin sections absent from
     nav AND `settings/pricing`/`settings/cashback` return **API 403**
     while staff endpoints return 200;
  3. company admin — `/admin` renders the **403 page**;
  4. impersonation — banner appears in the cabinet with the company slug,
     exit returns to the admin shell, banner gone.
- `make lint` exit 0 · `make test` exit 0 (**237 backend + 69 frontend**).

## Bugs found by the tests (and fixed)
- Dev proxy lacked `/api/admin` + `/api/partner` rewrites → admin data
  silently empty.
- `export let sessionUser` live-binding read stale null under SWC/webpack
  interop → replaced with a `getSessionUser()` getter.
- `tryRefresh` wasn't capturing the user payload (an earlier patch missed
  after prettier reformat) → role lost on full page reloads; fixed and
  covered by the impersonation E2E which hard-navigates.

## Visual evidence
`docs/screenshots/phase11-admin-dashboard.png` (dark shell, badge, KPIs,
sparklines), `phase11-admin-integrators.png`.

## Carry-over → Phase 12
Partner portal frontend (`/partner`) per PART A; the middleware guard and
portal routing already support it (`homeFor("partner") → /partner`).
