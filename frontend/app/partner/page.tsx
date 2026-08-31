"use client";

/** A.4 Overview — KPI cards, 12-month bar chart, latest accruals feed. */

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Bar, BarChart, Tooltip, XAxis, YAxis } from "recharts";

import {
  CHART_COLORS,
  ChartContainer,
  chartAxisProps,
  chartTooltipStyle,
} from "@/components/charts/theme";
import { StatCard } from "@/components/ui/StatCard";
import { fetchPartnerAccruals, fetchPartnerDashboard } from "@/lib/api/partner";
import { formatUzs } from "@/lib/format";

export default function PartnerOverview() {
  const t = useTranslations("partner");
  const { data, isPending } = useQuery({
    queryKey: ["p-dashboard"],
    queryFn: fetchPartnerDashboard,
  });
  const { data: latest } = useQuery({
    queryKey: ["p-latest-accruals"],
    queryFn: () => fetchPartnerAccruals(""),
  });

  return (
    <div data-testid="partner-overview">
      <h1 className="mb-4 text-xl font-semibold">{t("overview")}</h1>
      {isPending ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-24 animate-pulse rounded-lg bg-surface-2"
            />
          ))}
        </div>
      ) : data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label={t("companiesCard")}
              value={data.companies_total}
              hint={`active ${data.companies_active}`}
            />
            <StatCard
              label={t("monthCashback")}
              value={`${formatUzs(data.month_cashback_uzs)} UZS`}
            />
            <StatCard
              label={t("lifetime")}
              value={`${formatUzs(data.accrued_total_uzs)} UZS`}
            />
            <StatCard
              label={t("balance")}
              value={`${formatUzs(data.balance_uzs)} UZS`}
              tone="accent"
            />
            <StatCard
              label={t("yourPercent")}
              value={`${data.effective_percent}%`}
              tone="accent"
            />
            <StatCard
              label={t("payouts")}
              value={`${formatUzs(data.paid_out_uzs)} UZS`}
            />
          </div>

          <div className="mt-6">
            <p className="mb-2 text-xs font-semibold uppercase text-fg-faint">
              {t("chartTitle")}
            </p>
            <ChartContainer height={220}>
              <BarChart data={data.monthly_series}>
                <XAxis
                  dataKey="month"
                  {...chartAxisProps}
                  tickFormatter={(v: string) => v.slice(5)}
                />
                <YAxis
                  {...chartAxisProps}
                  width={56}
                  tickFormatter={(v: number) => formatUzs(v)}
                />
                <Tooltip {...chartTooltipStyle} />
                <Bar
                  dataKey="amount_uzs"
                  fill={CHART_COLORS.answered}
                  name="UZS"
                />
              </BarChart>
            </ChartContainer>
          </div>

          <section className="mt-6 rounded-lg border border-border bg-surface">
            <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
              {t("latestAccruals")}
            </p>
            <ul className="divide-y divide-border">
              {(latest?.accruals ?? []).slice(0, 6).map((a) => (
                <li
                  key={a.id}
                  className="flex items-center gap-2 px-4 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate">{a.company}</span>
                  <span className="tnum text-accent">
                    +{formatUzs(a.amount_uzs)}
                  </span>
                  <span className="tnum text-xs text-fg-faint">
                    {a.percent}%
                  </span>
                  <span className="tnum text-xs text-fg-faint">
                    {a.created_at.slice(0, 10)}
                  </span>
                </li>
              ))}
              {(latest?.accruals ?? []).length === 0 && (
                <li className="px-4 py-8 text-center text-sm text-fg-faint">
                  {t("noAccruals")}
                </li>
              )}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  );
}
