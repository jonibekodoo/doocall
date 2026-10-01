"use client";

/** A.4 Overview — KPI cards, 12-month bar chart, latest accruals feed. */

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";
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

          {/* Companies by status (trial split into running / expired) */}
          <div className="mt-4 rounded-lg border border-border bg-surface p-4" data-testid="companies-by-status">
            <p className="mb-3 text-xs font-semibold uppercase text-fg-faint">
              {t("companiesByStatus")}
            </p>
            <div className="grid gap-2 sm:grid-cols-4">
              {(
                [
                  ["active", "bg-accent-soft text-accent"],
                  ["trial", "bg-warning/15 text-warning"],
                  ["trial_expired", "bg-danger/15 text-danger"],
                  ["suspended", "bg-danger/10 text-danger"],
                ] as const
              ).map(([key, tone]) => (
                <div key={key} className={`rounded-md px-3 py-2 ${tone}`}>
                  <p className="text-[11px] font-semibold uppercase opacity-80">
                    {t(key === "trial_expired" ? "st_expired" : `st_${key}`)}
                  </p>
                  <p className="tnum text-2xl font-bold">
                    {data.companies_by_status?.[key] ?? 0}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Companies going offline within 3 days (trial end / balance out) */}
          <section
            className={`mt-4 rounded-lg border bg-surface ${
              data.expiring.length ? "border-warning/50" : "border-border"
            }`}
            data-testid="expiring-companies"
          >
            <p className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-sm font-semibold">
              <AlertTriangle
                className={`size-4 ${data.expiring.length ? "text-warning" : "text-fg-faint"}`}
              />
              {t("expiringTitle")}
              {data.expiring.length > 0 && (
                <span className="tnum ml-auto rounded-full bg-warning/15 px-2 py-0.5 text-xs font-semibold text-warning">
                  {data.expiring.length}
                </span>
              )}
            </p>
            <ul className="divide-y divide-border">
              {data.expiring.map((c) => (
                <li
                  key={`${c.reason}-${c.id}`}
                  className="flex items-center gap-3 px-4 py-2.5 text-sm"
                >
                  <Link
                    href={`/partner/companies/${c.id}`}
                    className="min-w-0 flex-1 truncate font-medium text-accent hover:underline"
                  >
                    {c.name}
                  </Link>
                  <span className="hidden text-xs text-fg-muted sm:inline">
                    {t(c.reason === "trial" ? "expiringTrial" : "expiringBalance")}
                  </span>
                  <span className="tnum text-xs text-fg-faint">{c.ends_on}</span>
                  <span
                    className={`tnum rounded-full px-2 py-0.5 text-xs font-semibold ${
                      c.days_left <= 1
                        ? "bg-danger/10 text-danger"
                        : "bg-warning/15 text-warning"
                    }`}
                  >
                    {c.days_left === 0
                      ? t("expiringToday")
                      : t("expiringDays", { n: c.days_left })}
                  </span>
                </li>
              ))}
              {data.expiring.length === 0 && (
                <li className="px-4 py-5 text-center text-xs text-fg-faint">
                  {t("expiringNone")}
                </li>
              )}
            </ul>
          </section>

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
