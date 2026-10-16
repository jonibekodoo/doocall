"use client";

/** §6.4 Отчеты — tab bar with submenus; every report wired to the API. */

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
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
import { Pagination, usePagination } from "@/components/ui/Pagination";
import { StatCard } from "@/components/ui/StatCard";
import {
  fetchAccountSettings,
  fetchGeneralReport,
  fetchLastContact,
  fetchPerClient,
  fetchPerEmployee,
  fetchPeriodCounts,
  fetchUnanswered,
  fetchWeekdayMatrix,
  type ReportFilters,
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

// ── Shared filter (dates in the company time zone + operators) ────────────

const PRESETS = [
  "today",
  "yesterday",
  "last7",
  "last30",
  "thisMonth",
  "lastMonth",
  "all",
] as const;
type Preset = (typeof PRESETS)[number];
const DEFAULT_PRESET: Preset = "last30";

/** Today's calendar date (YYYY-MM-DD) in ``timeZone`` (browser zone if unset). */
function todayIn(timeZone: string | undefined, now: Date): string {
  const format = (zone?: string) =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(now);
  try {
    return format(timeZone || undefined);
  } catch {
    return format(); // unknown zone name → browser zone
  }
}

/** Pure calendar arithmetic on YYYY-MM-DD (UTC-based: no DST surprises). */
function shiftDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function presetRange(
  preset: Preset,
  today: string,
): { from: string; to: string } {
  const [year, month] = today.split("-").map(Number);
  const monthStart = (y: number, m: number) =>
    new Date(Date.UTC(y, m - 1, 1)).toISOString().slice(0, 10);
  switch (preset) {
    case "today":
      return { from: today, to: today };
    case "yesterday":
      return { from: shiftDays(today, -1), to: shiftDays(today, -1) };
    case "last7":
      return { from: shiftDays(today, -6), to: today };
    case "last30":
      return { from: shiftDays(today, -29), to: today };
    case "thisMonth":
      return { from: monthStart(year, month), to: today };
    case "lastMonth":
      return {
        from: monthStart(year, month - 1),
        to: shiftDays(monthStart(year, month), -1),
      };
    case "all":
      return { from: "", to: "" };
  }
}

/** "2026-10-01" → "01.10.2026". */
function dmy(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

interface ReportFilterState {
  filters: ReportFilters;
  /** False until the company time zone is known (dates depend on it). */
  ready: boolean;
  /** "01.10.2026 – 16.10.2026", or "" for all time. */
  rangeLabel: string;
}

const ReportFilterContext = createContext<ReportFilterState>({
  filters: {},
  ready: true,
  rangeLabel: "",
});

const useReportFilters = () => useContext(ReportFilterContext);

/** Card title + the active range as a muted subtitle. */
function CardTitle({ children }: { children: React.ReactNode }) {
  const { rangeLabel } = useReportFilters();
  const t = useTranslations("reports");
  return (
    <span className="flex flex-col">
      {children}
      <span
        className="tnum text-xs font-normal text-fg-faint"
        data-testid="card-range"
      >
        {rangeLabel || t("allTime")}
      </span>
    </span>
  );
}

function ReportFilterBar({
  disabled,
  preset,
  range,
  employees,
  onPreset,
  onRange,
  onEmployees,
}: {
  disabled: boolean;
  preset: Preset | null;
  range: { from: string; to: string };
  employees: number[];
  onPreset: (preset: Preset) => void;
  onRange: (range: { from: string; to: string }) => void;
  onEmployees: (ids: number[]) => void;
}) {
  const t = useTranslations("reports");
  // All operators (unfiltered) — same source as the Calls page operator filter.
  const { data } = useQuery({
    queryKey: ["per-employee-list"],
    queryFn: () => fetchPerEmployee(),
    staleTime: 300_000,
  });
  const operators = data?.report ?? [];
  const toggle = (id: number) =>
    onEmployees(
      employees.includes(id)
        ? employees.filter((item) => item !== id)
        : [...employees, id].sort((a, b) => a - b),
    );

  return (
    <fieldset
      disabled={disabled}
      data-testid="report-filters"
      className="mb-4 space-y-2 rounded-lg border border-border bg-surface p-3 disabled:opacity-60"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <CalendarDays className="mr-1 size-4 text-fg-faint" />
        {PRESETS.map((key) => (
          <button
            key={key}
            type="button"
            data-testid={`preset-${key}`}
            aria-pressed={preset === key}
            onClick={() => onPreset(key)}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-medium",
              preset === key
                ? "bg-accent text-accent-fg"
                : "border border-border text-fg-muted hover:bg-surface-2",
            )}
          >
            {t(`preset_${key}`)}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="date"
          aria-label={t("dateFrom")}
          data-testid="filter-from"
          value={range.from}
          max={range.to || undefined}
          onChange={(event) => onRange({ ...range, from: event.target.value })}
          className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs"
        />
        <span className="text-fg-faint">—</span>
        <input
          type="date"
          aria-label={t("dateTo")}
          data-testid="filter-to"
          value={range.to}
          min={range.from || undefined}
          onChange={(event) => onRange({ ...range, to: event.target.value })}
          className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs"
        />

        <details className="relative" data-testid="filter-operators">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-surface-2">
            <Users className="size-3.5" />
            {employees.length
              ? t("operatorsSelected", { count: employees.length })
              : t("allOperators")}{" "}
            ▾
          </summary>
          <div className="absolute z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-md border border-border bg-surface p-1 shadow-lg">
            {employees.length > 0 && (
              <button
                type="button"
                data-testid="filter-operators-clear"
                onClick={() => onEmployees([])}
                className="block w-full rounded px-2.5 py-1.5 text-left text-xs text-accent hover:bg-surface-2"
              >
                {t("allOperators")}
              </button>
            )}
            {operators.map((operator) => (
              <label
                key={operator.operator_id}
                className="flex items-center gap-2 rounded px-2.5 py-1.5 text-sm hover:bg-surface-2"
              >
                <input
                  type="checkbox"
                  data-testid={`filter-operator-${operator.operator_id}`}
                  checked={employees.includes(operator.operator_id)}
                  onChange={() => toggle(operator.operator_id)}
                  className="size-4 accent-[var(--accent)]"
                />
                {operator.full_name || operator.user_name}
              </label>
            ))}
          </div>
        </details>
        <span className="text-xs text-fg-faint">{t("defaultHint")}</span>
      </div>
    </fieldset>
  );
}

// ── Individual report views ────────────────────────────────────────────────

function GeneralView() {
  const { filters, ready } = useReportFilters();
  const t = useTranslations("dashboard");
  const tCalls = useTranslations("calls");
  const { data, isPending } = useQuery({
    queryKey: ["r-general", filters],
    queryFn: () => fetchGeneralReport(filters),
    enabled: ready,
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
        <ReportCard title={<CardTitle>{tReports("answeredMissed")}</CardTitle>}>
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
        <ReportCard title={<CardTitle>{tReports("byDirection")}</CardTitle>}>
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
  const { filters, ready } = useReportFilters();
  const t = useTranslations("calls");
  const tReports = useTranslations("reports");
  const { data, isPending } = useQuery({
    queryKey: ["r-weekday", filters],
    queryFn: () => fetchWeekdayMatrix(filters),
    enabled: ready,
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
    <ReportCard title={<CardTitle>{tReports("weekdayMatrix")}</CardTitle>}>
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
  const { filters, ready } = useReportFilters();
  const t = useTranslations("reports");
  const [group, setGroup] = useState<"day" | "week" | "month">("day");
  const [unique, setUnique] = useState(false);
  const { data, isPending } = useQuery({
    queryKey: ["r-period", group, unique, filters],
    queryFn: () => fetchPeriodCounts(group, unique, filters),
    enabled: ready,
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
  const { filters, ready } = useReportFilters();
  const t = useTranslations("reports");
  const tCalls = useTranslations("calls");
  const { data, isPending } = useQuery({
    queryKey: ["r-employee", filters],
    queryFn: () => fetchPerEmployee(filters),
    enabled: ready,
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
  const { filters, ready } = useReportFilters();
  const t = useTranslations("reports");
  const { data, isPending } = useQuery({
    queryKey: ["r-client", filters],
    queryFn: () => fetchPerClient(filters),
    enabled: ready,
  });
  const paged = usePagination(data?.report ?? []);
  if (isPending) return <Skeleton />;
  if (paged.total === 0) {
    return (
      <p className="rounded-lg border border-border bg-surface p-10 text-center text-sm text-fg-faint">
        {t("noData")}
      </p>
    );
  }
  return (
    <div>
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
        {paged.slice.map((row) => (
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
    <Pagination
      page={paged.page}
      pages={paged.pages}
      total={paged.total}
      start={paged.start}
      end={paged.end}
      onPage={paged.setPage}
    />
    </div>
  );
}

function UnansweredView() {
  const { filters, ready } = useReportFilters();
  const t = useTranslations("reports");
  const [withContact, setWithContact] = useState(false);
  const { data, isPending } = useQuery({
    queryKey: ["r-unanswered", filters],
    queryFn: () => fetchUnanswered(filters),
    enabled: ready,
  });
  const all = (data?.report ?? []).filter((row) =>
    withContact ? Boolean(row.name) : true,
  );
  const paged = usePagination(all);
  if (isPending) return <Skeleton />;
  const rows = paged.slice;
  return (
    <div data-testid="report-unanswered">
      <label className="mb-2 flex items-center gap-1.5 text-sm">
        <input
          type="checkbox"
          checked={withContact}
          onChange={(event) => {
            setWithContact(event.target.checked);
            paged.reset();
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
      <Pagination
        page={paged.page}
        pages={paged.pages}
        total={paged.total}
        start={paged.start}
        end={paged.end}
        onPage={paged.setPage}
        className="mt-2"
      />
    </div>
  );
}

function LastContactView() {
  const { filters, ready } = useReportFilters();
  const { data, isPending } = useQuery({
    queryKey: ["r-last-contact", filters],
    queryFn: () => fetchLastContact(filters),
    enabled: ready,
  });
  const paged = usePagination(data?.report ?? []);
  if (isPending) return <Skeleton />;
  return (
    <div>
    <ul
      className="divide-y divide-border rounded-lg border border-border bg-surface"
      data-testid="report-last-contact"
    >
      {paged.slice.map((row) => (
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
    <Pagination
      page={paged.page}
      pages={paged.pages}
      total={paged.total}
      start={paged.start}
      end={paged.end}
      onPage={paged.setPage}
    />
    </div>
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

const ALL_TABS = TAB_GROUPS.flatMap((group) => group.tabs.map((tab) => tab.id));
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

type Range = { from: string; to: string };

/** Filter as read from the URL: null range = the default (Oxirgi 30 kun). */
function filterFromUrl(params: URLSearchParams): {
  range: Range | null;
  employees: number[];
} {
  const from = params.get("date_from") ?? "";
  const to = params.get("date_to") ?? "";
  const range =
    params.get("range") === "all"
      ? { from: "", to: "" }
      : ISO_DATE.test(from) || ISO_DATE.test(to)
        ? {
            from: ISO_DATE.test(from) ? from : "",
            to: ISO_DATE.test(to) ? to : "",
          }
        : null;
  const employees = (params.get("employees") ?? "")
    .split(",")
    .map((part) => Number(part))
    .filter((id) => Number.isInteger(id) && id > 0);
  return { range, employees };
}

function ReportsInner() {
  const t = useTranslations("reports");
  const tNav = useTranslations("nav");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const initialTab = params.get("tab") as Tab | null;
  const [tab, setTabState] = useState<Tab>(
    initialTab && ALL_TABS.includes(initialTab) ? initialTab : "general",
  );
  const [initial] = useState(() => filterFromUrl(params));
  const [chosenRange, setChosenRange] = useState<Range | null>(initial.range);
  const [employees, setEmployees] = useState<number[]>(initial.employees);

  // Presets count days in the COMPANY zone (admins can read it; others fall
  // back to the browser zone — the same in practice).
  const { data: account, isPending: zonePending } = useQuery({
    queryKey: ["s-account"],
    queryFn: fetchAccountSettings,
    retry: false,
    staleTime: 600_000,
  });
  const today = todayIn(account?.settings?.timezone, new Date());
  const range = chosenRange ?? presetRange(DEFAULT_PRESET, today);
  const activePreset =
    PRESETS.find((key) => {
      const candidate = presetRange(key, today);
      return candidate.from === range.from && candidate.to === range.to;
    }) ?? null;

  const writeUrl = useCallback(
    (next: { range: Range | null; employees: number[]; tab: Tab }) => {
      const query = new URLSearchParams(params.toString());
      for (const key of ["date_from", "date_to", "range", "employees", "tab"]) {
        query.delete(key);
      }
      if (next.range) {
        if (!next.range.from && !next.range.to) query.set("range", "all");
        if (next.range.from) query.set("date_from", next.range.from);
        if (next.range.to) query.set("date_to", next.range.to);
      }
      if (next.employees.length)
        query.set("employees", next.employees.join(","));
      if (next.tab !== "general") query.set("tab", next.tab);
      const text = query.toString();
      router.replace(text ? `${pathname}?${text}` : pathname, {
        scroll: false,
      });
    },
    [params, pathname, router],
  );

  const setRange = (next: Range) => {
    setChosenRange(next);
    writeUrl({ range: next, employees, tab });
  };
  const setOperators = (ids: number[]) => {
    setEmployees(ids);
    writeUrl({ range: chosenRange, employees: ids, tab });
  };
  const setTab = (next: Tab) => {
    setTabState(next);
    writeUrl({ range: chosenRange, employees, tab: next });
  };

  const filterState = useMemo<ReportFilterState>(
    () => ({
      ready: !zonePending,
      filters: {
        dateFrom: range.from || undefined,
        dateTo: range.to || undefined,
        employees: employees.length ? employees : undefined,
      },
      rangeLabel:
        range.from || range.to
          ? `${range.from ? dmy(range.from) : "…"} – ${range.to ? dmy(range.to) : "…"}`
          : "",
    }),
    [range.from, range.to, employees, zonePending],
  );

  return (
    <ReportFilterContext.Provider value={filterState}>
      <div>
        <h1 className="mb-4 text-xl font-semibold">{tNav("reports")}</h1>

        <ReportFilterBar
          disabled={zonePending}
          preset={activePreset}
          range={range}
          employees={employees}
          onPreset={(key) => setRange(presetRange(key, today))}
          onRange={setRange}
          onEmployees={setOperators}
        />

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

        <p
          className="tnum mb-3 text-sm text-fg-muted"
          data-testid="report-range"
        >
          {filterState.rangeLabel
            ? t("rangeLabel", { range: filterState.rangeLabel })
            : t("rangeAll")}
        </p>

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
    </ReportFilterContext.Provider>
  );
}

export default function ReportsPage() {
  return (
    <Suspense>
      <ReportsInner />
    </Suspense>
  );
}
