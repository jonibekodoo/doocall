"use client";

/** Company activity infographic — aggregate, non-PII stats shared by the
 * admin console and the partner portal. The `top_operators` block only
 * renders when the API includes it (admin), never for integrators. */

import {
  ArrowDownLeft,
  ArrowUpRight,
  PhoneCall,
  PhoneMissed,
  Timer,
  Users,
} from "lucide-react";
import { useTranslations } from "next-intl";
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
import { formatDuration } from "@/lib/format";

export interface CompanyStatsData {
  total_calls: number;
  answered: number;
  missed: number;
  answer_rate: number;
  inbound: number;
  outbound: number;
  total_duration_sec: number;
  avg_duration_sec: number;
  calls_30d: number;
  operator_count: number;
  first_call_at: string | null;
  daily_series: Array<{
    date: string;
    total: number;
    answered: number;
    missed: number;
  }>;
  top_operators?: Array<{
    id: number;
    name: string;
    calls: number;
    answered: number;
  }>;
}

function Tile({
  icon,
  label,
  value,
  sub,
  tone = "accent",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  tone?: "accent" | "warning" | "danger";
}) {
  const toneCls =
    tone === "danger"
      ? "text-danger"
      : tone === "warning"
        ? "text-warning"
        : "text-accent";
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center gap-2 text-xs font-medium uppercase text-fg-faint">
        <span className={toneCls}>{icon}</span>
        {label}
      </div>
      <p className={`tnum mt-1.5 text-2xl font-bold ${toneCls}`}>{value}</p>
      {sub && <p className="tnum mt-0.5 text-xs text-fg-muted">{sub}</p>}
    </div>
  );
}

export function CompanyStats({ stats }: { stats: CompanyStatsData }) {
  const t = useTranslations("companyStats");

  if (stats.total_calls === 0) {
    return (
      <section className="mt-6 rounded-xl border border-dashed border-border bg-surface p-8 text-center">
        <PhoneCall className="mx-auto mb-2 size-6 text-fg-faint" />
        <p className="text-sm text-fg-muted">{t("empty")}</p>
      </section>
    );
  }

  const series = stats.daily_series.map((d) => {
    const [, m, day] = d.date.split("-");
    return { d: `${Number(m)}/${Number(day)}`, answered: d.answered, missed: d.missed };
  });

  const donut = [
    { name: t("answered"), value: stats.answered, color: CHART_COLORS.answered },
    { name: t("missed"), value: stats.missed, color: CHART_COLORS.missed },
  ].filter((s) => s.value > 0);

  const maxOp = Math.max(1, ...(stats.top_operators ?? []).map((o) => o.calls));

  return (
    <div className="mt-6 space-y-4" data-testid="company-stats">
      <h2 className="text-sm font-semibold text-fg-muted">{t("title")}</h2>

      {/* KPI tiles */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          icon={<PhoneCall className="size-4" />}
          label={t("totalCalls")}
          value={stats.total_calls.toLocaleString()}
          sub={t("last30", { n: stats.calls_30d.toLocaleString() })}
        />
        <Tile
          icon={<PhoneMissed className="size-4" />}
          label={t("answerRate")}
          value={`${stats.answer_rate}%`}
          sub={t("answeredMissed", {
            a: stats.answered.toLocaleString(),
            m: stats.missed.toLocaleString(),
          })}
          tone={stats.answer_rate < 50 ? "danger" : "accent"}
        />
        <Tile
          icon={<Timer className="size-4" />}
          label={t("talkTime")}
          value={formatDuration(stats.total_duration_sec)}
          sub={t("avgCall", { d: formatDuration(stats.avg_duration_sec) })}
        />
        <Tile
          icon={<Users className="size-4" />}
          label={t("operators")}
          value={stats.operator_count.toLocaleString()}
          sub={
            stats.first_call_at
              ? t("since", { date: stats.first_call_at.slice(0, 10) })
              : undefined
          }
        />
      </div>

      {/* Direction split */}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex items-center gap-3 rounded-xl border border-border bg-surface p-4 shadow-sm">
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
            <ArrowDownLeft className="size-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase text-fg-faint">
              {t("inbound")}
            </p>
            <p className="tnum text-lg font-bold">
              {stats.inbound.toLocaleString()}
            </p>
          </div>
          <div className="tnum text-sm font-semibold text-fg-muted">
            {stats.total_calls
              ? Math.round((stats.inbound / stats.total_calls) * 100)
              : 0}
            %
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-xl border border-border bg-surface p-4 shadow-sm">
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
            <ArrowUpRight className="size-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase text-fg-faint">
              {t("outbound")}
            </p>
            <p className="tnum text-lg font-bold">
              {stats.outbound.toLocaleString()}
            </p>
          </div>
          <div className="tnum text-sm font-semibold text-fg-muted">
            {stats.total_calls
              ? Math.round((stats.outbound / stats.total_calls) * 100)
              : 0}
            %
          </div>
        </div>
      </div>

      {/* Charts: answered/missed donut + 30-day volume */}
      <div className="grid gap-4 lg:grid-cols-3">
        <ReportCard title={t("outcome")}>
          <ChartBox height={220}>
            <PieChart>
              <Tooltip
                {...chartTooltipStyle}
                formatter={(v: number) => [v.toLocaleString(), ""]}
              />
              <Pie
                data={donut}
                dataKey="value"
                nameKey="name"
                innerRadius="60%"
                outerRadius="88%"
                paddingAngle={2}
                strokeWidth={0}
              >
                {donut.map((s) => (
                  <Cell key={s.name} fill={s.color} />
                ))}
              </Pie>
            </PieChart>
          </ChartBox>
          <div className="mt-2 flex justify-center gap-4 text-xs">
            {donut.map((s) => (
              <span key={s.name} className="flex items-center gap-1.5">
                <span
                  className="size-2.5 rounded-full"
                  style={{ background: s.color }}
                />
                {s.name}: <b className="tnum">{s.value.toLocaleString()}</b>
              </span>
            ))}
          </div>
        </ReportCard>

        <ReportCard title={t("volume30")} className="lg:col-span-2">
          <ChartBox height={220}>
            <AreaChart data={series}>
              <defs>
                <linearGradient id="csAnswered" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_COLORS.answered} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={CHART_COLORS.answered} stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="csMissed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_COLORS.missed} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={CHART_COLORS.missed} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis dataKey="d" {...chartAxisProps} interval={6} />
              <YAxis {...chartAxisProps} width={32} allowDecimals={false} />
              <Tooltip {...chartTooltipStyle} />
              <Area
                type="monotone"
                stackId="1"
                dataKey="answered"
                name={t("answered")}
                stroke={CHART_COLORS.answered}
                strokeWidth={2}
                fill="url(#csAnswered)"
                dot={false}
              />
              <Area
                type="monotone"
                stackId="1"
                dataKey="missed"
                name={t("missed")}
                stroke={CHART_COLORS.missed}
                strokeWidth={2}
                fill="url(#csMissed)"
                dot={false}
              />
            </AreaChart>
          </ChartBox>
        </ReportCard>
      </div>

      {/* Top operators — admin only (present when API includes it) */}
      {stats.top_operators && stats.top_operators.length > 0 && (
        <ReportCard title={t("topOperators")}>
          <ul className="space-y-2.5">
            {stats.top_operators.map((op) => (
              <li key={op.id} className="flex items-center gap-3">
                <span className="w-32 shrink-0 truncate text-sm font-medium">
                  {op.name}
                </span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${(op.calls / maxOp) * 100}%` }}
                  />
                </div>
                <span className="tnum w-16 shrink-0 text-right text-sm">
                  {op.calls.toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </ReportCard>
      )}
    </div>
  );
}
