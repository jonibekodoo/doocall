"use client";

import { useMutation } from "@tanstack/react-query";
import { Banknote, CreditCard, PhoneCall } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { submitManualPayment } from "@/lib/api/endpoints";
import type { PaywallPayload } from "@/lib/api/types";
import { formatUzs } from "@/lib/format";

/** Full-screen paywall consuming the 402 SUBSCRIPTION_INACTIVE payload. */
export function PaywallScreen({ paywall }: { paywall: PaywallPayload }) {
  const t = useTranslations("paywall");
  const [requested, setRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useMutation({
    mutationFn: () => submitManualPayment(paywall.amount_due_uzs),
    onSuccess: () => setRequested(true),
    onError: (err: Error) => setError(err.message),
  });

  return (
    <div
      data-testid="paywall"
      className="grid min-h-screen place-items-center bg-bg p-4"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-surface p-8 shadow-lg">
        <span className="grid size-10 place-items-center rounded-md bg-danger/10 text-danger">
          <PhoneCall className="size-5" />
        </span>
        <h1 className="mt-4 font-[family-name:var(--font-display)] text-2xl font-semibold">
          {t("title")}
        </h1>
        <p className="mt-1 text-sm text-fg-muted">
          {paywall.reason === "trial_expired"
            ? t("trialExpired")
            : t("suspended")}
        </p>

        <dl className="tnum mt-6 space-y-2 rounded-md bg-surface-2 p-4 text-sm">
          <div className="flex justify-between">
            <dt className="text-fg-muted">{t("seats")}</dt>
            <dd>{paywall.seats}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-fg-muted">{t("perOperator")}</dt>
            <dd>{formatUzs(paywall.price_per_operator_uzs)} UZS</dd>
          </div>
          <div className="flex justify-between border-t border-border pt-2 font-semibold">
            <dt>{t("total")}</dt>
            <dd>{formatUzs(paywall.amount_due_uzs)} UZS</dd>
          </div>
        </dl>

        <p className="mt-6 text-xs font-medium uppercase tracking-wide text-fg-faint">
          {t("payWith")}
        </p>
        <div className="mt-2 flex gap-2">
          {paywall.providers
            .filter((provider) => provider !== "manual")
            .map((provider) => (
              <button
                key={provider}
                type="button"
                className="flex flex-1 items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold capitalize text-accent-fg hover:opacity-90"
              >
                <CreditCard className="size-4" /> {provider}
              </button>
            ))}
          <button
            type="button"
            data-testid="paywall-bank-btn"
            disabled={requested || request.isPending}
            onClick={() => request.mutate()}
            className="flex flex-1 items-center justify-center gap-2 rounded-md border border-accent px-4 py-2.5 text-sm font-semibold text-accent hover:bg-accent-soft disabled:opacity-50"
          >
            <Banknote className="size-4" /> Bank/Naqd
          </button>
        </div>
        {requested && (
          <p className="mt-3 rounded-md bg-accent-soft/60 p-2 text-xs text-accent">
            {t("bankRequested")}
          </p>
        )}
        {error && <p className="mt-3 text-xs text-danger">{error}</p>}
        <p className="mt-3 text-xs text-fg-faint">{t("manualNote")}</p>
      </div>
    </div>
  );
}
