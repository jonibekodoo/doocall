"use client";

/** AI Tahlil — Kotib AI call analyses: summary tiles, filters, paged table.
 * Without a Kotib connection (and no history) a "contact your admin" screen. */

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  AudioLines,
  Brain,
  MessageSquareText,
  Settings,
  Sparkles,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { DataTable, type Column } from "@/components/ui/DataTable";
import {
  DateRangePicker,
  type DateRange,
} from "@/components/ui/DateRangePicker";
import { FilterBar, FilterSelect } from "@/components/ui/FilterBar";
import { Pagination } from "@/components/ui/Pagination";
import { StatCard } from "@/components/ui/StatCard";
import {
  fetchAiAnalyses,
  fetchAiStatus,
  fetchPerEmployee,
  type AiAnalysisFilters,
  type AiAnalysisRow,
} from "@/lib/api/endpoints";
import { formatPhone } from "@/lib/format";

import { ScoreBadge } from "./ai-shared";

const FEATURES = ["fTranscribe", "fSentiment", "fSummary"] as const;
const FEATURE_ICONS = {
  fTranscribe: AudioLines,
  fSentiment: Brain,
  fSummary: MessageSquareText,
} as const;

const SETTINGS_HREF = "/cabinet/settings/integrations/kotib";

function daysAgoIso(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Gradient full-page state (the former coming-soon teaser). */
function NotConnected({ isAdmin }: { isAdmin: boolean }) {
  const t = useTranslations("ai");
  return (
    <div
      data-testid="ai-not-connected"
      className="relative overflow-hidden rounded-2xl border border-border"
    >
      <div className="absolute inset-0 bg-[#0d1220]" />
      <div className="pointer-events-none absolute -left-32 -top-32 size-96 rounded-full bg-[#7c3aed]/40 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 left-1/3 size-96 rounded-full bg-[#0ea5e9]/30 blur-3xl" />
      <div className="pointer-events-none absolute -right-24 -top-24 size-80 rounded-full bg-[#14b8a6]/30 blur-3xl" />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.15]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, #ffffff 1px, transparent 0)",
          backgroundSize: "28px 28px",
        }}
      />

      <div className="relative grid min-h-[70vh] place-items-center px-6 py-20 text-center text-white">
        <div className="max-w-2xl">
          <span className="mx-auto grid size-16 place-items-center rounded-2xl bg-white/10 backdrop-blur">
            <Sparkles className="size-8 text-[#a78bfa]" />
          </span>
          <p className="mt-6 inline-block rounded-full border border-white/20 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-[#7dd3fc]">
            {t("badge")}
          </p>
          <h1 className="mt-4 bg-gradient-to-r from-[#a78bfa] via-[#7dd3fc] to-[#5eead4] bg-clip-text font-[family-name:var(--font-display)] text-4xl font-bold text-transparent sm:text-5xl">
            {t("notConnectedTitle")}
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-white/80">
            {t("notConnectedText")}
          </p>
          {isAdmin && (
            <Link
              href={SETTINGS_HREF}
              data-testid="ai-open-settings"
              className="mt-6 inline-flex items-center gap-2 rounded-md bg-white px-4 py-2 text-sm font-semibold text-[#0d1220] hover:opacity-90"
            >
              <Settings className="size-4" /> {t("openSettings")}
            </Link>
          )}

          <div className="mt-10 grid gap-3 sm:grid-cols-3">
            {FEATURES.map((key) => {
              const Icon = FEATURE_ICONS[key];
              return (
                <div
                  key={key}
                  className="rounded-xl border border-white/10 bg-white/5 p-4 backdrop-blur"
                >
                  <Icon className="mx-auto size-5 text-[#7dd3fc]" />
                  <p className="mt-2 text-sm font-medium text-white/85">
                    {t(key)}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function AnalysesList() {
  const t = useTranslations("ai");
  const tc = useTranslations("common");

  const [draftRange, setDraftRange] = useState<DateRange>({
    from: daysAgoIso(30),
    to: daysAgoIso(0),
  });
  const [draftEmployee, setDraftEmployee] = useState("");
  const [draftMin, setDraftMin] = useState("");
  const [draftMax, setDraftMax] = useState("");
  const [draftViolations, setDraftViolations] = useState(false);
  const [draftSearch, setDraftSearch] = useState("");
  const [applied, setApplied] = useState<AiAnalysisFilters>({
    dateFrom: daysAgoIso(30),
    dateTo: daysAgoIso(0),
  });
  const [page, setPage] = useState(1);

  const { data: employees } = useQuery({
    queryKey: ["per-employee-list"],
    queryFn: () => fetchPerEmployee(),
    staleTime: 300_000,
  });
  const filters: AiAnalysisFilters = { ...applied, page };
  const { data, isPending } = useQuery({
    queryKey: ["ai-analyses", filters],
    queryFn: () => fetchAiAnalyses(filters),
  });

  const apply = () => {
    setPage(1);
    setApplied({
      dateFrom: draftRange.from || undefined,
      dateTo: draftRange.to || undefined,
      employees: draftEmployee ? [Number(draftEmployee)] : undefined,
      minScore: draftMin === "" ? undefined : Number(draftMin),
      maxScore: draftMax === "" ? undefined : Number(draftMax),
      violations: draftViolations || undefined,
      search: draftSearch || undefined,
    });
  };

  const detailHref = (row: AiAnalysisRow) => `/cabinet/ai/${row.id}`;
  const columns: Column<AiAnalysisRow>[] = [
    {
      key: "date",
      header: t("date"),
      cell: (row) => (
        <Link
          href={detailHref(row)}
          className="tnum text-xs text-accent hover:underline"
        >
          {formatDateTime(row.start_time)}
        </Link>
      ),
    },
    {
      key: "operator",
      header: t("operator"),
      cell: (row) => (
        <span className="block truncate">{row.operator?.full_name ?? "—"}</span>
      ),
    },
    {
      key: "client",
      header: t("client"),
      cell: (row) => <span className="tnum">{formatPhone(row.phone)}</span>,
    },
    {
      key: "score",
      header: t("score"),
      cell: (row) => <ScoreBadge score={row.final_score} />,
    },
    {
      key: "summary",
      header: t("summary"),
      className: "max-w-md",
      cell: (row) => (
        <Link
          href={detailHref(row)}
          title={row.summary}
          className="line-clamp-2 text-sm hover:text-accent"
        >
          {row.summary || "—"}
        </Link>
      ),
    },
    {
      key: "violation",
      header: (
        <AlertTriangle className="size-3.5" aria-label={t("violation")} />
      ),
      cell: (row) =>
        row.has_violation ? (
          <span title={t("violation")} data-testid={`ai-violation-${row.id}`}>
            <AlertTriangle className="size-4 text-danger" />
          </span>
        ) : null,
    },
  ];

  const summary = data?.summary;
  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatCard label={t("tileCount")} value={summary?.count ?? "—"} />
        <StatCard
          label={t("tileAvg")}
          value={
            summary?.avg_score === null || summary?.avg_score === undefined
              ? "—"
              : Math.round(summary.avg_score * 10) / 10
          }
          tone="accent"
        />
        <StatCard
          label={t("tileViolations")}
          value={summary?.violations ?? "—"}
          tone="danger"
        />
      </div>

      <FilterBar search={draftSearch} onSearch={setDraftSearch}>
        <FilterSelect
          label={t("operator")}
          value={draftEmployee}
          onChange={setDraftEmployee}
          options={[
            { value: "", label: t("operator") },
            ...(employees?.report ?? []).map((emp) => ({
              value: String(emp.operator_id),
              label: emp.full_name || emp.user_name,
            })),
          ]}
        />
        <DateRangePicker value={draftRange} onChange={setDraftRange} />
        <input
          type="number"
          value={draftMin}
          onChange={(event) => setDraftMin(event.target.value)}
          placeholder={`${t("score")} ≥`}
          aria-label={`${t("score")} ≥`}
          data-testid="ai-min-score"
          className="w-24 rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        />
        <input
          type="number"
          value={draftMax}
          onChange={(event) => setDraftMax(event.target.value)}
          placeholder={`${t("score")} ≤`}
          aria-label={`${t("score")} ≤`}
          data-testid="ai-max-score"
          className="w-24 rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        />
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={draftViolations}
            onChange={(event) => setDraftViolations(event.target.checked)}
            data-testid="ai-only-violations"
            className="size-4 accent-[var(--accent)]"
          />
          {t("onlyViolations")}
        </label>
        <button
          type="button"
          data-testid="ai-apply"
          onClick={apply}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg hover:opacity-90"
        >
          {tc("apply")}
        </button>
      </FilterBar>

      <DataTable<AiAnalysisRow>
        columns={columns}
        rows={data?.analyses ?? []}
        loading={isPending}
        storageKey="ai-analyses"
        empty={
          <p className="py-8 text-center text-sm text-fg-faint">
            {t("noResults")}
          </p>
        }
      />
      <Pagination
        page={page}
        pages={data?.pages ?? 1}
        total={data?.count ?? 0}
        onPage={setPage}
      />
    </>
  );
}

export default function AiAnalysisPage() {
  const t = useTranslations("ai");
  const { data: status, isPending } = useQuery({
    queryKey: ["ai-status"],
    queryFn: fetchAiStatus,
  });

  if (isPending) {
    return (
      <div data-testid="ai-loading" className="space-y-3">
        <div className="h-7 w-48 animate-pulse rounded bg-surface-3" />
        <div className="grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((index) => (
            <div
              key={index}
              className="h-20 animate-pulse rounded-lg bg-surface-3"
            />
          ))}
        </div>
      </div>
    );
  }
  if (!status) return null;

  if (!status.kotib_connected && !status.has_analyses) {
    return <NotConnected isAdmin={status.is_admin} />;
  }

  return (
    <div data-testid="ai-page">
      <h1 className="mb-4 text-xl font-semibold">{t("title")}</h1>
      {!status.kotib_connected && (
        <div
          data-testid="ai-disconnected-banner"
          className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-warning/40 bg-warning/10 px-4 py-3 text-sm"
        >
          <AlertTriangle className="size-4 shrink-0 text-warning" />
          <span className="flex-1">{t("disconnectedBanner")}</span>
          {status.is_admin && (
            <Link
              href={SETTINGS_HREF}
              className="font-semibold text-accent hover:underline"
            >
              {t("openSettings")}
            </Link>
          )}
        </div>
      )}
      {status.kotib_connected && !status.has_analyses ? (
        <div
          data-testid="ai-empty"
          className="grid place-items-center rounded-lg border border-dashed border-border bg-surface px-6 py-16 text-center"
        >
          <Sparkles className="size-8 text-accent" />
          <p className="mt-3 font-semibold">{t("emptyTitle")}</p>
          <p className="mt-1 max-w-md text-sm text-fg-muted">
            {t("emptyText")}
          </p>
        </div>
      ) : (
        <AnalysesList />
      )}
    </div>
  );
}
