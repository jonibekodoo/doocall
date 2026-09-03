"use client";

/** §6.4 Отчеты — tab bar with submenus; every report wired to the API. */

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  LabelList,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { DirectionIcon } from "@/components/calls-shared";
import { CallAudioButton } from "@/components/CallAudioButton";
import {
  CHART_COLORS,
  ChartBox,
  ChartContainer,
  ReportCard,
  chartAxisProps,
  chartTooltipStyle,
} from "@/components/charts/theme";
import { StatCard } from "@/components/ui/StatCard";
import {
  fetchGeneralReport,
  fetchLastContact,
  fetchPerClient,
  fetchPerEmployee,
  fetchPeriodCounts,
  fetchUnanswered,
  fetchWeekdayMatrix,
} from "@/lib/api/endpoints";
import { formatDuration, formatPhone, humanizeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab =
  | "general"
  | "weekday"
  | "period"
  | "emp-distribution"
  | "emp-am"
  | "emp-duration"
  | "client-distribution"
  | "unanswered"
  | "last-contact";

const TAB_GROUPS: Array<{
  group: string;
  tabs: Array<{ id: Tab; label: string }>;
}> = [
  { group: "general", tabs: [{ id: "general", label: "general" }] },
  {
    group: "periods",
    tabs: [
      { id: "weekday", label: "weekdayMatrix" },
      { id: "period", label: "periodChart" },
    ],
  },
  {
    group: "employees",
    tabs: [
      { id: "emp-distribution", label: "distribution" },
      { id: "emp-am", label: "answeredMissed" },
      { id: "emp-duration", label: "durationMin" },
    ],
  },
  {
    group: "clients",
    tabs: [
      { id: "client-distribution", label: "distribution" },
      { id: "unanswered", label: "unanswered" },
      { id: "last-contact", label: "lastContact" },
    ],
  },
];

const WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const DONUT_COLORS = [
  "var(--accent-600)",
  "var(--accent-400)",
  "var(--accent-800)",
  "var(--accent-300)",
  "var(--accent-700)",
  "var(--accent-200)",
];

function hhmmss(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return [h, m, s].map((part) => String(part).padStart(2, "0")).join(":");
}

// ── Individual report views ────────────────────────────────────────────────

function GeneralView() {
  const t = useTranslations("dashboard");
  const tCalls = useTranslations("calls");
  const { data, isPending } = useQuery({
    queryKey: ["r-general"],
    queryFn: () => fetchGeneralReport(),
  });
  const tReports = useTranslations("reports");
  if (isPending) return <Skeleton />;
  if (!data) return null;
  const { report } = data;
  const rate =
    report.all.total > 0
      ? Math.round((report.all.answered / report.all.total) * 100)
      : 0;
  const donut = [
    { name: tCalls("answered"), value: report.all.answered },
    { name: tCalls("missed"), value: report.all.missed },
  ];
  const directions = [
    {
      name: tCalls("inbound"),
      answered: report.inbound.answered,
      missed: report.inbound.missed,
    },
    {
      name: tCalls("outbound"),
      answered: report.outbound.answered,
      missed: report.outbound.missed,
    },
  ];
  return (
    <div data-testid="report-general" className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label={t("all")} value={report.all.total} />
        <StatCard
          label={tCalls("answered")}
          value={report.all.answered}
          tone="accent"
          hint={rate + "%"}
        />
        <StatCard
          label={tCalls("missed")}
          value={report.all.missed}
          tone="danger"
        />
        <StatCard
          label={tCalls("duration")}
          value={hhmmss(report.total_duration_sec)}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <ReportCard title={tReports("answeredMissed")}>
          <div className="relative">
            <ChartBox height={240}>
              <PieChart>
                <Tooltip {...chartTooltipStyle} />
                <Pie
                  data={donut}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="65%"
                  outerRadius="90%"
                  paddingAngle={2}
                  strokeWidth={0}
                >
                  <Cell fill={CHART_COLORS.answered} />
                  <Cell fill={CHART_COLORS.missed} />
                </Pie>
              </PieChart>
            </ChartBox>
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
              <div>
                <p className="tnum text-3xl font-bold">{report.all.total}</p>
                <p className="text-xs uppercase text-fg-faint">{t("all")}</p>
              </div>
            </div>
          </div>
        </ReportCard>
        <ReportCard title={tReports("byDirection")}>
          <ChartBox height={240}>
            <BarChart data={directions} barGap={6}>
              <XAxis dataKey="name" {...chartAxisProps} />
              <YAxis {...chartAxisProps} width={36} />
              <Tooltip {...chartTooltipStyle} />
              <Bar
                dataKey="answered"
                fill={CHART_COLORS.answered}
                name={tCalls("answered")}
                radius={[6, 6, 0, 0]}
              />
              <Bar
                dataKey="missed"
                fill={CHART_COLORS.missed}
                name={tCalls("missed")}
                radius={[6, 6, 0, 0]}
              />
            </BarChart>
          </ChartBox>
        </ReportCard>
      </div>
    </div>
  );
}

function WeekdayView() {
  const t = useTranslations("calls");
  const tReports = useTranslations("reports");
  const { data, isPending } = useQuery({
    queryKey: ["r-weekday"],
    queryFn: () => fetchWeekdayMatrix(),
  });
  if (isPending) return <Skeleton />;
  const labels = tReports("weekdaysShort").split(",");
  const chartRows = (data?.report ?? []).map((row) => ({
    name: labels[row.weekday - 1] ?? String(row.weekday),
    answered: row.answered,
    missed: row.missed,
  }));
  return (
    <div className="space-y-4">
    <ReportCard title={tReports("weekdayMatrix")}>
      <ChartBox height={240}>
        <BarChart data={chartRows} barGap={4}>
          <XAxis dataKey="name" {...chartAxisProps} interval={0} />
          <YAxis {...chartAxisProps} width={36} />
          <Tooltip {...chartTooltipStyle} />
          <Bar
            dataKey="answered"
            fill={CHART_COLORS.answered}
            name={t("answered")}
            radius={[6, 6, 0, 0]}
          />
          <Bar
            dataKey="missed"
            fill={CHART_COLORS.missed}
            name={t("missed")}
            radius={[6, 6, 0, 0]}
          />
        </BarChart>
      </ChartBox>
    </ReportCard>
    <table
      className="w-full overflow-hidden rounded-lg border border-border bg-surface text-sm"
      data-testid="report-weekday"
    >
      <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
        <tr>
          <th className="px-3 py-2 text-left">—</th>
          <th className="px-3 py-2 text-right">Все</th>
          <th className="px-3 py-2 text-right">{t("inbound")}</th>
          <th className="px-3 py-2 text-right">{t("outbound")}</th>
          <th className="px-3 py-2 text-right">{t("answered")}</th>
          <th className="px-3 py-2 text-right">{t("missed")}</th>
        </tr>
      </thead>
      <tbody>
        {(data?.report ?? []).map((row) => (
          <tr key={row.weekday} className="border-t border-border">
            <td className="px-3 py-2 font-medium">
              {labels[row.weekday - 1] ?? WEEKDAYS_RU[row.weekday - 1]}
            </td>
            <td className="tnum px-3 py-2 text-right">{row.total}</td>
            <td className="tnum px-3 py-2 text-right">{row.inbound}</td>
            <td className="tnum px-3 py-2 text-right">{row.outbound}</td>
            <td className="tnum px-3 py-2 text-right text-accent">
              {row.answered}
            </td>
            <td className="tnum px-3 py-2 text-right text-danger">
              {row.missed}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

function PeriodView() {
  const t = useTranslations("reports");
  const [group, setGroup] = useState<"day" | "week" | "month">("day");
  const [unique, setUnique] = useState(false);
  const { data, isPending } = useQuery({
    queryKey: ["r-period", group, unique],
    queryFn: () => fetchPeriodCounts(group, unique),
  });
  return (
    <div data-testid="report-period">
      <div className="mb-3 flex items-center gap-3">
        {(["day", "week", "month"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setGroup(option)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium",
              group === option
                ? "bg-accent text-accent-fg"
                : "border border-border text-fg-muted",
            )}
          >
            {option}
          </button>
        ))}
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={unique}
            onChange={(event) => setUnique(event.target.checked)}
            className="accent-[var(--accent)]"
            data-testid="unique-checkbox"
          />
          {t("unique")}
        </label>
      </div>
      {isPending ? (
        <Skeleton />
      ) : (
        <ChartContainer height={280}>
          <AreaChart data={(data?.report ?? []).slice(-31)}>
            <defs>
              <linearGradient id="periodFill" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0%"
                  stopColor={CHART_COLORS.answered}
                  stopOpacity={0.35}
                />
                <stop
                  offset="100%"
                  stopColor={CHART_COLORS.answered}
                  stopOpacity={0.02}
                />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="bucket"
              {...chartAxisProps}
              tickFormatter={(v: string) => v.slice(5)}
            />
            <YAxis {...chartAxisProps} width={36} />
            <Tooltip {...chartTooltipStyle} />
            <Area
              type="monotone"
              dataKey="total"
              stroke={CHART_COLORS.answered}
              strokeWidth={2.5}
              fill="url(#periodFill)"
              dot={{ r: 2.5, fill: CHART_COLORS.answered, strokeWidth: 0 }}
              activeDot={{ r: 4 }}
            />
          </AreaChart>
        </ChartContainer>
      )}
    </div>
  );
}

function EmployeeView({ mode }: { mode: "distribution" | "am" | "duration" }) {
  const t = useTranslations("reports");
  const tCalls = useTranslations("calls");
  const { data, isPending } = useQuery({
    queryKey: ["r-employee"],
    queryFn: () => fetchPerEmployee(),
  });
  if (isPending) return <Skeleton />;
  const rows = data?.report ?? [];
  if (mode === "distribution") {
    return (
      <div data-testid="report-emp-distribution">
        <ChartContainer height={300}>
          <PieChart>
            <Tooltip {...chartTooltipStyle} />
            <Pie
              data={rows.map((row) => ({
                name: row.full_name || row.user_name,
                value: row.total,
              }))}
              dataKey="value"
              nameKey="name"
              innerRadius="55%"
              outerRadius="85%"
              label={(entry) => `${entry.name}: ${entry.value}`}
            >
              {rows.map((row, index) => (
                <Cell
                  key={row.operator_id}
                  fill={DONUT_COLORS[index % DONUT_COLORS.length]}
                />
              ))}
            </Pie>
          </PieChart>
        </ChartContainer>
      </div>
    );
  }
  if (mode === "am") {
    return (
      <ChartContainer height={300}>
        <BarChart
          data={rows.map((row) => ({
            name: row.full_name?.split(" ")[0] || row.user_name,
            answered: row.answered,
            missed: row.missed,
          }))}
        >
          <XAxis dataKey="name" {...chartAxisProps} interval={0} />
          <YAxis {...chartAxisProps} width={36} />
          <Tooltip {...chartTooltipStyle} />
          <Bar
            dataKey="answered"
            stackId="e"
            fill={CHART_COLORS.answered}
            name={tCalls("answered")}
          />
          <Bar
            dataKey="missed"
            stackId="e"
            fill={CHART_COLORS.missed}
            name={tCalls("missed")}
          />
        </BarChart>
      </ChartContainer>
    );
  }
  return (
    <div>
      <ChartContainer height={300}>
        <BarChart
          data={rows.map((row) => ({
            name: row.full_name?.split(" ")[0] || row.user_name,
            minutes: row.duration_minutes,
          }))}
        >
          <XAxis dataKey="name" {...chartAxisProps} interval={0} />
          <YAxis {...chartAxisProps} width={44} />
          <Tooltip {...chartTooltipStyle} />
          <Bar dataKey="minutes" fill={CHART_COLORS.inbound}>
            <LabelList
              dataKey="minutes"
              position="top"
              fill="var(--fg-muted)"
              fontSize={10}
            />
          </Bar>
        </BarChart>
      </ChartContainer>
      <p className="mt-2 text-xs text-fg-faint">{t("roundingNote")}</p>
    </div>
  );
}

function ClientDistributionView() {
  const t = useTranslations("reports");
  const { data, isPending } = useQuery({
    queryKey: ["r-client"],
    queryFn: () => fetchPerClient(),
  });
  if (isPending) return <Skeleton />;
  const rows = data?.report ?? [];
  if (rows.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-surface p-10 text-center text-sm text-fg-faint">
        {t("noData")}
      </p>
    );
  }
  return (
    <table
      className="w-full rounded-lg border border-border bg-surface text-sm"
      data-testid="report-clients"
    >
      <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
        <tr>
          <th className="px-3 py-2 text-left">Клиент</th>
          <th className="px-3 py-2 text-right">Все</th>
          <th className="px-3 py-2 text-right">✓</th>
          <th className="px-3 py-2 text-right">✗</th>
          <th className="px-3 py-2 text-right">⏱</th>
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 50).map((row) => (
          <tr key={row.counterparty_number} className="border-t border-border">
            <td className="px-3 py-2">
              {row.name ?? (
                <span className="tnum">
                  {formatPhone(row.counterparty_number)}
                </span>
              )}
            </td>
            <td className="tnum px-3 py-2 text-right">{row.total}</td>
            <td className="tnum px-3 py-2 text-right text-accent">
              {row.answered}
            </td>
            <td className="tnum px-3 py-2 text-right text-danger">
              {row.missed}
            </td>
            <td className="tnum px-3 py-2 text-right">
              {formatDuration(row.duration)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function UnansweredView() {
  const t = useTranslations("reports");
  const [withContact, setWithContact] = useState(false);
  const [page, setPage] = useState(1);
  const { data, isPending } = useQuery({
    queryKey: ["r-unanswered"],
    queryFn: () => fetchUnanswered(),
  });
  if (isPending) return <Skeleton />;
  const all = (data?.report ?? []).filter((row) =>
    withContact ? Boolean(row.name) : true,
  );
  const pageSize = 20;
  const rows = all.slice((page - 1) * pageSize, page * pageSize);
  return (
    <div data-testid="report-unanswered">
      <label className="mb-2 flex items-center gap-1.5 text-sm">
        <input
          type="checkbox"
          checked={withContact}
          onChange={(event) => {
            setWithContact(event.target.checked);
            setPage(1);
          }}
          className="accent-[var(--accent)]"
        />
        {t("withContact")}
      </label>
      <table className="w-full rounded-lg border border-border bg-surface text-sm">
        <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
          <tr>
            <th className="px-3 py-2 text-left">Клиент</th>
            <th className="px-3 py-2 text-right">{t("howLongAgo")}</th>
            <th className="px-3 py-2 text-right">{t("attempts")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.counterparty_number}
              className="border-t border-border bg-danger/5"
            >
              <td className="px-3 py-2">
                {row.name ?? (
                  <span className="tnum">
                    {formatPhone(row.counterparty_number)}
                  </span>
                )}
              </td>
              <td className="tnum px-3 py-2 text-right">
                {humanizeAgo(row.last_attempt)}
              </td>
              <td className="tnum px-3 py-2 text-right">
                {row.attempts_since_success}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex justify-end gap-1.5 text-sm">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => setPage((value) => value - 1)}
          className="rounded-md border border-border px-2.5 py-1 disabled:opacity-40"
        >
          ←
        </button>
        <button
          type="button"
          disabled={page * pageSize >= all.length}
          onClick={() => setPage((value) => value + 1)}
          className="rounded-md border border-border px-2.5 py-1 disabled:opacity-40"
        >
          →
        </button>
      </div>
    </div>
  );
}

function LastContactView() {
  const { data, isPending } = useQuery({
    queryKey: ["r-last-contact"],
    queryFn: () => fetchLastContact(),
  });
  if (isPending) return <Skeleton />;
  return (
    <ul
      className="divide-y divide-border rounded-lg border border-border bg-surface"
      data-testid="report-last-contact"
    >
      {(data?.report ?? []).slice(0, 50).map((row) => (
        <li
          key={row.counterparty_number}
          className={cn(
            "flex items-center gap-2.5 px-4 py-2 text-sm",
            row.status === "no_answer" && "bg-danger/5",
          )}
        >
          <DirectionIcon direction={row.direction} />
          <span className="min-w-0 flex-1 truncate">
            {row.name ?? (
              <span className="tnum">
                {formatPhone(row.counterparty_number)}
              </span>
            )}
          </span>
          <span className="tnum text-xs text-fg-muted">
            {new Date(row.last_call).toLocaleString("ru-RU", {
              day: "2-digit",
              month: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          <span className="tnum text-xs">{formatDuration(row.duration)}</span>
          {row.status === "answered" && (
            <CallAudioButton callId={row.call_record_id} />
          )}
        </li>
      ))}
    </ul>
  );
}

function Skeleton() {
  return (
    <div
      className="h-64 animate-pulse rounded-lg bg-surface-2"
      data-testid="report-skeleton"
    />
  );
}

// ── Page shell with tab groups + dropdown submenus ─────────────────────────

function ReportsInner() {
  const t = useTranslations("reports");
  const tNav = useTranslations("nav");
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>(
    params.get("tab") === "unanswered" ? "unanswered" : "general",
  );

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">{tNav("reports")}</h1>

      <div className="mb-4 flex flex-wrap gap-1.5" data-testid="report-tabs">
        {TAB_GROUPS.map(({ group, tabs }) =>
          tabs.length === 1 ? (
            <button
              key={group}
              type="button"
              onClick={() => setTab(tabs[0].id)}
              className={cn(
                "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
                tab === tabs[0].id
                  ? "bg-accent text-accent-fg shadow-sm"
                  : "border border-border text-fg-muted hover:bg-surface-2",
              )}
            >
              {t(group as "general")}
            </button>
          ) : (
            <details key={group} className="group relative">
              <summary
                className={cn(
                  "cursor-pointer list-none rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
                  tabs.some((item) => item.id === tab)
                    ? "bg-accent text-accent-fg shadow-sm"
                    : "border border-border text-fg-muted hover:bg-surface-2",
                )}
              >
                {t(group as "periods")} ▾
              </summary>
              <div className="absolute z-10 mt-1 w-56 rounded-md border border-border bg-surface p-1 shadow-lg">
                {tabs.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    data-testid={`tab-${item.id}`}
                    onClick={(event) => {
                      setTab(item.id);
                      (
                        event.currentTarget.closest(
                          "details",
                        ) as HTMLDetailsElement
                      ).open = false;
                    }}
                    className={cn(
                      "block w-full rounded px-3 py-1.5 text-left text-sm",
                      tab === item.id
                        ? "text-accent"
                        : "text-fg-muted hover:bg-surface-2",
                    )}
                  >
                    {t(item.label as "distribution")}
                  </button>
                ))}
              </div>
            </details>
          ),
        )}
      </div>

      {tab === "general" && <GeneralView />}
      {tab === "weekday" && <WeekdayView />}
      {tab === "period" && <PeriodView />}
      {tab === "emp-distribution" && <EmployeeView mode="distribution" />}
      {tab === "emp-am" && <EmployeeView mode="am" />}
      {tab === "emp-duration" && <EmployeeView mode="duration" />}
      {tab === "client-distribution" && <ClientDistributionView />}
      {tab === "unanswered" && <UnansweredView />}
      {tab === "last-contact" && <LastContactView />}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <Suspense>
      <ReportsInner />
    </Suspense>
  );
}
