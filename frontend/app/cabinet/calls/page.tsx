"use client";

/** §6.2 Звонки — full filter bar, paginated table, audio, export.
 * Call records are immutable — no delete anywhere. */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download, FilterX, UserPlus, X } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { CallAiBadge } from "@/app/cabinet/ai/ai-shared";
import { AudioPlayer } from "@/components/AudioPlayer";
import { CallStatusBadge, DirectionIcon } from "@/components/calls-shared";
import { RemoteDialButton } from "@/components/RemoteDialButton";
import { CallAudioButton } from "@/components/CallAudioButton";
import { CallMapButton } from "@/components/CallMapButton";
import { DataTable, type Column } from "@/components/ui/DataTable";
import {
  DateRangePicker,
  type DateRange,
} from "@/components/ui/DateRangePicker";
import { FilterBar, FilterSelect } from "@/components/ui/FilterBar";
import { Pagination } from "@/components/ui/Pagination";
import { useToastStore } from "@/components/ui/Toast";
import {
  fetchCallDetail,
  fetchCalls,
  fetchExport,
  fetchPerEmployee,
  startExport,
} from "@/lib/api/endpoints";
import type { CallRow } from "@/lib/api/types";
import { buildCallsQuery, type CallFilters } from "@/lib/filters";
import { formatDuration, formatPhone } from "@/lib/format";

const CRM_LABEL: Record<string, string> = {
  amocrm: "amoCRM",
  bitrix24: "Bitrix24",
  odoo: "Odoo",
};

function daysAgoIso(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

/** Live filter controls (strings, as the inputs hold them). */
interface LiveFilters {
  from: string;
  to: string;
  employee: string;
  direction: string;
  status: string;
  minDuration: string;
  sim: string;
  search: string;
}

/** Default view: last 30 days, everything else unfiltered. */
function defaultFilters(): LiveFilters {
  return {
    from: daysAgoIso(30),
    to: daysAgoIso(0),
    employee: "",
    direction: "",
    status: "",
    minDuration: "",
    sim: "",
    search: "",
  };
}

/** URL query key for each filter (same names as the API). */
const URL_KEYS: Record<keyof LiveFilters, string> = {
  from: "date_from",
  to: "date_to",
  employee: "employees",
  direction: "direction",
  status: "status",
  minDuration: "min_duration",
  sim: "sim_slot",
  search: "search",
};

/** Filters from the URL; a key that is present (even empty) wins over the
 * default — "date_from=" means "no lower bound". */
function filtersFromUrl(params: URLSearchParams): LiveFilters {
  const result = defaultFilters();
  for (const key of Object.keys(URL_KEYS) as (keyof LiveFilters)[]) {
    const value = params.get(URL_KEYS[key]);
    if (value !== null) result[key] = value;
  }
  return result;
}

function sameFilters(a: LiveFilters, b: LiveFilters): boolean {
  return (Object.keys(URL_KEYS) as (keyof LiveFilters)[]).every(
    (key) => a[key] === b[key],
  );
}

/** Live controls → API filter model (invalid numbers are ignored). */
function toCallFilters(live: LiveFilters): CallFilters {
  const minDuration = Number(live.minDuration);
  return {
    dateFrom: live.from || undefined,
    dateTo: live.to || undefined,
    direction: (live.direction || undefined) as CallFilters["direction"],
    status: (live.status || undefined) as CallFilters["status"],
    search: live.search.trim() || undefined,
    minDuration:
      live.minDuration && Number.isFinite(minDuration) && minDuration > 0
        ? minDuration
        : undefined,
    simSlot: live.sim === "" ? undefined : Number(live.sim),
    employees: live.employee ? [Number(live.employee)] : undefined,
  };
}

const SEARCH_DEBOUNCE_MS = 400;

/** Deep link: /cabinet/calls?call=<id> opens that call in a side drawer. The
 * call is always fetched by id, so it works whatever the current page or
 * filters are (and yields our own presigned audio URL). */
function CallDrawer({
  callId,
  onClose,
}: {
  callId: number;
  onClose: () => void;
}) {
  const t = useTranslations("calls");
  const { data, isPending, isError } = useQuery({
    queryKey: ["call-detail", callId],
    queryFn: () => fetchCallDetail(callId),
  });
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const call = data?.call;
  const audio = call?.audios.find((item) => item.kind === "primary");
  const rows: Array<[string, React.ReactNode]> = call
    ? [
        [
          t("date"),
          new Date(call.start_time).toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          }),
        ],
        [
          t("direction"),
          <span key="d" className="inline-flex items-center gap-1.5">
            <DirectionIcon direction={call.direction} />
            {call.direction === "inbound" ? t("inbound") : t("outbound")}
          </span>,
        ],
        [
          t("client"),
          <span key="c">
            {call.counterparty_name && (
              <span className="block">{call.counterparty_name}</span>
            )}
            <span className="flex items-center gap-1.5">
              <span className="tnum">
                {formatPhone(call.counterparty_number)}
              </span>
              <RemoteDialButton number={call.counterparty_number} />
            </span>
          </span>,
        ],
        [t("operator"), call.operator_name ?? "—"],
        [
          t("status"),
          <CallStatusBadge
            key="s"
            status={call.status}
            direction={call.direction}
          />,
        ],
        [
          t("duration"),
          <span key="u" className="tnum">
            {formatDuration(call.duration)}
          </span>,
        ],
      ]
    : [];

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end"
      data-testid="call-drawer"
    >
      <button
        type="button"
        aria-label={t("close")}
        onClick={onClose}
        className="absolute inset-0 bg-black/30"
      />
      <aside
        role="dialog"
        aria-label={t("detailTitle")}
        className="relative flex h-full w-full max-w-md flex-col gap-4 overflow-y-auto border-l border-border bg-surface p-5 shadow-xl"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{t("detailTitle")}</h2>
          <button
            type="button"
            data-testid="call-drawer-close"
            aria-label={t("close")}
            onClick={onClose}
            className="grid size-8 place-items-center rounded-md hover:bg-surface-2"
          >
            <X className="size-4" />
          </button>
        </div>
        {isPending && (
          <div className="h-40 animate-pulse rounded-lg bg-surface-3" />
        )}
        {(isError || (!isPending && !call)) && (
          <p className="text-sm text-fg-muted">{t("notFound")}</p>
        )}
        {call && (
          <>
            <dl className="space-y-2 text-sm">
              {rows.map(([label, value]) => (
                <div key={label} className="flex gap-3">
                  <dt className="w-28 shrink-0 text-fg-muted">{label}</dt>
                  <dd className="min-w-0 flex-1">{value}</dd>
                </div>
              ))}
            </dl>
            {audio && (
              <div data-testid="call-drawer-audio">
                <AudioPlayer src={audio.url} />
              </div>
            )}
            {call.ai && (
              <div className="flex items-center gap-2 text-sm">
                <CallAiBadge
                  analysisId={call.ai.analysis_id}
                  score={call.ai.final_score}
                  title={t("aiScore")}
                />
              </div>
            )}
          </>
        )}
      </aside>
    </div>
  );
}

function CallsInner() {
  const tNav = useTranslations("nav");
  const t = useTranslations("calls");
  const tc = useTranslations("common");
  const tContacts = useTranslations("contacts");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const deepLinkId = Number(params.get("call"));
  const openCallId =
    Number.isInteger(deepLinkId) && deepLinkId > 0 ? deepLinkId : null;
  const closeCall = useCallback(() => {
    const next = new URLSearchParams(params.toString());
    next.delete("call");
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, {
      scroll: false,
    });
  }, [params, pathname, router]);

  // Live filters (§6.2, default 30 days): every control applies at once,
  // the search box after a short pause (or Enter). Mirrored in the URL.
  const [live, setLive] = useState<LiveFilters>(() => filtersFromUrl(params));
  const [searchInput, setSearchInput] = useState(live.search);
  const [page, setPage] = useState(1);
  const [ordering, setOrdering] = useState<CallFilters["ordering"]>("-date");

  const writeUrl = useCallback(
    (next: LiveFilters) => {
      const query = new URLSearchParams(params.toString());
      const defaults = defaultFilters();
      for (const key of Object.keys(URL_KEYS) as (keyof LiveFilters)[]) {
        if (next[key] === defaults[key]) query.delete(URL_KEYS[key]);
        else query.set(URL_KEYS[key], next[key]);
      }
      const text = query.toString();
      router.replace(text ? `${pathname}?${text}` : pathname, {
        scroll: false,
      });
    },
    [params, pathname, router],
  );

  // Latest filters for the stable `update` below (keeps the debounce timer
  // from restarting on unrelated re-renders).
  const liveRef = useRef(live);
  liveRef.current = live;
  const update = useCallback(
    (patch: Partial<LiveFilters>) => {
      const next = { ...liveRef.current, ...patch };
      if (sameFilters(liveRef.current, next)) return;
      liveRef.current = next;
      setLive(next);
      setPage(1);
      writeUrl(next);
    },
    [writeUrl],
  );

  // Debounced search: one request after typing stops, none per keystroke.
  useEffect(() => {
    if (searchInput === live.search) return;
    const timer = setTimeout(
      () => update({ search: searchInput }),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [searchInput, live.search, update]);

  const atDefaults = sameFilters(live, defaultFilters()) && searchInput === "";
  const clearFilters = () => {
    setSearchInput("");
    update(defaultFilters());
  };

  const { data: employees } = useQuery({
    queryKey: ["per-employee-list"],
    queryFn: () => fetchPerEmployee(),
    staleTime: 300_000,
  });

  const filters: CallFilters = { ...toCallFilters(live), page, ordering };
  const { data, isPending } = useQuery({
    queryKey: ["calls", filters],
    queryFn: () => fetchCalls(filters),
    // Keep the current rows on screen while the next filter loads.
    placeholderData: keepPreviousData,
  });

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
    // Exactly the live list filters (incl. a search still being typed).
    const current = { ...live, search: searchInput };
    if (searchInput !== live.search) update({ search: searchInput });
    const body = await startExport(
      format,
      Object.fromEntries(
        new URLSearchParams(buildCallsQuery(toCallFilters(current))),
      ),
    );
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
            <span className="flex items-center gap-1 text-xs text-fg-faint">
              <span className="tnum">
                {formatPhone(row.counterparty_number)}
              </span>
              <RemoteDialButton number={row.counterparty_number} />
            </span>
          </span>
        ) : (
          <span className="flex items-center gap-1.5">
            <span className="tnum">{formatPhone(row.counterparty_number)}</span>
            <RemoteDialButton number={row.counterparty_number} />
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
        <CallStatusBadge status={row.status} direction={row.direction} />
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
      cell: (row) => (
        <div className="flex items-center gap-1.5">
          {row.status === "answered" && <CallAudioButton callId={row.id} />}
          {row.has_location && <CallMapButton callId={row.id} />}
          {row.crm.map((mark) => (
            <span
              key={mark.provider}
              data-testid={`crm-mark-${mark.provider}`}
              title={`${CRM_LABEL[mark.provider] ?? mark.provider} · ${
                mark.status === "ok" ? t("crmSent") : `${t("crmFailed")}: ${mark.error}`
              } · ${mark.at.slice(0, 16).replace("T", " ")}`}
              className={
                mark.status === "ok"
                  ? "rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent"
                  : "rounded bg-danger/10 px-1.5 py-0.5 text-[10px] font-semibold text-danger"
              }
            >
              {CRM_LABEL[mark.provider] ?? mark.provider} {mark.status === "ok" ? "✓" : "✗"}
            </span>
          ))}
          {row.ai && (
            <CallAiBadge
              analysisId={row.ai.analysis_id}
              score={row.ai.final_score}
              title={t("aiScore")}
            />
          )}
        </div>
      ),
    },
  ];

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

      <div
        onKeyDown={(event) => {
          // Enter in the search box searches right away (skips the pause).
          const target = event.target as HTMLInputElement;
          if (event.key === "Enter" && target.type === "search") {
            update({ search: searchInput });
          }
        }}
      >
        <FilterBar search={searchInput} onSearch={setSearchInput}>
          <FilterSelect
            label={t("operator")}
            value={live.employee}
            onChange={(value) => update({ employee: value })}
            options={[
              { value: "", label: t("operator") },
              ...(employees?.report ?? []).map((emp) => ({
                value: String(emp.operator_id),
                label: emp.full_name || emp.user_name,
              })),
            ]}
          />
          <DateRangePicker
            value={{ from: live.from, to: live.to }}
            onChange={(range: DateRange) =>
              update({ from: range.from, to: range.to })
            }
          />
          <FilterSelect
            label={t("direction")}
            value={live.direction}
            onChange={(value) => update({ direction: value })}
            options={[
              { value: "", label: t("direction") },
              { value: "inbound", label: t("inbound") },
              { value: "outbound", label: t("outbound") },
            ]}
          />
          <FilterSelect
            label={t("status")}
            value={live.status}
            onChange={(value) => update({ status: value })}
            options={[
              { value: "", label: t("status") },
              { value: "answered", label: t("answered") },
              { value: "missed", label: t("statusMissedIn") },
              { value: "not_reached", label: t("statusNotReachedOut") },
              { value: "no_answer", label: t("statusAllUnanswered") },
            ]}
          />
          <input
            type="number"
            min={0}
            value={live.minDuration}
            onChange={(event) => update({ minDuration: event.target.value })}
            placeholder={`${t("duration")} ≥`}
            aria-label={`${t("duration")} ≥`}
            data-testid="filter-min-duration"
            className="w-28 rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
          />
          <FilterSelect
            label="SIM"
            value={live.sim}
            onChange={(value) => update({ sim: value })}
            options={[
              { value: "", label: "SIM" },
              { value: "0", label: "SIM 1" },
              { value: "1", label: "SIM 2" },
            ]}
          />
          {!atDefaults && (
            <button
              type="button"
              data-testid="clear-filters"
              onClick={clearFilters}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm text-fg-muted hover:bg-surface-2 hover:text-fg"
            >
              <FilterX className="size-4" /> {t("clearFilters")}
            </button>
          )}
        </FilterBar>
      </div>

      <DataTable<CallRow>
        columns={columns}
        rows={data?.results ?? []}
        loading={isPending}
        storageKey="calls"
      />

      {/* Server-paged: 20 per page (backend PAGE_SIZE) */}
      <Pagination
        page={page}
        pages={data?.pages ?? 1}
        total={data?.count ?? 0}
        pageSize={data?.page_size ?? 20}
        onPage={setPage}
      />

      {openCallId !== null && (
        <CallDrawer callId={openCallId} onClose={closeCall} />
      )}
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
