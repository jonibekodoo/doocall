"use client";

/** §6.1 Рабочий стол — period tabs, stacked direction bars, per-operator
 * columns, latest-successful + currently-unanswered tables. */

import { useQuery } from "@tanstack/react-query";
import { CircleHelp } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, LabelList, Tooltip, XAxis, YAxis } from "recharts";

import { CallAudioButton } from "@/components/CallAudioButton";
import { DirectionIcon, directionBars } from "@/components/calls-shared";
import {
  CHART_COLORS,
  ChartContainer,
  chartAxisProps,
  chartTooltipStyle,
} from "@/components/charts/theme";
import { fetchDashboard } from "@/lib/api/endpoints";
import type { CallRow } from "@/lib/api/types";
import { formatDuration, formatPhone } from "@/lib/format";
import { cn } from "@/lib/utils";

const PERIODS = ["today", "3d", "7d"] as const;

function CallsMiniTable({
  title,
  rows,
  unansweredTint = false,
  reportHref,
}: {
  title: string;
  rows: CallRow[];
  unansweredTint?: boolean;
  reportHref: string;
}) {
  const tc = useTranslations("common");
  const emptyText = useTranslations("table")("empty");
  return (
    <section className="min-w-0 rounded-lg border border-border bg-surface">
      <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Link
          href={reportHref}
          className="text-xs font-medium text-accent hover:underline"
        >
          {tc("fullReport")}
        </Link>
      </header>
      {rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-fg-faint">
          {emptyText}
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((call) => (
            <li
              key={call.id}
              className={cn(
                "flex items-center gap-2.5 px-4 py-2 text-sm",
                unansweredTint && "bg-danger/5",
              )}
            >
              <DirectionIcon direction={call.direction} />
              <span className="min-w-0 flex-1 truncate">
                {call.counterparty_name ??
                  formatPhone(call.counterparty_number)}
              </span>
              <span className="tnum shrink-0 text-xs text-fg-muted">
                {new Date(call.start_time).toLocaleTimeString("ru-RU", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <span className="tnum shrink-0 text-xs text-fg-muted">
                {formatDuration(call.duration)}
              </span>
              {call.status === "answered" && (
                <CallAudioButton callId={call.id} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function CabinetHome() {
  const tNav = useTranslations("nav");
  const tPeriod = useTranslations("period");
  const tCalls = useTranslations("calls");
  const tDash = useTranslations("dashboard");
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("today");
  const [operator, setOperator] = useState<number | undefined>(undefined);

  const { data, isPending } = useQuery({
    queryKey: ["dashboard", period, operator],
    queryFn: () => fetchDashboard(period, operator),
  });

  const bars = data ? directionBars(data.general) : [];
  const operators = data?.per_operator ?? [];

  return (
    <div data-testid="dashboard-page">
      {/* Period tabs */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <span className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{tNav("dashboard")}</h1>
          <a
            href="/help/recording"
            target="_blank"
            rel="noopener"
            data-testid="recording-guide-link"
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs font-medium text-fg-muted hover:border-accent hover:text-accent"
          >
            <CircleHelp className="size-3.5" />
            {tDash("recordingGuide")}
          </a>
        </span>
        <div className="flex gap-1.5" data-testid="period-tabs">
          {PERIODS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setPeriod(option)}
              aria-pressed={option === period}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-medium",
                option === period
                  ? "bg-accent text-accent-fg"
                  : "border border-border text-fg-muted hover:bg-surface-2",
              )}
            >
              {tPeriod(option)}
            </button>
          ))}
        </div>
      </div>

      {/* Operator filter */}
      <div className="mb-4">
        <select
          aria-label={tCalls("operator")}
          value={operator ?? ""}
          onChange={(event) =>
            setOperator(
              event.target.value ? Number(event.target.value) : undefined,
            )
          }
          className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm"
        >
          <option value="">{tDash("allOperators")}</option>
          {operators.map((op) => (
            <option key={op.id} value={op.id}>
              {op.full_name || op.user_name}
            </option>
          ))}
        </select>
      </div>

      {isPending ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-64 animate-pulse rounded-lg bg-surface-2"
              data-testid="dash-skeleton"
            />
          ))}
        </div>
      ) : data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* §6.1 stacked horizontal bars — Все/Входящие/Исходящие */}
          <ChartContainer height={200}>
            <BarChart
              data={bars.map((bar) => ({
                ...bar,
                label: tDash(bar.key as "all" | "inbound" | "outbound"),
              }))}
              layout="vertical"
              margin={{ left: 8, right: 40 }}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="label"
                width={92}
                {...chartAxisProps}
              />
              <Tooltip {...chartTooltipStyle} />
              <Bar
                dataKey="answered"
                stackId="a"
                fill={CHART_COLORS.answered}
                name={tCalls("answered")}
              />
              <Bar
                dataKey="missed"
                stackId="a"
                fill={CHART_COLORS.missed}
                name={tCalls("missed")}
              >
                <LabelList
                  dataKey="total"
                  position="right"
                  fill="var(--fg-muted)"
                  fontSize={12}
                />
              </Bar>
            </BarChart>
          </ChartContainer>

          {/* Per-operator stacked columns, sorted desc with labels */}
          <ChartContainer height={200}>
            <BarChart
              data={[...operators]
                .sort((a, b) => b.total - a.total)
                .map((op) => ({
                  name: op.full_name?.split(" ")[0] || op.user_name,
                  answered: op.answered,
                  missed: op.missed,
                  total: op.total,
                }))}
              margin={{ top: 18 }}
            >
              <XAxis dataKey="name" {...chartAxisProps} interval={0} />
              <YAxis {...chartAxisProps} width={34} />
              <Tooltip {...chartTooltipStyle} />
              <Bar
                dataKey="answered"
                stackId="o"
                fill={CHART_COLORS.answered}
                name={tCalls("answered")}
              />
              <Bar
                dataKey="missed"
                stackId="o"
                fill={CHART_COLORS.missed}
                name={tCalls("missed")}
              >
                <LabelList
                  dataKey="total"
                  position="top"
                  fill="var(--fg-muted)"
                  fontSize={11}
                />
              </Bar>
            </BarChart>
          </ChartContainer>

          <CallsMiniTable
            title={tDash("latestSuccessful")}
            rows={data.latest_calls}
            reportHref="/cabinet/calls?status=answered"
          />
          <CallsMiniTable
            title={tDash("currentUnanswered")}
            rows={data.unanswered_now}
            unansweredTint
            reportHref="/cabinet/reports?tab=unanswered"
          />
        </div>
      ) : null}
    </div>
  );
}
