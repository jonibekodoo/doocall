# PHASE 10 — Three-portal backend: integrators & cashback (completed)

## Session-start verification
`make up` / `make lint` / `make test` all green (174+53) before new work.
NOTE: `ADDENDUM_admin_integrator.md` is not present in the repo (searched);
A.1/A.2/A.5 were implemented from the requirements inlined in the brief —
flagged in code comments, consistent with the standing master-spec ruling.

## Delivered

1. **Roles (A.1)** — `superadmin` / `platform_admin` / `integrator` as
   platform Role rows (company=NULL) with permission sets where
   superadmin ⊃ platform_admin (platform_admin lacks settings, admin CRUD,
   overrides, payouts, impersonation). Login response now carries
   `role` + `portal` for frontend routing.
2. **Models (A.2)** — `apps.partners`: Integrator (unique 8-char referral
   code generator, override %, payout_details, suspend), PlatformSetting
   (+history, PricingSetting-style), CashbackAccrual (OneToOne→Payment =
   idempotency anchor, percent snapshot, accrued/reversed/paid_out),
   PayoutRequest (pending→approved→paid | rejected, processed_by);
   `Company.integrator` + `acquired_via` with **model-level immutability**
   (only the reassignment service may change the binding). Migrations clean.
3. **Cashback engine (A.5)** — hooked into `billing.apply_payment`, so all
   three providers accrue identically; months-limit with calendar-correct
   `add_months`; refund reversal; `balance_uzs` property (accrued − held).
4. **Admin API `/api/admin/v1`** — dashboard KPIs, companies
   list/detail/suspend/activate/extend-trial, superadmin reassignment,
   manual payment approval returning the fired accrual, integrator CRUD
   (override PATCH superadmin-gated inside the endpoint), cashback
   settings, platform-admin CRUD, payout queue + approve/reject/mark-paid,
   audit query, **impersonation**: 15-minute AccessToken with
   `impersonated`/`impersonator_id` claims, start/stop audited.
5. **Partner API `/api/partner/v1`** — dashboard (12-month SQL series),
   my-companies (commercial fields only), on-behalf registration (trial +
   `integrator_manual` binding), accrual ledger with filters, payout
   create/list, profile/payout-details. **Referral**: public registration
   accepts `ref` (case-insensitive); invalid/suspended → self_signup,
   never blocks.
6. **Isolation** — integrators 403 on all cabinet endpoints (no company →
   HasCompany guard); partner payloads contain zero operational fields
   (asserted); foreign companies 404; company users 403 on both portals.

## Tests — 59 new, `apps.partners` coverage **95%** (target ≥85%)

- **Matrix**: 13 endpoints × 5 roles + anonymous, table-driven; override
  editing superadmin-only; suspended integrator loses the portal.
- **Cashback**: default 10% math, 15% override, all three providers,
  unbound/suspended no-accrual, double-processing → one accrual, percent
  change affects only future payments (snapshot + history row), months
  limit at boundary with frozen time, refund reversal (idempotent),
  balance property, payout lifecycle incl. rejected-releases-balance and
  oldest-first allocation, invalid transitions blocked, reassignment keeps
  old accruals + direct mutation raises.
- **Referral**: valid/lowercase code binds, invalid & suspended fall back,
  on-behalf creates trial and the client can log into the cabinet.
- **Impersonation**: token ≤15 min, `impersonated` claim, works against
  cabinet API, start/stop audit-logged; login portal hint verified.
- **Functional**: every admin/partner endpoint exercised (KPIs, filters,
  lifecycle actions, settings roundtrip, admin CRUD, payout queue,
  audit filters, monthly series math, ledger filters, profile update).

## Verification
`make lint` → exit 0 (117 files mypy-clean) · `make test` → exit 0:
**233 backend passed** (174 prior + 59 new), 53 frontend; backend total
coverage 94%, partners app 95%.

## Seed
`seed_demo` now creates: DEMOINT1 (10% default) with Ahlan House bound via
reassignment, DEMOINT2 (15% override) with a manually-registered client
company, payments generating accruals on both paths, one pending payout.
Logins: `partner1@demo.uz` / `partner2@demo.uz` / `super@doocall.uz`
(all `demo1234`).

## Carry-over → Phases 11–12
Frontend portals (admin + partner UIs) per PART A; impersonation banner UI;
payout notification emails.
