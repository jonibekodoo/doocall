"use client";

/** §6.2 Звонки — full filter bar, paginated table, audio, export.
 * Call records are immutable — no delete anywhere. */

import { useQuery } from "@tanstack/react-query";
import { Download, UserPlus } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { DirectionIcon } from "@/components/calls-shared";
import { CallAudioButton } from "@/components/CallAudioButton";
import { DataTable, type Column } from "@/components/ui/DataTable";
import {
  DateRangePicker,
  type DateRange,
} from "@/components/ui/DateRangePicker";
import { FilterBar, FilterSelect } from "@/components/ui/FilterBar";
import { useToastStore } from "@/components/ui/Toast";
import {
  fetchCalls,
  fetchExport,
  fetchPerEmployee,
  startExport,
} from "@/lib/api/endpoints";
import type { CallRow } from "@/lib/api/types";
import type { CallFilters } from "@/lib/filters";
import { formatDuration, formatPhone } from "@/lib/format";

function daysAgoIso(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

function CallsInner() {
  const tNav = useTranslations("nav");
  const t = useTranslations("calls");
  const tc = useTranslations("common");
  const tContacts = useTranslations("contacts");
  const params = useSearchParams();

  // Staged (draft) filters — applied on Применить (§6.2, default 30d).
  const [draftRange, setDraftRange] = useState<DateRange>({
    from: daysAgoIso(30),
    to: daysAgoIso(0),
  });
  const [draftDirection, setDraftDirection] = useState("");
  const [draftStatus, setDraftStatus] = useState(params.get("status") ?? "");
  const [draftSearch, setDraftSearch] = useState("");
  const [draftMinDuration, setDraftMinDuration] = useState("");
  const [draftSim, setDraftSim] = useState("");
  const [draftEmployee, setDraftEmployee] = useState("");

  const [applied, setApplied] = useState<CallFilters>({
    dateFrom: daysAgoIso(30),
    dateTo: daysAgoIso(0),
    status: (params.get("status") as CallFilters["status"]) ?? undefined,
  });
  const [page, setPage] = useState(1);
  const [ordering, setOrdering] = useState<CallFilters["ordering"]>("-date");

  const { data: employees } = useQuery({
    queryKey: ["per-employee-list"],
    queryFn: () => fetchPerEmployee(),
    staleTime: 300_000,
  });

  const filters: CallFilters = { ...applied, page, ordering };
  const { data, isPending } = useQuery({
    queryKey: ["calls", filters],
    queryFn: () => fetchCalls(filters),
  });

  const apply = () => {
    setPage(1);
    setApplied({
      dateFrom: draftRange.from || undefined,
      dateTo: draftRange.to || undefined,
      direction: (draftDirection || undefined) as CallFilters["direction"],
      status: (draftStatus || undefined) as CallFilters["status"],
      search: draftSearch || undefined,
      minDuration: draftMinDuration ? Number(draftMinDuration) : undefined,
      simSlot: draftSim === "" ? undefined : Number(draftSim),
      employees: draftEmployee ? [Number(draftEmployee)] : undefined,
    });
  };

  // Export with task-progress toast (poll until done/failed).
  const [exportId, setExportId] = useState<number | null>(null);
  useEffect(() => {
    if (exportId === null) return;
    const timer = setInterval(async () => {
      try {
        const status = await fetchExport(exportId);
        if (status.status === "done" && status.url) {
          clearInterval(timer);
          setExportId(null);
          useToastStore
            .getState()
            .push({ kind: "success", text: `${tc("export")}: ✓` });
          window.open(status.url, "_blank");
        } else if (status.status === "failed") {
          clearInterval(timer);
          setExportId(null);
          useToastStore
            .getState()
            .push({ kind: "error", text: `${tc("export")}: ✗` });
        }
      } catch {
        clearInterval(timer);
        setExportId(null);
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [exportId, tc]);

  const runExport = async (format: "csv" | "xlsx") => {
    const body = await startExport(format, {
      ...(applied.dateFrom ? { date_from: applied.dateFrom } : {}),
      ...(applied.dateTo ? { date_to: applied.dateTo } : {}),
      ...(applied.status ? { status: applied.status } : {}),
      ...(applied.direction ? { direction: applied.direction } : {}),
    });
    setExportId(body.export_id);
    useToastStore.getState().push({ kind: "info", text: `${tc("export")}…` });
  };

  const columns: Column<CallRow>[] = [
    {
      key: "date",
      header: (
        <button
          type="button"
          onClick={() => setOrdering(ordering === "-date" ? "date" : "-date")}
          className="font-semibold uppercase"
        >
          {t("date")}{" "}
          {ordering?.includes("date") ? (ordering === "-date" ? "↓" : "↑") : ""}
        </button>
      ),
      cell: (row) => (
        <span className="tnum text-xs">
          {new Date(row.start_time).toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      ),
    },
    {
      key: "direction",
      header: t("direction"),
      cell: (row) => <DirectionIcon direction={row.direction} />,
    },
    {
      key: "client",
      header: t("client"),
      cell: (row) =>
        row.counterparty_name ? (
          <span className="block min-w-0">
            <span className="block truncate">{row.counterparty_name}</span>
            <span className="tnum block text-xs text-fg-faint">
              {formatPhone(row.counterparty_number)}
            </span>
          </span>
        ) : (
          <span className="flex items-center gap-1.5">
            <span className="tnum">{formatPhone(row.counterparty_number)}</span>
            <Link
              href={`/cabinet/contacts?fromCall=${row.id}`}
              title={tContacts("createFromCall")}
              className="text-fg-faint hover:text-accent"
            >
              <UserPlus className="size-3.5" />
            </Link>
          </span>
        ),
    },
    {
      key: "operator",
      header: t("operator"),
      cell: (row) => (
        <span className="block min-w-0">
          <span className="block truncate">{row.operator_name ?? "—"}</span>
          {row.operator_number && (
            <span className="tnum block text-xs text-fg-faint">
              {formatPhone(row.operator_number)}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "status",
      header: t("status"),
      cell: (row) => (
        <span
          className={
            row.status === "answered"
              ? "rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent"
              : "rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger"
          }
        >
          {row.status === "answered" ? t("answered") : t("missed")}
        </span>
      ),
    },
    {
      key: "duration",
      header: (
        <button
          type="button"
          data-testid="sort-duration"
          onClick={() =>
            setOrdering(ordering === "-duration" ? "duration" : "-duration")
          }
          className="font-semibold uppercase"
        >
          {t("duration")}{" "}
          {ordering?.includes("duration")
            ? ordering === "-duration"
              ? "↓"
              : "↑"
            : ""}
        </button>
      ),
      numeric: true,
      cell: (row) => formatDuration(row.duration),
    },
    {
      key: "audio",
      header: "▶",
      cell: (row) =>
        row.status === "answered" ? <CallAudioButton callId={row.id} /> : null,
    },
  ];

  const total = data?.count ?? 0;
  const start = total === 0 ? 0 : (page - 1) * 30 + 1;
  const end = Math.min(page * 30, total);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{tNav("calls")}</h1>
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={() => runExport("csv")}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-surface-2"
          >
            <Download className="size-3.5" /> CSV
          </button>
          <button
            type="button"
            onClick={() => runExport("xlsx")}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-surface-2"
          >
            <Download className="size-3.5" /> XLSX
          </button>
        </div>
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
        <FilterSelect
          label={t("direction")}
          value={draftDirection}
          onChange={setDraftDirection}
          options={[
            { value: "", label: t("direction") },
            { value: "inbound", label: t("inbound") },
            { value: "outbound", label: t("outbound") },
          ]}
        />
        <FilterSelect
          label={t("status")}
          value={draftStatus}
          onChange={setDraftStatus}
          options={[
            { value: "", label: t("status") },
            { value: "answered", label: t("answered") },
            { value: "no_answer", label: t("missed") },
          ]}
        />
        <input
          type="number"
          min={0}
          value={draftMinDuration}
          onChange={(event) => setDraftMinDuration(event.target.value)}
          placeholder={`${t("duration")} ≥`}
          className="w-28 rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        />
        <FilterSelect
          label="SIM"
          value={draftSim}
          onChange={setDraftSim}
          options={[
            { value: "", label: "SIM" },
            { value: "0", label: "SIM 1" },
            { value: "1", label: "SIM 2" },
          ]}
        />
        <button
          type="button"
          data-testid="apply-filters"
          onClick={apply}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg hover:opacity-90"
        >
          {tc("apply")}
        </button>
      </FilterBar>

      <DataTable<CallRow>
        columns={columns}
        rows={data?.results ?? []}
        loading={isPending}
        storageKey="calls"
      />

      {/* Pagination: «1—30 из N» */}
      <div className="mt-3 flex items-center justify-between text-sm text-fg-muted">
        <span className="tnum" data-testid="pagination-info">
          {start}—{end} {tc("of")} {total}
        </span>
        <div className="flex gap-1.5">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((value) => value - 1)}
            className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
          >
            ←
          </button>
          <button
            type="button"
            disabled={data ? page >= data.pages : true}
            onClick={() => setPage((value) => value + 1)}
            className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
          >
            →
          </button>
        </div>
      </div>
    </div>
  );
}

export default function CallsPage() {
  return (
    <Suspense>
      <CallsInner />
    </Suspense>
  );
}
