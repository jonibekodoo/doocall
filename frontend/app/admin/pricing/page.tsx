"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import { fetchPricing, savePricing } from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";

export default function AdminPricingPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["a-pricing"], queryFn: fetchPricing });
  const [price, setPrice] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: savePricing,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-pricing"] });
      setPrice(null);
      useToastStore
        .getState()
        .push({ kind: "success", text: t("pricing.updated") });
    },
  });

  return (
    <div data-testid="admin-pricing" className="max-w-lg">
      <h1 className="mb-1 text-xl font-semibold">{t("pricing.title")}</h1>
      <p className="mb-4 rounded-md bg-warning/10 px-3 py-2 text-xs font-medium text-warning">
        {t("pricing.notice")}
      </p>
      {data && (
        <>
          <div className="rounded-lg border border-border bg-surface p-4">
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("pricing.priceLabel")}
              </span>
              <input
                type="number"
                data-testid="price-input"
                value={price ?? String(data.price_per_operator_uzs)}
                onChange={(e) => setPrice(e.target.value)}
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
              />
            </label>
            <button
              type="button"
              data-testid="price-save"
              disabled={price === null || save.isPending}
              onClick={() =>
                save.mutate({ price_per_operator_uzs: Number(price) })
              }
              className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
            >
              {t("common.save")}
            </button>
          </div>
          <div className="mt-5 rounded-lg border border-border bg-surface">
            <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
              {t("pricing.history")}
            </p>
            <ul className="divide-y divide-border">
              {data.history.map((h, i) => (
                <li
                  key={i}
                  className="flex items-center gap-2 px-4 py-2 text-sm"
                >
                  <span className="tnum flex-1">
                    {formatUzs(h.price_per_operator_uzs)} UZS
                  </span>
                  <span className="text-xs text-fg-muted">
                    {h.changed_by ?? "—"}
                  </span>
                  <span className="tnum text-xs text-fg-faint">
                    {h.changed_at.slice(0, 16).replace("T", " ")}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
