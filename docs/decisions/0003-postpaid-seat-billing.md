# ADR-0003: Postpaid seat billing with per-period price snapshots

**Status**: accepted (Phase 4)

**Context**: Pricing is per active operator per 30-day period; admins can
change the global price at any moment; invoices must be predictable.

**Decision**: `Subscription` holds a price snapshot for the RUNNING period.
At period end the finished period is invoiced at the snapshot (seats counted
at invoice time), then the snapshot refreshes from `PricingSetting` — price
changes therefore apply to the NEXT period only. Payments (manual/Payme/
Click) all converge on one idempotent `apply_payment` that settles the
invoice and (re)activates + extends the company.

**Consequences**: mid-period hires appear on the next invoice; a company is
never retro-billed after a price change; webhook retries cannot
double-extend a period.
