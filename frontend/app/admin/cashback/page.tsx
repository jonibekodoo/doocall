"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import { fetchCashbackSettings, saveCashbackSettings } from "@/lib/api/admin";
import { cashbackExample } from "@/lib/admin-shared";

export default function AdminCashbackPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["a-cashback"],
    queryFn: fetchCashbackSettings,
  });
  const [percent, setPercent] = useState<string | null>(null);
  const [months, setMonths] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: saveCashbackSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-cashback"] });
      setPercent(null);
      setMonths(null);
      useToastStore
        .getState()
        .push({ kind: "success", text: t("cashback.updated") });
    },
  });

  const shownPercent = Number(percent ?? data?.default_cashback_percent ?? 0);

  return (
    <div data-testid="admin-cashback" className="max-w-lg">
      <h1 className="mb-4 text-xl font-semibold">{t("cashback.title")}</h1>
      {data && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <label className="mb-3 block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("cashback.defaultPercent")}
            </span>
            <input
              type="number"
              step="0.5"
              data-testid="cashback-percent"
              value={percent ?? data.default_cashback_percent}
              onChange={(e) => setPercent(e.target.value)}
              className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
          <label className="mb-3 block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("cashback.monthsLimit")}
            </span>
            <input
              type="number"
              data-testid="cashback-months"
              value={months ?? data.cashback_months_limit}
              onChange={(e) => setMonths(e.target.value)}
              className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
          <p
            data-testid="cashback-example"
            className="tnum rounded-md bg-surface-2 px-3 py-2 text-sm"
          >
            {t("cashback.example", { value: cashbackExample(shownPercent) })}
          </p>
          <button
            type="button"
            data-testid="cashback-save"
            disabled={(percent === null && months === null) || save.isPending}
            onClick={() =>
              save.mutate({
                ...(percent !== null
                  ? { default_cashback_percent: percent }
                  : {}),
                ...(months !== null
                  ? { cashback_months_limit: Number(months) }
                  : {}),
              })
            }
            className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
          >
            {t("common.save")}
          </button>
        </div>
      )}
    </div>
  );
}
