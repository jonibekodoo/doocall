# dooCall — Cashback engine (Addendum A.5)

## Actors & knobs

* **Integrator** — brings companies (referral link, manual on-behalf
  registration, or superadmin reassignment). Has a unique 8-char
  `referral_code` and an optional `cashback_percent_override`.
* **PlatformSetting** (singleton, history-tracked): `default_cashback_percent`
  (10%) and `cashback_months_limit` (12) — superadmin-only editing.

## Accrual lifecycle

```
Payment approved (manual admin / Payme webhook / Click webhook)
        │  all providers converge on billing.apply_payment()
        ▼
accrue_cashback(payment)          ← idempotent: OneToOne(payment)
  ├─ company unbound / integrator suspended → no accrual
  ├─ payment after company's first N months → no accrual (months limit)
  └─ else → CashbackAccrual(status=accrued,
              percent = override or default   ← SNAPSHOT at accrual time,
              amount  = round(amount × %))
```

**Example.** Company bound to an integrator with 15% override pays
200 000 UZS → accrual of 30 000 UZS at percent snapshot `15.00`. The
platform default later changing to 25% does NOT touch this row — only
future payments accrue at the new rate.

## Reversal

Refund → `reverse_cashback(payment)`: status → `reversed`, timestamped,
audited, idempotent. Reversed rows never count toward balance.

## Balance & payouts

```
balance = Σ accruals(status=accrued) − Σ payouts(status ∈ {pending, approved})
```

Payout flow: integrator requests (≤ balance) → superadmin `approve` →
`mark-paid` (allocates oldest accruals to the payout, marking them
`paid_out`) or `reject` at any pre-paid step (**releases the hold**).
Every transition is audit-logged with the acting user.

## Reassignment

Superadmin-only (`reassign_integrator`): existing accruals REMAIN with the
original integrator; only future payments accrue to the new one. Direct
mutation of `Company.integrator` raises — the service is the single door.

## Month-limit semantics

`cutoff = company.created_at + cashback_months_limit months` (calendar
arithmetic, day-clamped). A payment accrues iff its `approved_at < cutoff`.
Tested with frozen time at limit−1 month (accrues) and limit+1 day (does not).
