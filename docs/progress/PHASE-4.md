# PHASE 4 — Web auth, billing engine, payments (completed)

## Phase 3 verification (session start)

`make test` green (69 + 2) and manual curl replays of `/auth` (full payload)
and `/upload` against the dev stack — both succeeded (§5.4-shaped response,
`resolved_name` from catalogue).

## Delivered

1. **Web auth (`apps.web`, `/api/web/v1/`)** — registration funnel
   (company+admin+trial subscription in one call, slug-unique, email-unique),
   SimpleJWT login with access-in-body + refresh in httpOnly cookie
   (path-scoped), refresh **rotation with blacklist**, logout, password reset
   via Mailhog, email verification behind `EMAIL_VERIFICATION_ENABLED`
   (default off). New `User.email_verified` field (migration accounts.0002);
   `rest_framework_simplejwt.token_blacklist` installed + migrated.
2. **Billing engine (`apps/billing/services.py`)** — seat count = active
   operators; total = seats × snapshot price; strict state machine
   trial→active⇄suspended→canceled (terminal) with `Company.status` sync +
   audit on every transition; `roll_period` invoices the finished period at
   the snapshot and refreshes the snapshot after — price changes hit the
   NEXT period only (tested).
3. **Beat jobs** (`CELERY_BEAT_SCHEDULE`, DatabaseScheduler syncs on start):
   nightly trial-expiry suspension (00:15), daily invoice sweep (01:00),
   audio-retention **stub** (02:00, real job Phase 9). All accept `now_iso`.
4. **Payments** — `PaymentProvider` interface; `manual` fully wired (admin
   approve → `services.apply_payment` → invoice paid + company active +
   period extended, idempotent); **Payme** (JSON-RPC, Basic-auth secret,
   tiyin amounts, Check/Create/Perform/Cancel/CheckTransaction) and **Click**
   (prepare/complete, md5 sign chain) adapters with env credentials; webhook
   endpoints `/api/web/v1/billing/webhooks/<provider>`.
5. **Enforcement** — mobile 402 now driven by the real subscription state
   (sweep → `Company.status` → Phase-3 gate); web `GET /billing/status`
   returns 402 + `paywall{reason,seats,price,amount_due,providers}`.
6. **AuditLog** — register/login/password-reset/payment/webhook/suspension/
   activation/invoice events.

## Tests (43 new; billing app coverage **91%**, target ≥85%)

- Trial expiry with frozen time → company suspended → mobile upload 402.
- Invoice math: seats×price; inactive seats excluded; mid-period operator →
  next invoice; **price change applies next period only**; period rolls +30d;
  sweep only invoices due subscriptions; suspended not invoiced.
- Manual approval: suspended trial company → active, period extended, invoice
  paid, audited; **idempotent** (retry can't double-extend).
- Payme: valid Check→Create→Perform E2E (invoice paid, company active);
  tampered/missing credentials rejected (nothing processed); wrong amount;
  cancel/check states; unknown method/transaction.
- Click: valid prepare→complete E2E; tampered-after-signing payload and
  wrong-secret rejected with SIGN error; unknown provider/manual → 404.
- JWT flow: httpOnly cookie flags, protected endpoint via access token,
  **refresh rotation blacklists the old token**, logout clears + blacklists,
  bad password 401, missing cookie 401.
- Password reset E2E via mail outbox; no account enumeration; bad token 400.
- Email-verification flag: off→no mail; on→403 until verified, then 200.
- Paywall: suspended company → 402 with exact payload key set.

## Verification evidence

- `make test` → exit 0: **112 backend passed** (69 prior + 43 new), 2
  frontend; total backend coverage 92%.
- Backend lint: ruff + format + strict mypy clean (82 files).
- Migrations clean (`accounts.0002`, token_blacklist).

## Notes / carry-over

- Payme/Click adapters are sandbox-shaped per public protocol docs; real
  merchant-cabinet onboarding (fiscalization fields, real endpoints) to be
  finalized when credentials exist — the interface + signature layer won't
  change.
- Master spec (§4/§6.5/§7/§13) still absent — executed from the task message.
- JWT dev secret lengthened to ≥32 bytes (RFC 7518 warning removed).
