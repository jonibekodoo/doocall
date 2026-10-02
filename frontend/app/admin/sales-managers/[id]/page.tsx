"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ImageIcon, KeyRound, Pencil } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Pagination, usePagination } from "@/components/ui/Pagination";
import { useToastStore } from "@/components/ui/Toast";
import {
  fetchSalesManager,
  resetSalesManagerPassword,
  updateSalesManager,
  uploadSalesManagerLogo,
} from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";
import { useAuth } from "@/lib/auth";

const EDIT_FIELDS = [
  "name",
  "company_name",
  "email",
  "phone",
  "commission_percent",
  "bank_card",
  "bank_mfo",
  "bank_inn",
  "bank_transit",
] as const;

export default function AdminSalesManagerDetailPage() {
  const t = useTranslations("admin");
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isSuper = user?.role === "superadmin";
  const [edit, setEdit] = useState<Record<string, string> | null>(null);
  const [pwOpen, setPwOpen] = useState(false);
  const [pw, setPw] = useState("");

  const { data, isPending } = useQuery({
    queryKey: ["a-sales-manager", id],
    queryFn: () => fetchSalesManager(id),
    enabled: Number.isFinite(id),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["a-sales-manager", id] });
  // Hooks before the early returns below (React hook rules).
  const integratorsPaged = usePagination(data?.manager.integrator_list ?? []);
  const commissionsPaged = usePagination(data?.manager.commissions ?? []);
  const payoutsPaged = usePagination(data?.manager.payouts ?? []);

  const save = useMutation({
    mutationFn: (body: Record<string, string>) => updateSalesManager(id, body),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["a-sales-managers"] });
      setEdit(null);
      useToastStore.getState().push({ kind: "success", text: t("salesM.saved") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });
  const logo = useMutation({
    mutationFn: (file: File) => uploadSalesManagerLogo(id, file),
    onSuccess: () => {
      invalidate();
      useToastStore.getState().push({ kind: "success", text: t("salesM.saved") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });
  const setStatus = useMutation({
    mutationFn: (status: string) => updateSalesManager(id, { status }),
    onSuccess: invalidate,
  });
  const resetPw = useMutation({
    mutationFn: () => resetSalesManagerPassword(id, pw),
    onSuccess: () => {
      setPwOpen(false);
      setPw("");
      useToastStore.getState().push({ kind: "success", text: t("salesM.passwordSaved") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  if (isPending) return <div className="h-64 animate-pulse rounded-lg bg-surface-2" />;
  if (!data) return null;
  const m = data.manager;

  return (
    <div data-testid="admin-sales-manager-detail">
      <Link href="/admin/sales-managers" className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-accent">
        <ArrowLeft className="size-4" /> {t("salesM.back")}
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <label className="group relative grid size-14 shrink-0 cursor-pointer place-items-center overflow-hidden rounded-xl border border-border bg-surface-2">
            {m.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={m.logo_url} alt="" className="size-full object-contain" />
            ) : (
              <ImageIcon className="size-5 text-fg-faint" />
            )}
            <input
              type="file"
              accept="image/png,image/jpeg,image/svg+xml,image/webp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) logo.mutate(f);
                e.target.value = "";
              }}
            />
          </label>
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold">
              {m.name}
              <button
                type="button"
                onClick={() =>
                  setEdit(Object.fromEntries(EDIT_FIELDS.map((k) => [k, String((m as unknown as Record<string, string>)[k] ?? "")])))
                }
                className="grid size-7 place-items-center rounded-md text-fg-muted hover:bg-surface-2 hover:text-accent"
              >
                <Pencil className="size-4" />
              </button>
            </h1>
            {m.company_name && <p className="text-sm font-medium text-fg-muted">{m.company_name}</p>}
            <p className="mt-1 text-sm text-fg-muted">
              {m.email}
              {m.phone && <> · {m.phone}</>} · {t("salesM.commission")}:{" "}
              <b className="tnum">{m.commission_percent}%</b> · {t("salesM.balance")}:{" "}
              <b className="tnum">{formatUzs(m.balance_uzs)} UZS</b> · {t("salesM.lifetime")}:{" "}
              <b className="tnum">{formatUzs(m.lifetime_commission_uzs)} UZS</b>
            </p>
            {(m.bank_card || m.bank_mfo || m.bank_inn || m.bank_transit) && (
              <p className="tnum mt-1 text-xs text-fg-faint">
                {t("salesM.bank_card")}: {m.bank_card || "—"} · MFO: {m.bank_mfo || "—"} · INN:{" "}
                {m.bank_inn || "—"} · {t("salesM.bank_transit")}: {m.bank_transit || "—"}
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {isSuper && (
            <button
              type="button"
              onClick={() => setPwOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
            >
              <KeyRound className="size-4" /> {t("salesM.resetPassword")}
            </button>
          )}
          <button
            type="button"
            onClick={() => setStatus.mutate(m.status === "active" ? "suspended" : "active")}
            className={
              m.status === "active"
                ? "rounded-md border border-danger/40 px-3 py-1.5 text-sm text-danger"
                : "rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg"
            }
          >
            {m.status === "active" ? t("salesM.suspend") : t("salesM.activate")}
          </button>
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">{t("salesM.integratorsList")}</p>
          <ul className="divide-y divide-border">
            {integratorsPaged.slice.map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
                <Link href={`/admin/integrators/${i.id}`} className="truncate text-accent hover:underline">
                  {i.name}
                </Link>
                <span className="tnum text-xs text-fg-faint">{i.companies}</span>
              </li>
            ))}
            {m.integrator_list.length === 0 && <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>}
          </ul>
          <Pagination
            className="border-t border-border px-4 py-2"
            page={integratorsPaged.page}
            pages={integratorsPaged.pages}
            total={integratorsPaged.total}
            start={integratorsPaged.start}
            end={integratorsPaged.end}
            onPage={integratorsPaged.setPage}
          />
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">{t("salesM.commissions")}</p>
          <ul className="divide-y divide-border">
            {commissionsPaged.slice.map((c) => (
              <li key={c.id} className="flex items-center gap-2 px-4 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate text-xs">{c.company}</span>
                <span className="tnum">{formatUzs(c.amount_uzs)}</span>
                <span className="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px]">
                  {t(`integratorDetail.acc_${c.status}` as "integratorDetail.acc_accrued")}
                </span>
              </li>
            ))}
            {m.commissions.length === 0 && <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>}
          </ul>
          <Pagination
            className="border-t border-border px-4 py-2"
            page={commissionsPaged.page}
            pages={commissionsPaged.pages}
            total={commissionsPaged.total}
            start={commissionsPaged.start}
            end={commissionsPaged.end}
            onPage={commissionsPaged.setPage}
          />
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">{t("salesM.payouts")}</p>
          <ul className="divide-y divide-border">
            {payoutsPaged.slice.map((p) => (
              <li key={p.id} className="flex items-center gap-2 px-4 py-2 text-sm">
                <span className="tnum flex-1">{formatUzs(p.amount_uzs)} UZS</span>
                <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">
                  {t(`salesM.payout_${p.status}` as "salesM.payout_pending")}
                </span>
              </li>
            ))}
            {m.payouts.length === 0 && <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>}
          </ul>
          <Pagination
            className="border-t border-border px-4 py-2"
            page={payoutsPaged.page}
            pages={payoutsPaged.pages}
            total={payoutsPaged.total}
            start={payoutsPaged.start}
            end={payoutsPaged.end}
            onPage={payoutsPaged.setPage}
          />
        </section>
      </div>

      {edit && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4" role="dialog">
          <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
            <h2 className="mb-3 text-base font-semibold">{t("salesM.editTitle")}</h2>
            <div className="max-h-[60vh] space-y-2 overflow-y-auto">
              {EDIT_FIELDS.map((k) => (
                <label key={k} className="block text-sm">
                  <span className="mb-1 block text-xs text-fg-muted">{t(`salesM.${k}`)}</span>
                  <input
                    value={edit[k] ?? ""}
                    onChange={(e) => setEdit((f) => ({ ...(f ?? {}), [k]: e.target.value }))}
                    className="w-full rounded-md border border-border bg-surface px-3 py-2"
                  />
                </label>
              ))}
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" onClick={() => setEdit(null)} className="rounded-md border border-border px-3 py-1.5 text-sm">
                {t("common.cancel")}
              </button>
              <button
                type="button"
                onClick={() => save.mutate(edit)}
                className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg"
              >
                {t("salesM.save")}
              </button>
            </div>
          </div>
        </div>
      )}

      {pwOpen && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4" role="dialog">
          <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
            <h2 className="mb-3 text-base font-semibold">{t("salesM.resetPassword")}</h2>
            <input
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              autoComplete="off"
              className="w-full rounded-md border border-border bg-surface px-3 py-2 font-mono"
            />
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" onClick={() => setPwOpen(false)} className="rounded-md border border-border px-3 py-1.5 text-sm">
                {t("common.cancel")}
              </button>
              <button
                type="button"
                disabled={pw.length < 8}
                onClick={() => resetPw.mutate()}
                className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
              >
                {t("salesM.save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
