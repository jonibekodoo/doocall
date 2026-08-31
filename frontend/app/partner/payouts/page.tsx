"use client";

/** A.5 Payouts — balance card, request dialog, history. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useToastStore } from "@/components/ui/Toast";
import {
  fetchPartnerPayouts,
  fetchPartnerProfile,
  requestPayout,
} from "@/lib/api/partner";
import { formatUzs } from "@/lib/format";
import { validatePayoutAmount } from "@/lib/payout";

function PayoutDialog({
  balance,
  minimum,
  details,
  onClose,
  onDone,
}: {
  balance: number;
  minimum: number;
  details: Record<string, string>;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useTranslations("partner");
  const [amount, setAmount] = useState("");
  const error =
    amount === ""
      ? null
      : validatePayoutAmount(Number(amount), balance, minimum);
  const request = useMutation({
    mutationFn: () => requestPayout(Number(amount)),
    onSuccess: () => {
      useToastStore.getState().push({ kind: "success", text: "OK" });
      onDone();
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">{t("requestPayout")}</h2>
        <p className="tnum mb-2 text-sm text-fg-muted">
          {t("available")}: <b>{formatUzs(balance)} UZS</b> · {t("minAmount")}:{" "}
          {formatUzs(minimum)} UZS
        </p>
        <input
          type="number"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder={t("amount")}
          data-testid="payout-amount"
          className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
        />
        {error && (
          <p
            role="alert"
            data-testid="payout-error"
            className="mt-1.5 text-xs text-danger"
          >
            {error === "below_minimum"
              ? `${t("minAmount")}: ${formatUzs(minimum)} UZS`
              : error === "over_balance"
                ? `${t("available")}: ${formatUzs(balance)} UZS`
                : "—"}
          </p>
        )}
        <p className="mt-3 text-xs font-semibold uppercase text-fg-faint">
          {t("payoutDetails")}
        </p>
        <p className="tnum mt-1 rounded bg-surface-2 px-3 py-2 text-xs">
          {Object.values(details).join(" · ") || "—"}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-sm"
          >
            ✗
          </button>
          <button
            type="button"
            data-testid="payout-submit"
            disabled={amount === "" || error !== null || request.isPending}
            onClick={() => request.mutate()}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
          >
            {t("requestPayout")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PartnerPayoutsPage() {
  const t = useTranslations("partner");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const { data, isPending } = useQuery({
    queryKey: ["p-payouts"],
    queryFn: fetchPartnerPayouts,
  });
  const { data: profile } = useQuery({
    queryKey: ["p-profile"],
    queryFn: fetchPartnerProfile,
  });

  return (
    <div data-testid="partner-payouts">
      <h1 className="mb-4 text-xl font-semibold">{t("payouts")}</h1>
      {data && (
        <div className="mb-5 flex flex-wrap items-center gap-4 rounded-lg border border-border bg-surface p-4">
          <div>
            <p className="text-xs font-semibold uppercase text-fg-faint">
              {t("balance")}
            </p>
            <p
              className="tnum text-2xl font-bold text-accent"
              data-testid="payout-balance"
            >
              {formatUzs(data.balance_uzs)} UZS
            </p>
          </div>
          <button
            type="button"
            data-testid="payout-open"
            onClick={() => setOpen(true)}
            className="ml-auto rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg"
          >
            {t("requestPayout")}
          </button>
        </div>
      )}

      <section className="rounded-lg border border-border bg-surface">
        <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
          {t("history")}
        </p>
        <ul className="divide-y divide-border" data-testid="payout-history">
          {isPending
            ? Array.from({ length: 3 }).map((_, i) => (
                <li key={i} className="px-4 py-3">
                  <div className="h-4 animate-pulse rounded bg-surface-3" />
                </li>
              ))
            : (data?.payouts ?? []).map((p) => (
                <li
                  key={p.id}
                  className="flex items-center gap-2 px-4 py-2.5 text-sm"
                >
                  <span className="tnum flex-1 font-medium">
                    {formatUzs(p.amount_uzs)} UZS
                  </span>
                  <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">
                    {p.status}
                  </span>
                  <span className="tnum text-xs text-fg-faint">
                    {p.requested_at.slice(0, 10)}
                  </span>
                </li>
              ))}
          {!isPending && (data?.payouts ?? []).length === 0 && (
            <li className="px-4 py-8 text-center text-sm text-fg-faint">
              {t("noPayouts")}
            </li>
          )}
        </ul>
      </section>

      {open && data && (
        <PayoutDialog
          balance={data.balance_uzs}
          minimum={data.min_payout_uzs}
          details={profile?.payout_details ?? {}}
          onClose={() => setOpen(false)}
          onDone={() =>
            queryClient.invalidateQueries({ queryKey: ["p-payouts"] })
          }
        />
      )}
    </div>
  );
}
