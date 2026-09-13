"use client";

/** A.3 Admin dashboard — KPI tiles + infographics (status donut, 30-day
 * payments & calls area charts). */

import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  CreditCard,
  Handshake,
  ListChecks,
  PhoneCall,
  Wallet,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
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
import { fetchKpis } from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

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

/** Build a labelled series from the raw 30-value array (x = day offset). */
function toSeries(values: number[]): Array<{ d: string; v: number }> {
  const n = values.length;
  return values.map((v, i) => {
    const daysAgo = n - 1 - i;
    const date = new Date();
    date.setDate(date.getDate() - daysAgo);
    return { d: `${date.getMonth() + 1}/${date.getDate()}`, v };
  });
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
          label={t("dashboard.callsToday")}
          value={data.calls_today}
        />
        <KpiTile
          icon={Handshake}
          label={t("dashboard.integrators")}
          value={data.integrators}
        />
      </div>

      {/* Attention row: pending payments / payouts */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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

        <ReportCard title={t("dashboard.paymentsChart")}>
          <ChartBox height={240}>
            <AreaChart data={toSeries(data.payments_series)}>
              <defs>
                <linearGradient id="payFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_COLORS.answered} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={CHART_COLORS.answered} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis dataKey="d" {...chartAxisProps} interval={6} />
              <YAxis
                {...chartAxisProps}
                width={44}
                tickFormatter={(v: number) =>
                  v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)
                }
              />
              <Tooltip
                {...chartTooltipStyle}
                formatter={(v: number) => [`${formatUzs(v)} UZS`, ""]}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke={CHART_COLORS.answered}
                strokeWidth={2.5}
                fill="url(#payFill)"
                dot={false}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ChartBox>
        </ReportCard>
      </div>

      {/* Calls area (full width) */}
      <ReportCard title={t("dashboard.callsChart")}>
        <ChartBox height={220}>
          <AreaChart data={toSeries(data.calls_series)}>
            <defs>
              <linearGradient id="callFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLORS.inbound} stopOpacity={0.35} />
                <stop offset="100%" stopColor={CHART_COLORS.inbound} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="d" {...chartAxisProps} interval={6} />
            <YAxis {...chartAxisProps} width={36} />
            <Tooltip {...chartTooltipStyle} />
            <Area
              type="monotone"
              dataKey="v"
              stroke={CHART_COLORS.inbound}
              strokeWidth={2.5}
              fill="url(#callFill)"
              dot={false}
              activeDot={{ r: 4 }}
            />
          </AreaChart>
        </ChartBox>
      </ReportCard>
    </div>
  );
}
