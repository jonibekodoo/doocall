# dooCall — Billing

## Model

Seat-based, monthly, postpaid:

- **Seat** = an ACTIVE `OperatorProfile` of the company. Seats are counted at
  invoice-generation time, so an operator added mid-period first appears on
  the invoice for the period in which they were added.
- **Price** = `PricingSetting.price_per_operator_uzs` (company row overrides
  the single global row; both history-tracked). The `Subscription` holds a
  **price snapshot** for the running period.
- **Price changes apply NEXT period only**: the period-end invoice always
  bills the snapshot; the snapshot refreshes from PricingSetting when the
  period rolls (`services.roll_period`). Covered by an explicit test.
- **Period** = 30 days (`services.PERIOD_DAYS`).

## Subscription state machine (`apps/billing/services.py`)

```
trial ──activate──▶ active ──suspend──▶ suspended
  │                   ▲                     │
  │                   └────activate─────────┘   (payment received)
  └──suspend/cancel──▶ …      any state ──cancel──▶ canceled (terminal)
```

Transitions are enforced (`InvalidTransition`); every transition syncs
`Company.status` (the flag the mobile API's 402 gate reads) and writes an
`AuditLog` row.

## Scheduled jobs (Celery beat — `CELERY_BEAT_SCHEDULE`)

| Task | When | What |
|---|---|---|
| `suspend_expired_trials` | nightly 00:15 | `Company.status=trial` with `trial_ends_at` in the past → suspended (subscription + company + audit) |
| `generate_due_invoices` | daily 01:00 | Active subscriptions whose `current_period_end ≤ now` → invoice the finished period at the snapshot price, roll the period, refresh the snapshot |
| `cleanup_expired_audio` | nightly 02:00 | **Stub** — schedule reserved; real retention job lands in Phase 9 |

Tasks accept `now_iso` for deterministic testing (frozen time).

## Payments

`PaymentProvider` interface (`apps/billing/providers/`): `verify(request)`
(signature/credential check) → `handle(request)` (parse + apply) →
`bad_signature_response()`. All providers converge on
**`services.apply_payment`**: payment approved → invoice paid → company
(re)activated — suspended/trial companies get a fresh 30-day period; already
active companies get +30 days appended. Idempotent (webhook retries can't
double-extend).

| Provider | Transport | Signature |
|---|---|---|
| `manual` | none — admin action "Approve selected payments" in Django admin | n/a (admin auth) |
| `payme` | JSON-RPC webhook `/api/web/v1/billing/webhooks/payme` (CheckPerform/Create/Perform/Cancel/Check) | `Authorization: Basic base64("Paycom:"+PAYME_SECRET_KEY)`; amounts in tiyin |
| `click` | SHOP-API prepare(0)/complete(1) webhook `/api/web/v1/billing/webhooks/click` | `sign_string` = md5 chain incl. `CLICK_SECRET_KEY` |

Credentials are env-driven (`PAYME_*`, `CLICK_*` in `.env`); adapters are
sandbox-shaped and tested with valid + tampered payloads.

## Web auth & registration funnel

- `POST /api/web/v1/auth/register` — company name + admin email + phone +
  password → `Company` (status=**trial**, `trial_ends_at = now + trial_days`
  from PricingSetting), admin `User`, trial `Subscription`. Audited.
- `POST /auth/login` — SimpleJWT: access token in body, refresh token in an
  **httpOnly cookie** scoped to `/api/web/v1/auth`. `POST /auth/refresh`
  rotates + blacklists the old token; `POST /auth/logout` blacklists + clears.
- `POST /auth/password-reset[/confirm]` — token email (Mailhog in dev).
- Email verification behind `EMAIL_VERIFICATION_ENABLED` (default off):
  when on, login is blocked (403 `EMAIL_NOT_VERIFIED`) until
  `POST /auth/verify-email`.

## Enforcement

- **Mobile**: suspended/expired company → every `/api/call/v1/*` call
  (including `/auth`) returns **402 `SUBSCRIPTION_INACTIVE`** — driven by
  `Company.status`, which the state machine and nightly sweep maintain.
- **Web cabinet**: `GET /api/web/v1/billing/status` returns 200 with
  seats/price/amount-due, or **402** with a `paywall` object
  (`reason, seats, price_per_operator_uzs, amount_due_uzs, providers`) that
  the frontend renders as the paywall screen.

## Audit trail

`core.AuditLog` rows for: `web.register`, `web.login`, `web.password_reset`,
`payment.applied`, `payment.approve` (admin), `payment.webhook` /
`payment.webhook_rejected`, `subscription.activated` / `.suspended` /
`.canceled`, `invoice.generated`.
