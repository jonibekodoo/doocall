"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import { createSalesIntegrator, fetchSalesIntegrators } from "@/lib/api/sales";
import { cn } from "@/lib/utils";

const STATUS_COLORS: Record<string, string> = {
  active: "var(--accent)",
  trial: "var(--warning)",
  expired: "var(--danger-500)",
  suspended: "var(--fg-faint)",
};

function CreateDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const t = useTranslations("sales");
  const [form, setForm] = useState({ name: "", company_name: "", email: "", phone: "", password: "" });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const valid = form.name.trim() && form.email.includes("@") && form.password.length >= 8;
  const create = useMutation({
    mutationFn: () => createSalesIntegrator({ name: form.name.trim(), company_name: form.company_name.trim(), email: form.email.trim(), phone: form.phone, password: form.password }),
    onSuccess: (body) => {
      useToastStore.getState().push({ kind: "success", text: t("integratorCreated", { code: body.integrator.referral_code }) });
      onCreated();
      onClose();
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });
  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4" role="dialog">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">{t("newIntegrator")}</h2>
        {(["name", "company_name", "email", "phone", "password"] as const).map((k) => (
          <label key={k} className="mb-2 block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">{t(`int_${k}`)}</span>
            <input type={k === "password" ? "password" : "text"} value={form[k]} onChange={set(k)} className="w-full rounded-md border border-border bg-surface px-3 py-2" />
          </label>
        ))}
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-border px-3 py-1.5 text-sm">{t("cancel")}</button>
          <button type="button" disabled={!valid || create.isPending} onClick={() => create.mutate()} className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40">{t("create")}</button>
        </div>
      </div>
    </div>
  );
}

export default function SalesIntegratorsPage() {
  const t = useTranslations("sales");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const { data, isPending } = useQuery({ queryKey: ["sales-integrators"], queryFn: fetchSalesIntegrators });
  const rows = data?.integrators ?? [];

  return (
    <div data-testid="sales-integrators">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("integrators")}</h1>
        <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-fg"><Plus className="size-4" /> {t("newIntegrator")}</button>
      </div>
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">{t("integrator")}</th>
              <th className="px-3 py-2 text-right">{t("companies")}</th>
              <th className="px-3 py-2 text-right">{t("companyStatus")}</th>
              <th className="px-3 py-2 text-left">{t("status")}</th>
            </tr>
          </thead>
          <tbody>
            {isPending ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i}><td colSpan={4} className="px-3 py-2.5"><div className="h-3.5 animate-pulse rounded bg-surface-3" /></td></tr>
              ))
            ) : rows.length === 0 ? (
              <tr><td colSpan={4} className="px-4 py-10 text-center text-sm text-fg-faint">{t("noIntegrators")}</td></tr>
            ) : (
              rows.map((r) => {
                const cs = r.company_status;
                const total = cs.active + cs.trial + cs.expired + cs.suspended;
                return (
                  <tr key={r.id} className="border-t border-border hover:bg-surface-2/60">
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2.5">
                        <span className="grid size-8 shrink-0 place-items-center overflow-hidden rounded-md border border-border bg-surface-2 text-xs font-bold text-fg-muted">
                          {r.logo_url ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={r.logo_url} alt="" className="size-full object-contain" />
                          ) : (
                            (r.company_name || r.name).slice(0, 1).toUpperCase()
                          )}
                        </span>
                        <span className="min-w-0">
                          <Link href={`/sales/integrators/${r.id}`} className="block truncate font-medium text-accent hover:underline">{r.name}</Link>
                          {r.company_name && <span className="block truncate text-xs text-fg-faint">{r.company_name}</span>}
                        </span>
                      </div>
                    </td>
                    <td className="tnum px-3 py-2.5 text-right font-semibold">{r.companies}</td>
                    <td className="px-3 py-2.5">
                      {total === 0 ? (
                        <span className="text-fg-faint">—</span>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          <div className="flex h-2.5 w-24 overflow-hidden rounded-full bg-surface-2">
                            {(["active", "trial", "expired", "suspended"] as const).map((k) => cs[k] > 0 ? <div key={k} style={{ width: `${(cs[k] / total) * 100}%`, background: STATUS_COLORS[k] }} /> : null)}
                          </div>
                          <span className="tnum flex gap-1.5 text-xs">
                            {(["active", "trial", "expired", "suspended"] as const).map((k) => cs[k] > 0 ? <span key={k} style={{ color: STATUS_COLORS[k] }}>{cs[k]}</span> : null)}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", r.status === "active" ? "bg-accent-soft text-accent" : "bg-surface-3 text-fg-muted")}>
                        {t(`st_${r.status === "active" ? "active" : "suspended"}`)}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {open && <CreateDialog onClose={() => setOpen(false)} onCreated={() => queryClient.invalidateQueries({ queryKey: ["sales-integrators"] })} />}
    </div>
  );
}
