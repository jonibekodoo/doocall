"use client";

/** A.3 Admin dashboard — KPI tiles + infographics (status donut, 30-day
 * payments & calls area charts). */

import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  Building2,
  Clock,
  Coins,
  CreditCard,
  Handshake,
  ListChecks,
  Phone,
  PhoneCall,
  Wallet,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import {
  Area,
  AreaChart,
  Cell,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  CHART_COLORS,
  ChartBox,
  ReportCard,
  chartAxisProps,
  chartTooltipStyle,
} from "@/components/charts/theme";
import {
  type DashboardMetric,
  type DashboardPeriod,
  fetchDashboardSeries,
  fetchKpis,
  fetchSalesManagerStats,
  fetchAdminCallsToday,
} from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const PERIODS: DashboardPeriod[] = ["daily", "weekly", "monthly", "yearly"];

function KpiTile({
  icon: Icon,
  label,
  value,
  hint,
  tone = "default",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: "default" | "accent" | "warning";
}) {
  const toneRing = {
    default: "bg-accent-soft text-accent",
    accent: "bg-accent-soft text-accent",
    warning: "bg-warning/15 text-warning",
  }[tone];
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center gap-3">
        <span className={cn("grid size-10 shrink-0 place-items-center rounded-lg", toneRing)}>
          <Icon className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-fg-faint">
            {label}
          </p>
          <p className="tnum truncate text-2xl font-bold leading-tight">
            {value}
          </p>
        </div>
      </div>
      {hint && <p className="mt-2 text-xs text-fg-muted">{hint}</p>}
    </div>
  );
}

/** Time-series area chart with a daily/weekly/monthly/yearly selector. */
function PeriodChart({
  metric,
  title,
  color,
  fillId,
  money = false,
}: {
  metric: DashboardMetric;
  title: string;
  color: string;
  fillId: string;
  money?: boolean;
}) {
  const t = useTranslations("admin");
  const [period, setPeriod] = useState<DashboardPeriod>("daily");
  const { data, isPending } = useQuery({
    queryKey: ["a-series", metric, period],
    queryFn: () => fetchDashboardSeries(metric, period),
  });
  const series = data?.series ?? [];
  const interval = period === "daily" ? 6 : period === "weekly" ? 1 : 0;

  return (
    <ReportCard
      title={title}
      action={
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value as DashboardPeriod)}
          aria-label={t("dashboard.period")}
          className="rounded-md border border-border bg-surface px-2 py-1 text-xs"
        >
          {PERIODS.map((p) => (
            <option key={p} value={p}>
              {t(`dashboard.period${p[0].toUpperCase()}${p.slice(1)}` as "dashboard.periodDaily")}
            </option>
          ))}
        </select>
      }
    >
      {isPending ? (
        <div className="h-[240px] animate-pulse rounded-lg bg-surface-2" />
      ) : (
        <ChartBox height={240}>
          <AreaChart data={series}>
            <defs>
              <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" {...chartAxisProps} interval={interval} />
            <YAxis
              {...chartAxisProps}
              width={money ? 44 : 36}
              allowDecimals={false}
              tickFormatter={(v: number) =>
                v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)
              }
            />
            <Tooltip
              {...chartTooltipStyle}
              formatter={(v: number) => [
                money ? `${formatUzs(v)} UZS` : v.toLocaleString(),
                "",
              ]}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2.5}
              fill={`url(#${fillId})`}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </AreaChart>
        </ChartBox>
      )}
    </ReportCard>
  );
}

const MEDALS = ["🥇", "🥈", "🥉"];

function SalesManagersSummary() {
  const t = useTranslations("admin");
  const { data } = useQuery({ queryKey: ["a-sales-stats"], queryFn: fetchSalesManagerStats });
  if (!data || data.managers.length === 0) return null;
  const top = [...data.managers]
    .sort((a, b) => b.commission_uzs - a.commission_uzs)
    .slice(0, 5);
  const max = Math.max(1, ...top.map((r) => r.commission_uzs));
  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-fg-muted">
        {t("dashboard.salesManagersTitle")}
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile
          icon={Briefcase}
          label={t("salesM.total")}
          value={data.totals.managers}
        />
        <KpiTile
          icon={Handshake}
          label={t("salesM.integrators")}
          value={data.totals.integrators}
        />
        <KpiTile
          icon={CreditCard}
          label={t("salesM.revenue")}
          value={`${formatUzs(data.totals.revenue_uzs)} UZS`}
        />
        <KpiTile
          icon={Coins}
          label={t("salesM.commissionPaid")}
          value={`${formatUzs(data.totals.commission_uzs)} UZS`}
        />
      </div>
      <ReportCard title={t("salesM.topByCommission")}>
        <ul className="space-y-3">
          {top.map((r, i) => (
            <li key={r.id} className="flex items-center gap-3">
              <span className="w-5 text-center text-sm">
                {i < 3 ? MEDALS[i] : <span className="text-fg-faint">{i + 1}</span>}
              </span>
              <Link
                href={`/admin/sales-managers/${r.id}`}
                className="w-32 shrink-0 truncate text-sm font-medium text-accent hover:underline"
              >
                {r.name}
              </Link>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${(r.commission_uzs / max) * 100}%` }}
                />
              </div>
              <span className="tnum w-24 shrink-0 text-right text-sm font-semibold">
                {formatUzs(r.commission_uzs)}
              </span>
            </li>
          ))}
        </ul>
      </ReportCard>
    </div>
  );
}

/** Leaderboard: ten busiest companies over the whole period — all-time total
 * and today's count, with a share bar against the leader. */
function CallsTodayReport() {
  const t = useTranslations("admin");
  const { data } = useQuery({ queryKey: ["a-calls-today"], queryFn: fetchAdminCallsToday, refetchInterval: 60_000 });
  const rows = data?.companies ?? [];
  const max = Math.max(1, ...rows.map((c) => c.total));
  return (
    <div className="rounded-xl border border-border bg-surface" data-testid="calls-today-report">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">{t("dashboard.callsTodayTitle")}</h2>
          {data && (
            <p className="tnum text-xs text-fg-faint">
              {t("dashboard.callsTodayCompanies", { n: data.companies_count })} · {data.date}
            </p>
          )}
        </div>
        {data && (
          <div className="ml-auto flex items-center gap-5 text-xs">
            <span>
              <span className="block uppercase text-fg-faint">{t("dashboard.ctTotal")}</span>
              <b className="tnum text-lg" data-testid="calls-total-all">{data.total.toLocaleString()}</b>
            </span>
            <span>
              <span className="block uppercase text-fg-faint">{t("dashboard.ctToday")}</span>
              <b className="tnum text-lg text-accent" data-testid="calls-today-total">{data.today.toLocaleString()}</b>
            </span>
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="w-8 px-3 py-2 text-left">№</th>
              <th className="px-3 py-2 text-left">{t("dashboard.ctCompany")}</th>
              <th className="px-3 py-2 text-right">{t("dashboard.ctTotal")}</th>
              <th className="px-3 py-2 text-right">{t("dashboard.ctToday")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c, index) => (
              <tr key={c.id} className="border-t border-border hover:bg-surface-2/60">
                <td className="tnum px-3 py-2.5 text-fg-faint">{index + 1}</td>
                <td className="px-3 py-2.5">
                  <Link href={`/admin/companies/${c.id}`} className="font-medium text-accent hover:underline">
                    {c.name}
                  </Link>
                  <div className="mt-1 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-surface-2">
                    <div className="h-full rounded-full bg-accent/70" style={{ width: `${(c.total / max) * 100}%` }} />
                  </div>
                </td>
                <td className="tnum px-3 py-2.5 text-right font-semibold">{c.total.toLocaleString()}</td>
                <td className={cn("tnum px-3 py-2.5 text-right", c.today > 0 ? "font-semibold text-accent" : "text-fg-faint")}>
                  {c.today.toLocaleString()}
                </td>
              </tr>
            ))}
            {data && rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-8 text-center text-xs text-fg-faint">
                  {t("dashboard.callsTodayEmpty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const t = useTranslations("admin");
  const tc = useTranslations("admin.companies");
  const { data, isPending } = useQuery({
    queryKey: ["a-kpis"],
    queryFn: fetchKpis,
  });

  if (isPending || !data) {
    return (
      <div data-testid="admin-dashboard">
        <h1 className="mb-4 text-xl font-semibold">{t("dashboard.title")}</h1>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-24 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      </div>
    );
  }

  const c = data.companies;
  const statusData = [
    { name: tc("statusActive"), value: c.active, color: CHART_COLORS.answered },
    { name: tc("statusTrial"), value: c.trial, color: CHART_COLORS.inbound },
    { name: tc("statusSuspended"), value: c.suspended, color: CHART_COLORS.missed },
  ].filter((s) => s.value > 0);

  return (
    <div data-testid="admin-dashboard" className="space-y-5">
      <h1 className="text-xl font-semibold">{t("dashboard.title")}</h1>

      {/* KPI tiles */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile
          icon={Building2}
          label={t("dashboard.companies")}
          value={c.total}
          hint={t("dashboard.companiesHint", {
            active: c.active,
            trial: c.trial,
            suspended: c.suspended,
          })}
        />
        <KpiTile
          icon={CreditCard}
          label={t("dashboard.payments30")}
          value={`${formatUzs(data.payments_30d_uzs)} UZS`}
        />
        <KpiTile
          icon={PhoneCall}
          label={t("dashboard.totalCalls")}
          value={data.total_calls.toLocaleString()}
          hint={t("dashboard.totalCallTimeHint")}
        />
        <KpiTile
          icon={Clock}
          label={t("dashboard.totalCallTime")}
          value={t("dashboard.hours", {
            n: Math.round(data.total_call_seconds / 3600).toLocaleString(),
          })}
          hint={t("dashboard.totalCallTimeHint")}
        />
      </div>

      {/* Secondary row: calls today / integrators / pending payments / payouts */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile
          icon={Phone}
          label={t("dashboard.callsToday")}
          value={data.calls_today}
        />
        <KpiTile
          icon={Handshake}
          label={t("dashboard.integrators")}
          value={data.integrators}
        />
        <Link href="/admin/payments" className="block">
          <KpiTile
            icon={Wallet}
            label={t("dashboard.pendingPayments")}
            value={data.pending_payments ?? 0}
            tone={data.pending_payments ? "warning" : "default"}
          />
        </Link>
        <Link href="/admin/payouts" className="block">
          <KpiTile
            icon={ListChecks}
            label={t("dashboard.payoutsQueue")}
            value={data.pending_payouts ?? 0}
            tone={data.pending_payouts ? "warning" : "default"}
          />
        </Link>
      </div>

      {/* Companies status donut + payments area */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ReportCard title={t("dashboard.companiesStatus")}>
          <div className="relative">
            <ChartBox height={240}>
              <PieChart>
                <Tooltip {...chartTooltipStyle} />
                <Pie
                  data={statusData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="62%"
                  outerRadius="88%"
                  paddingAngle={2}
                  strokeWidth={0}
                >
                  {statusData.map((s) => (
                    <Cell key={s.name} fill={s.color} />
                  ))}
                </Pie>
              </PieChart>
            </ChartBox>
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
              <div>
                <p className="tnum text-3xl font-bold">{c.total}</p>
                <p className="text-xs uppercase text-fg-faint">
                  {t("dashboard.companies")}
                </p>
              </div>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs">
            {statusData.map((s) => (
              <span key={s.name} className="flex items-center gap-1.5">
                <span
                  className="size-2.5 rounded-full"
                  style={{ background: s.color }}
                />
                {s.name}: <b className="tnum">{s.value}</b>
              </span>
            ))}
          </div>
        </ReportCard>

        <PeriodChart
          metric="payments"
          title={t("dashboard.paymentsChart")}
          color={CHART_COLORS.answered}
          fillId="payFill"
          money
        />
      </div>

      {/* Calls area (full width) */}
      <PeriodChart
        metric="calls"
        title={t("dashboard.callsChart")}
        color={CHART_COLORS.inbound}
        fillId="callFill"
      />

      {/* Sales managers */}
      <SalesManagersSummary />

      {/* Today's calls by company / operator */}
      <CallsTodayReport />
    </div>
  );
}
