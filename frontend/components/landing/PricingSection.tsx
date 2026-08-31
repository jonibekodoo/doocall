"use client";

/** Pricing section: LIVE per-operator price + seat-count slider. */

import { useEffect, useState } from "react";

import { formatUzs } from "@/lib/format";
import {
  clampSeats,
  computeMonthlyTotal,
  MAX_SEATS,
  MIN_SEATS,
} from "@/lib/pricing";

interface Strings {
  title: string;
  perOperator: string;
  seats: string;
  total: string;
  trial: string; // contains {days}
}

export function PricingSection({ strings }: { strings: Strings }) {
  const [price, setPrice] = useState<number | null>(null);
  const [trialDays, setTrialDays] = useState<number>(14);
  const [seats, setSeats] = useState(5);

  useEffect(() => {
    fetch("/api/public/pricing")
      .then((response) => response.json())
      .then((body) => {
        setPrice(body.price_per_operator_uzs);
        setTrialDays(body.trial_days);
      })
      .catch(() => setPrice(50000)); // graceful fallback, keeps layout stable
  }, []);

  const total = price === null ? null : computeMonthlyTotal(seats, price);

  return (
    <section id="pricing" className="mx-auto max-w-3xl px-6 py-20">
      <h2 className="text-center font-[family-name:var(--font-display)] text-3xl font-bold sm:text-4xl">
        {strings.title}
      </h2>

      <div className="mt-10 rounded-2xl border border-border bg-surface p-8 shadow-lg">
        {/* Fixed heights everywhere — no layout shift while price loads. */}
        <div className="flex min-h-16 items-baseline justify-center gap-2">
          <span
            className="tnum font-[family-name:var(--font-display)] text-5xl font-bold text-accent"
            data-testid="unit-price"
          >
            {price === null ? "· · ·" : formatUzs(price)}
          </span>
          <span className="text-sm text-fg-muted">
            UZS {strings.perOperator}
          </span>
        </div>

        <div className="mt-8">
          <div className="flex items-center justify-between text-sm">
            <span className="text-fg-muted">{strings.seats}</span>
            <span
              className="tnum text-lg font-semibold"
              data-testid="seat-count"
            >
              {seats}
            </span>
          </div>
          <input
            type="range"
            min={MIN_SEATS}
            max={MAX_SEATS}
            value={seats}
            onChange={(event) =>
              setSeats(clampSeats(Number(event.target.value)))
            }
            className="mt-2 w-full accent-[var(--accent)]"
            data-testid="seat-slider"
            aria-label={strings.seats}
          />
        </div>

        <div className="mt-6 flex min-h-12 items-baseline justify-between border-t border-border pt-4">
          <span className="text-sm text-fg-muted">{strings.total}</span>
          <span
            className="tnum font-[family-name:var(--font-display)] text-3xl font-bold"
            data-testid="monthly-total"
          >
            {total === null ? "· · ·" : `${formatUzs(total)} UZS`}
          </span>
        </div>

        <p className="mt-4 text-center text-xs text-fg-faint">
          {strings.trial.replace("{days}", String(trialDays))}
        </p>
      </div>
    </section>
  );
}
