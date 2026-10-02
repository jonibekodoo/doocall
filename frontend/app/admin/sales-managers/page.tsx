"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { Pagination, usePagination } from "@/components/ui/Pagination";
import { useToastStore } from "@/components/ui/Toast";
import {
  createSalesManager,
  fetchSalesManagerStats,
  fetchSalesManagers,
} from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";

const MEDALS = ["🥇", "🥈", "🥉"];

function CreateDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const t = useTranslations("admin");
  const [form, setForm] = useState({ name: "", email: "", phone: "", password: "", commission_percent: "" });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const valid = form.name.trim() && form.email.includes("@") && form.password.length >= 8;
  const create = useMutation({
    mutationFn: () =>
      createSalesManager({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone: form.phone,
        commission_percent: form.commission_percent || "0",
      }),
    onSuccess: () => {
      useToastStore.getState().push({ kind: "success", text: t("salesM.created") });
      onCreated();
      onClose();
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4" role="dialog">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">{t("salesM.newTitle")}</h2>
        {(["name", "email", "phone", "password"] as const).map((k) => (
          <label key={k} className="mb-2 block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">{t(`salesM.${k}`)}</span>
            <input
              type={k === "password" ? "password" : "text"}
              value={form[k]}
              onChange={set(k)}
              className="w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
        ))}
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">{t("salesM.commission")}</span>
          <input
            type="number"
            step="0.5"
            value={form.commission_percent}
            onChange={set("commission_percent")}
            placeholder="10"
            className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
          />
        </label>
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-border px-3 py-1.5 text-sm">
            {t("common.cancel")}
          </button>
          <button
            type="button"
            disabled={!valid || create.isPending}
            onClick={() => create.mutate()}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
          >
            {t("common.create")}
          </button>
        </div>
      </div>
    </div>
  );
}

function Leaderboard() {
  const t = useTranslations("admin");
  const { data } = useQuery({ queryKey: ["a-sales-stats"], queryFn: fetchSalesManagerStats });
  if (!data || data.managers.length === 0) return null;
  const top = [...data.managers].sort((a, b) => b.commission_uzs - a.commission_uzs).slice(0, 5);
  const max = Math.max(1, ...top.map((r) => r.commission_uzs));
  return (
    <div className="mb-5 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <p className="text-xs font-medium uppercase text-fg-faint">{t("salesM.total")}</p>
          <p className="tnum mt-1 text-xl font-bold">{data.totals.managers}</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <p className="text-xs font-medium uppercase text-fg-faint">{t("salesM.integrators")}</p>
          <p className="tnum mt-1 text-xl font-bold">{data.totals.integrators}</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <p className="text-xs font-medium uppercase text-fg-faint">{t("salesM.revenue")}</p>
          <p className="tnum mt-1 text-xl font-bold">{formatUzs(data.totals.revenue_uzs)} UZS</p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <p className="text-xs font-medium uppercase text-fg-faint">{t("salesM.commissionPaid")}</p>
          <p className="tnum mt-1 text-xl font-bold">{formatUzs(data.totals.commission_uzs)} UZS</p>
        </div>
      </div>
      <section className="rounded-xl border border-border bg-surface shadow-sm">
        <header className="border-b border-border px-4 py-2.5 text-sm font-semibold">{t("salesM.topByCommission")}</header>
        <ul className="space-y-3 p-4">
          {top.map((r, i) => (
            <li key={r.id} className="flex items-center gap-3">
              <span className="w-5 text-center text-sm">{i < 3 ? MEDALS[i] : <span className="text-fg-faint">{i + 1}</span>}</span>
              <Link href={`/admin/sales-managers/${r.id}`} className="w-28 shrink-0 truncate text-sm font-medium text-accent hover:underline">
                {r.name}
              </Link>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <div className="h-full rounded-full bg-accent" style={{ width: `${(r.commission_uzs / max) * 100}%` }} />
              </div>
              <span className="tnum w-24 shrink-0 text-right text-sm font-semibold">{formatUzs(r.commission_uzs)}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default function AdminSalesManagersPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({ queryKey: ["a-sales-managers"], queryFn: fetchSalesManagers });
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");

  // Small, fully loaded list — filter client-side, instantly.
  const needle = q.trim().toLowerCase();
  const rows = (data?.managers ?? []).filter(
    (m) =>
      (!status || m.status === status) &&
      (!needle ||
        [m.name, m.company_name, m.email, m.phone]
          .filter(Boolean)
          .some((v) => v.toLowerCase().includes(needle))),
  );
  const paged = usePagination(rows);

  return (
    <div data-testid="admin-sales-managers">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("salesM.title")}</h1>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-fg"
        >
          {t("salesM.new")}
        </button>
      </div>

      <Leaderboard />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            paged.reset();
          }}
          placeholder={t("salesM.searchPlaceholder")}
          data-testid="sales-managers-search"
          className="w-72 rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            paged.reset();
          }}
          aria-label={t("common.status")}
          className="rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        >
          <option value="">{t("common.allStatuses")}</option>
          <option value="active">{t("integratorDetail.st_active")}</option>
          <option value="suspended">{t("integratorDetail.st_suspended")}</option>
        </select>
        {!isPending && (needle || status) && (
          <span className="tnum text-xs text-fg-muted">
            {rows.length} / {data?.managers.length ?? 0}
          </span>
        )}
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">№</th>
              <th className="px-3 py-2 text-left">{t("salesM.name")}</th>
              <th className="px-3 py-2 text-right">{t("salesM.commission")}</th>
              <th className="px-3 py-2 text-right">{t("salesM.integrators")}</th>
              <th className="px-3 py-2 text-right">{t("salesM.balance")}</th>
              <th className="px-3 py-2 text-left">{t("common.status")}</th>
            </tr>
          </thead>
          <tbody>
            {isPending
              ? Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={6} className="px-3 py-2.5">
                      <div className="h-3.5 animate-pulse rounded bg-surface-3" />
                    </td>
                  </tr>
                ))
              : paged.slice.map((m, index) => (
                  <tr key={m.id} className="border-t border-border hover:bg-surface-2/60">
                    <td className="px-3 py-2.5 text-fg-faint">{paged.start + index}</td>
                    <td className="px-3 py-2.5">
                      <Link href={`/admin/sales-managers/${m.id}`} className="font-medium text-accent hover:underline">
                        {m.name}
                      </Link>
                      <span className="ml-1.5 text-xs text-fg-faint">{m.email}</span>
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">{m.commission_percent}%</td>
                    <td className="tnum px-3 py-2.5 text-right">{m.integrators}</td>
                    <td className="tnum px-3 py-2.5 text-right">{formatUzs(m.balance_uzs)}</td>
                    <td className="px-3 py-2.5 text-xs">
                      {t(`integratorDetail.st_${m.status}` as "integratorDetail.st_active")}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
        {!isPending && rows.length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-fg-faint">
            {needle || status ? t("common.nothingFound") : t("salesM.empty")}
          </p>
        )}
        <Pagination
          className="border-t border-border px-3 py-2"
          page={paged.page}
          pages={paged.pages}
          total={paged.total}
          start={paged.start}
          end={paged.end}
          onPage={paged.setPage}
        />
      </div>

      {open && (
        <CreateDialog
          onClose={() => setOpen(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["a-sales-managers"] });
            queryClient.invalidateQueries({ queryKey: ["a-sales-stats"] });
          }}
        />
      )}
    </div>
  );
}
