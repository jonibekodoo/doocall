# PHASE 12 — Partner portal (`/partner`) + Addendum wrap-up

Status: **DONE** · Scope: ADDENDUM PART A — integrator-facing frontend
(MoySklad-style), landing `?ref=` attribution, full-loop E2E, final docs.

## Phase-11 verification (entry gate)

- `make lint` exit 0 · `make test` exit 0 before any Phase-12 change.
- Phase-11 Playwright suite re-run: **4/4 passed** on the seeded stack.
- One backend addition required by this phase's brief:
  `PlatformSetting.min_payout_uzs` (default **50 000**, migration
  `partners.0002`) — enforced in `request_payout`, exposed in
  `GET /api/partner/v1/payouts` and the partner dashboard. The stricter
  minimum broke 6 pre-existing payout tests → partners `conftest` now
  seeds `min_payout_uzs=1000` and a dedicated
  `test_cannot_request_below_minimum` covers the real default.

## Built

1. **Partner shell** — light sidebar + emerald **Partner** badge
   (`data-testid="partner-badge"`), i18n nav (ru/uz/en), same Phase-6
   tokens; guarded by the `doocall_portal=partner` middleware cookie
   (real enforcement stays API-side).
2. **Обзор** (`/partner`) — 6 stat cards (balance, accrued total, month
   cashback, companies, effective %, min payout) + 12-month accrual
   BarChart (Recharts) + latest accruals table.
3. **Мои компании** — list + detail with **commercial data only**
   (plan/seats/status/payments/accruals; no calls, contacts, users or
   devices anywhere in the partner API surface).
4. **Добавить клиента** — two tabs:
   - *Referral*: canonical link (`referralLink()` builder), copy button,
     QR (api.qrserver.com), promo code. Landing `RefCapture` stores
     `?ref=` in a **30-day** `doocall_ref` cookie; `/register` reads it
     and passes `ref` (invalid/suspended codes silently fall back to
     `self_signup` — registration is never blocked).
   - *Manual*: on-behalf registration → `TempPasswordReveal` —
     crypto-random 12 chars, no `O0Il1`, **shown exactly once** with
     copy + mailto, gone after «OK».
5. **Начисления** — filterable ledger (status/period), totals footer,
   client-side CSV export.
6. **Выплаты** — balance card, request dialog with
   `validatePayoutAmount` (`frontend/lib/payout.ts`:
   invalid / below_minimum / over_balance), history with status chips.
7. **Профиль** — code, effective %, payout details editor.

## Tests

- **Vitest: 85 passed** (Phase-12 file: payout-validation truth table
  incl. the over-balance-beats-minimum edge, referral-link builder
  (custom base, trailing-slash strip, URL-encoding), temp-password
  generator + reveal-once component (clipboard asserted through
  userEvent's stub), UZS/percent formatting).
- **Playwright `e2e/phase12.spec.ts`: full partner loop passed** —
  and re-run **twice consecutively green** after being made
  run-independent:
  1. partner1 login → overview shows seeded balance + `10.00%`
     (test setup pins the global % via superadmin API);
  2. referral tab → fresh browser context visits `/?ref=DEMOINT1` →
     registers → company appears as `trial` / `referral_link`;
  3. manual on-behalf registration → `integrator_manual`;
  4. superadmin creates a 400 000 UZS manual payment (backend shell) →
     approve → response `cashback_accrued_uzs === 40000`;
  5. **relative balance assert**: `balance_after − balance_before ===
     40 000` (was an absolute `>= 40000` that broke on re-runs after
     earlier runs drained the balance via paid payouts) + auto top-up
     if the balance dips under the 50 000 minimum;
  6. payout 50 000 request → pending → superadmin approve + mark-paid →
     history shows **paid**;
  7. isolation probe: integrator token on `/api/web/v1/calls` → **403**.

## Final gates (outputs pasted)

```
make lint  → exit 0   (ruff + ruff format + mypy: 117 files clean;
                       next lint ✔ · prettier ✔ · tsc --noEmit ✔)
make test  → exit 0
  backend : 238 passed  (partners app: 64 tests, 95% coverage)
            TOTAL coverage ~94% (CI gate: 85%)
  frontend: Vitest 85 passed
Playwright: phase11 4/4 · phase12 full loop 1/1 (×2 consecutive runs)
```

## Addendum wrap-up docs

- `docs/architecture.md` — three-portal mermaid + PART A section.
- `README.md` — portal table rows, status → Phases 1–12.
- `docs/COMPLIANCE_CHECKLIST.md` — section **C (ADDENDUM PART A)**
  C1–C13 all ✅; summary **71 items: 67 done, 4 deferred** (master-spec
  pins, real Payme/Click merchant creds, APK artifact, host TLS certs).

## Visual evidence

`docs/screenshots/phase12-partner-overview.png`,
`phase12-partner-add.png`.

## Known placeholders (unchanged)

Master spec (`CLAUDE_CODE_PROMPT_dooCall.md`) and
`ADDENDUM_admin_integrator.md` were never present on this machine; all
work executed from the per-phase brief texts + `backend-api-docs.md`,
with placeholder values flagged inline. Production referral base URL
(`https://doocall.uz`) is env-overridable.
