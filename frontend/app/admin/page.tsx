"use client";

/** A.3 Admin dashboard — KPI cards + 30-day sparklines. */

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Sparkline } from "@/components/charts/Sparkline";
import { StatCard } from "@/components/ui/StatCard";
import { kpiCards } from "@/lib/admin-shared";
import { fetchKpis } from "@/lib/api/admin";

export default function AdminDashboard() {
  const t = useTranslations("admin");
  const { data, isPending } = useQuery({
    queryKey: ["a-kpis"],
    queryFn: fetchKpis,
  });

  return (
    <div data-testid="admin-dashboard">
      <h1 className="mb-4 text-xl font-semibold">{t("dashboard.title")}</h1>
      {isPending ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={index}
              className="h-24 animate-pulse rounded-lg bg-surface-2"
            />
          ))}
        </div>
      ) : data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {kpiCards(data, t).map((card) => (
              <StatCard
                key={card.key}
                label={card.label}
                value={card.value}
                hint={card.hint ?? undefined}
              />
            ))}
          </div>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-border bg-surface p-4">
              <p className="mb-2 text-xs font-semibold uppercase text-fg-faint">
                {t("dashboard.paymentsChart")}
              </p>
              <Sparkline data={data.payments_series} />
            </div>
            <div className="rounded-lg border border-border bg-surface p-4">
              <p className="mb-2 text-xs font-semibold uppercase text-fg-faint">
                {t("dashboard.callsChart")}
              </p>
              <Sparkline data={data.calls_series} />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
