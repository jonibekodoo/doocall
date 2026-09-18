"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import { fetchSalesPayouts, requestSalesPayout } from "@/lib/api/sales";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = {
  pending: "bg-warning/15 text-warning",
  approved: "bg-accent-soft text-accent",
  paid: "bg-accent-soft text-accent",
  rejected: "bg-danger/10 text-danger",
};

export default function SalesPayoutsPage() {
  const t = useTranslations("sales");
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const { data } = useQuery({ queryKey: ["sales-payouts"], queryFn: fetchSalesPayouts });

  const request = useMutation({
    mutationFn: () => requestSalesPayout(Number(amount), ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-payouts"] });
      setAmount("");
      useToastStore.getState().push({ kind: "success", text: t("payoutRequested") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  const balance = data?.balance_uzs ?? 0;
  const min = data?.min_payout_uzs ?? 0;
  const valid = Number(amount) >= min && Number(amount) <= balance;

  return (
    <div data-testid="sales-payouts">
      <h1 className="mb-4 text-xl font-semibold">{t("payouts")}</h1>

      <div className="mb-5 rounded-2xl border border-border bg-surface p-5">
        <p className="text-xs font-medium uppercase text-fg-faint">{t("balance")}</p>
        <p className="tnum mt-1 text-2xl font-bold text-accent">{formatUzs(balance)} UZS</p>
        <p className="tnum mt-1 text-xs text-fg-muted">{t("minPayout", { n: formatUzs(min) })}</p>
        <div className="mt-4 flex gap-2">
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={t("amountPlaceholder")}
            className="tnum w-48 rounded-md border border-border bg-surface px-3 py-2 text-sm"
          />
          <button
            type="button"
            disabled={!valid || request.isPending}
            onClick={() => request.mutate()}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
          >
            {t("requestPayout")}
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-right">{t("amount")}</th>
              <th className="px-3 py-2 text-left">{t("status")}</th>
              <th className="px-3 py-2 text-left">{t("requestedAt")}</th>
            </tr>
          </thead>
          <tbody>
            {(data?.payouts ?? []).map((p) => (
              <tr key={p.id} className="border-t border-border">
                <td className="tnum px-3 py-2.5 text-right font-medium">{formatUzs(p.amount_uzs)}</td>
                <td className="px-3 py-2.5">
                  <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_TONE[p.status] ?? "bg-surface-3")}>
                    {t(`payout_${p.status}` as "payout_pending")}
                  </span>
                </td>
                <td className="tnum px-3 py-2.5 text-xs text-fg-muted">{p.requested_at.slice(0, 10)}</td>
              </tr>
            ))}
            {(data?.payouts ?? []).length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-10 text-center text-sm text-fg-faint">
                  {t("noPayouts")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
