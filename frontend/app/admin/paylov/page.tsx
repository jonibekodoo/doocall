"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  Search,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { confirmDialog } from "@/components/ui/Confirm";
import { Pagination, usePagination } from "@/components/ui/Pagination";
import { useToastStore } from "@/components/ui/Toast";
import {
  fetchPaylovAutoPay,
  fetchPaylovLogs,
  fetchPaylovTransactions,
  paylovTransactionAction,
  type PaylovLogRow,
  type PaylovTransaction,
} from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = {
  pending: "bg-warning/15 text-warning",
  approved: "bg-success/15 text-success",
  rejected: "bg-danger/15 text-danger",
  failed: "bg-danger/15 text-danger",
};

function fmtTime(iso: string): string {
  return iso.slice(0, 19).replace("T", " ");
}

// ── Tiles ──────────────────────────────────────────────────────────────────
function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-xs font-semibold uppercase text-fg-faint">{label}</p>
      <p className={cn("tnum mt-1.5 text-2xl font-bold", tone)}>{value}</p>
    </div>
  );
}

// ── Transactions tab ─────────────────────────────────────────────────────────
function TransactionsTab() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (status) params.set("status", status);
  const query = params.toString() ? `?${params}` : "";

  const { data } = useQuery({
    queryKey: ["a-paylov-tx", query],
    queryFn: () => fetchPaylovTransactions(query),
  });
  const paged = usePagination(data?.transactions ?? []);
  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "refund" | "cancel" }) =>
      paylovTransactionAction(id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-paylov-tx"] });
      useToastStore.getState().push({ kind: "success", text: t("paylov.actionDone") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  const run = async (row: PaylovTransaction, action: "refund" | "cancel") => {
    if (await confirmDialog(t(`paylov.confirm_${action}`), { danger: true }))
      act.mutate({ id: row.id, action });
  };

  return (
    <div>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label={t("paylov.txCount")} value={String(data?.total_count ?? 0)} />
        <Tile label={t("paylov.txSum")} value={`${formatUzs(data?.total_uzs ?? 0)}`} />
        <Tile
          label={t("paylov.approvedCount")}
          value={String(data?.approved_count ?? 0)}
          tone="text-success"
        />
        <Tile
          label={t("paylov.approvedSum")}
          value={`${formatUzs(data?.approved_uzs ?? 0)}`}
          tone="text-success"
        />
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-faint" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              paged.reset();
            }}
            placeholder={t("paylov.searchPlaceholder")}
            className="w-64 rounded-md border border-border bg-surface py-1.5 pl-8 pr-3 text-sm"
          />
        </div>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            paged.reset();
          }}
          className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm"
        >
          <option value="">{t("paylov.allStatuses")}</option>
          <option value="pending">pending</option>
          <option value="approved">approved</option>
          <option value="rejected">rejected</option>
          <option value="failed">failed</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-surface-2 text-left text-xs uppercase text-fg-faint">
            <tr>
              <th className="px-3 py-2">№</th>
              <th className="px-3 py-2">{t("paylov.company")}</th>
              <th className="px-3 py-2 text-right">{t("paylov.amount")}</th>
              <th className="px-3 py-2">{t("paylov.status")}</th>
              <th className="px-3 py-2">Paylov ID</th>
              <th className="px-3 py-2">{t("paylov.created")}</th>
              <th className="px-3 py-2 text-right">{t("paylov.actions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {paged.slice.map((row, index) => (
              <tr key={row.id} className="hover:bg-surface-2/40">
                <td className="tnum px-3 py-2 text-fg-faint">{paged.start + index}</td>
                <td className="px-3 py-2 font-medium">{row.company}</td>
                <td className="tnum px-3 py-2 text-right">{formatUzs(row.amount_uzs)}</td>
                <td className="px-3 py-2">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                      STATUS_TONE[row.status] ?? "bg-surface-3 text-fg-muted",
                    )}
                  >
                    {row.status}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-fg-muted">
                  {row.external_id || "—"}
                </td>
                <td className="tnum px-3 py-2 text-xs text-fg-muted">{fmtTime(row.created_at)}</td>
                <td className="px-3 py-2">
                  <div className="flex justify-end gap-1.5">
                    {row.status === "pending" && (
                      <button
                        type="button"
                        onClick={() => run(row, "cancel")}
                        className="rounded-md border border-danger/40 px-2 py-1 text-xs text-danger"
                      >
                        {t("paylov.cancel")}
                      </button>
                    )}
                    {row.status === "approved" && (
                      <button
                        type="button"
                        onClick={() => run(row, "refund")}
                        className="rounded-md border border-danger/40 px-2 py-1 text-xs text-danger"
                      >
                        {t("paylov.refund")}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {(data?.transactions ?? []).length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-sm text-fg-faint">
                  —
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
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

// ── Logs tab ─────────────────────────────────────────────────────────────────
function LogRow({ log }: { log: PaylovLogRow }) {
  const [open, setOpen] = useState(false);
  const inbound = log.direction === "in";
  return (
    <div className="rounded-xl border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span
          className={cn(
            "grid size-8 shrink-0 place-items-center rounded-lg",
            inbound ? "bg-accent-soft text-accent" : "bg-warning/15 text-warning",
          )}
        >
          {inbound ? <ArrowDownLeft className="size-4" /> : <ArrowUpRight className="size-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-medium">
            <span className="font-mono">{log.event}</span>
            {log.ok ? (
              <CheckCircle2 className="size-4 text-success" />
            ) : (
              <XCircle className="size-4 text-danger" />
            )}
            {log.http_status != null && (
              <span className="tnum text-xs text-fg-faint">{log.http_status}</span>
            )}
          </p>
          <p className="tnum text-xs text-fg-faint">
            {fmtTime(log.created_at)}
            {log.payment_id != null && ` · #${log.payment_id}`}
            {log.note && ` · ${log.note}`}
          </p>
        </div>
        <ChevronDown className={cn("size-4 text-fg-faint transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="grid gap-3 border-t border-border p-4 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase text-fg-faint">Request</p>
            <pre className="max-h-64 overflow-auto rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed">
              {JSON.stringify(log.request_body, null, 2)}
            </pre>
          </div>
          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase text-fg-faint">Response</p>
            <pre className="max-h-64 overflow-auto rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed">
              {JSON.stringify(log.response_body, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function LogsTab() {
  const t = useTranslations("admin");
  const [direction, setDirection] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const params = new URLSearchParams();
  if (direction) params.set("direction", direction);
  if (errorsOnly) params.set("errors", "1");
  const query = params.toString() ? `?${params}` : "";

  const { data } = useQuery({
    queryKey: ["a-paylov-logs", query],
    queryFn: () => fetchPaylovLogs(query),
  });
  const paged = usePagination(data?.logs ?? []);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select
          value={direction}
          onChange={(e) => {
            setDirection(e.target.value);
            paged.reset();
          }}
          className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm"
        >
          <option value="">{t("paylov.allDirections")}</option>
          <option value="in">{t("paylov.inbound")}</option>
          <option value="out">{t("paylov.outbound")}</option>
        </select>
        <label className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-fg-muted">
          <input
            type="checkbox"
            checked={errorsOnly}
            onChange={(e) => {
              setErrorsOnly(e.target.checked);
              paged.reset();
            }}
            className="accent-accent"
          />
          {t("paylov.errorsOnly")}
        </label>
      </div>
      <div className="space-y-2">
        {paged.slice.map((log) => <LogRow key={log.id} log={log} />)}
        {(data?.logs ?? []).length === 0 && (
          <p className="py-10 text-center text-sm text-fg-faint">—</p>
        )}
      </div>
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

// ── Auto-payments tab ────────────────────────────────────────────────────────
function AutoPayTab() {
  const t = useTranslations("admin");
  const { data } = useQuery({ queryKey: ["a-paylov-autopay"], queryFn: fetchPaylovAutoPay });
  const rows = usePagination(data?.rows ?? []);
  const payments = usePagination(data?.payments ?? []);
  const enabledCount = (data?.rows ?? []).filter((row) => row.is_enabled).length;
  const failedCount = (data?.payments ?? []).filter((row) => row.status === "failed").length;

  return (
    <div data-testid="paylov-autopay-tab">
      {data && !data.platform_enabled && (
        <p className="mb-4 rounded-lg border border-danger/40 bg-danger/5 px-4 py-3 text-sm font-medium text-danger">
          {t("paylov.autopayPlatformOff")}
        </p>
      )}
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label={t("paylov.autopayCompanies")} value={String(data?.rows.length ?? 0)} />
        <Tile label={t("paylov.autopayEnabled")} value={String(enabledCount)} tone="text-success" />
        <Tile label={t("paylov.autopayCharges")} value={String(data?.payments.length ?? 0)} />
        <Tile label={t("paylov.autopayFailed")} value={String(failedCount)} tone="text-danger" />
      </div>

      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[820px] text-sm">
          <thead className="bg-surface-2 text-left text-xs uppercase text-fg-faint">
            <tr>
              <th className="px-3 py-2">№</th>
              <th className="px-3 py-2">{t("paylov.company")}</th>
              <th className="px-3 py-2">{t("paylov.autopayState")}</th>
              <th className="px-3 py-2">{t("paylov.autopayCard")}</th>
              <th className="px-3 py-2 text-right">{t("paylov.amount")}</th>
              <th className="px-3 py-2">{t("paylov.autopayLast")}</th>
              <th className="px-3 py-2 text-right">{t("paylov.autopayStreak")}</th>
              <th className="px-3 py-2">{t("paylov.autopayReason")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.slice.map((row, index) => (
              <tr key={row.company_id} className="hover:bg-surface-2/40">
                <td className="tnum px-3 py-2 text-fg-faint">{rows.start + index}</td>
                <td className="px-3 py-2">
                  <Link
                    href={`/admin/companies/${row.company_id}`}
                    className="font-medium text-accent hover:underline"
                  >
                    {row.company}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                      row.is_enabled ? "bg-success/15 text-success" : "bg-surface-3 text-fg-muted",
                    )}
                  >
                    {row.is_enabled ? t("paylov.autopayOn") : t("paylov.autopayOff")}
                  </span>
                </td>
                <td className="tnum px-3 py-2 text-xs">{row.card ?? "—"}</td>
                <td className="tnum px-3 py-2 text-right">
                  {formatUzs(row.effective_amount_uzs)}
                  <span className="block text-[11px] text-fg-faint">
                    {row.amount_mode === "fixed"
                      ? t("paylov.autopayModeFixed")
                      : t("paylov.autopayModeMonth")}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs">
                  {row.last_attempt_at ? (
                    <span className="tnum" title={row.last_error || undefined}>
                      {fmtTime(row.last_attempt_at)}
                      <span
                        className={cn(
                          "ml-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                          row.last_status === "ok"
                            ? "bg-success/15 text-success"
                            : row.last_status === "failed"
                              ? "bg-danger/15 text-danger"
                              : "bg-warning/15 text-warning",
                        )}
                      >
                        {row.last_status || "—"}
                      </span>
                    </span>
                  ) : (
                    <span className="text-fg-faint">—</span>
                  )}
                </td>
                <td
                  className={cn(
                    "tnum px-3 py-2 text-right",
                    row.fail_streak > 0 ? "font-semibold text-danger" : "text-fg-faint",
                  )}
                >
                  {row.fail_streak}
                </td>
                <td
                  className="max-w-[220px] truncate px-3 py-2 text-xs text-fg-muted"
                  title={row.disabled_reason}
                >
                  {row.disabled_reason || "—"}
                </td>
              </tr>
            ))}
            {(data?.rows ?? []).length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-sm text-fg-faint">
                  —
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Pagination
        page={rows.page}
        pages={rows.pages}
        total={rows.total}
        start={rows.start}
        end={rows.end}
        onPage={rows.setPage}
      />

      <h2 className="mb-2 mt-6 text-sm font-semibold">{t("paylov.autopayChargesTitle")}</h2>
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-surface-2 text-left text-xs uppercase text-fg-faint">
            <tr>
              <th className="px-3 py-2">№</th>
              <th className="px-3 py-2">{t("paylov.company")}</th>
              <th className="px-3 py-2">{t("paylov.autopayCard")}</th>
              <th className="px-3 py-2 text-right">{t("paylov.amount")}</th>
              <th className="px-3 py-2">{t("paylov.status")}</th>
              <th className="px-3 py-2">{t("paylov.created")}</th>
              <th className="px-3 py-2">{t("paylov.autopayError")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {payments.slice.map((row, index) => (
              <tr key={row.id} className="hover:bg-surface-2/40">
                <td className="tnum px-3 py-2 text-fg-faint">{payments.start + index}</td>
                <td className="px-3 py-2">
                  <Link
                    href={`/admin/companies/${row.company_id}`}
                    className="font-medium text-accent hover:underline"
                  >
                    {row.company}
                  </Link>
                </td>
                <td className="tnum px-3 py-2 text-xs">{row.card ?? "—"}</td>
                <td className="tnum px-3 py-2 text-right">{formatUzs(row.amount_uzs)}</td>
                <td className="px-3 py-2">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                      STATUS_TONE[row.status] ?? "bg-surface-3 text-fg-muted",
                    )}
                  >
                    {row.status}
                  </span>
                </td>
                <td className="tnum px-3 py-2 text-xs text-fg-muted">{fmtTime(row.created_at)}</td>
                <td
                  className="max-w-[240px] truncate px-3 py-2 text-xs text-danger"
                  title={row.error}
                >
                  {row.error || "—"}
                </td>
              </tr>
            ))}
            {(data?.payments ?? []).length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-sm text-fg-faint">
                  —
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Pagination
        page={payments.page}
        pages={payments.pages}
        total={payments.total}
        start={payments.start}
        end={payments.end}
        onPage={payments.setPage}
      />
    </div>
  );
}

export default function AdminPaylovPage() {
  const t = useTranslations("admin");
  const [tab, setTab] = useState<"tx" | "autopay" | "logs">("tx");

  return (
    <div data-testid="admin-paylov">
      <h1 className="mb-4 text-xl font-semibold">{t("paylov.title")}</h1>
      <div className="mb-4 inline-flex rounded-lg border border-border bg-surface p-1">
        {(["tx", "autopay", "logs"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
              tab === key ? "bg-accent text-accent-fg" : "text-fg-muted hover:text-fg",
            )}
          >
            {t(`paylov.tab_${key}`)}
          </button>
        ))}
      </div>
      {tab === "tx" ? <TransactionsTab /> : tab === "autopay" ? <AutoPayTab /> : <LogsTab />}
    </div>
  );
}
