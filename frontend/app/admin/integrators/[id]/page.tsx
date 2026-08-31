"use client";

/** Integrator detail: profile, effective-% editor (superadmin), contact
 * editing, companies, accrual ledger, payout actions, suspend toggle. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { useToastStore } from "@/components/ui/Toast";
import {
  fetchIntegratorDetail,
  patchIntegrator,
  payoutAction,
} from "@/lib/api/admin";
import { effectivePercentLabel } from "@/lib/admin-shared";
import { formatUzs } from "@/lib/format";
import { useAuth } from "@/lib/auth";

function EditIntegratorDialog({
  initial,
  onClose,
  onSubmit,
}: {
  initial: { name: string; email: string; phone: string; card: string };
  onClose: () => void;
  onSubmit: (body: {
    name: string;
    email: string;
    phone: string;
    payout_details: Record<string, string>;
  }) => void;
}) {
  const t = useTranslations("admin.integratorDetail");
  const [form, setForm] = useState(initial);
  const set =
    (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [key]: event.target.value }));
  const valid = form.name.trim().length >= 2 && form.email.includes("@");

  const FIELDS = [
    { key: "name" as const, label: t("nameLabel") },
    { key: "email" as const, label: "Email" },
    { key: "phone" as const, label: t("phoneLabel") },
    { key: "card" as const, label: t("cardLabel") },
  ];

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">{t("editTitle")}</h2>
        {FIELDS.map(({ key, label }) => (
          <label key={key} className="mb-2 block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">{label}</span>
            <input
              value={form[key]}
              onChange={set(key)}
              data-testid={`edit-int-${key}`}
              className="w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
        ))}
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-sm"
          >
            {t("cancel")}
          </button>
          <button
            type="button"
            data-testid="edit-int-submit"
            disabled={!valid}
            onClick={() =>
              onSubmit({
                name: form.name.trim(),
                email: form.email.trim(),
                phone: form.phone.trim(),
                payout_details: form.card.trim()
                  ? { card: form.card.trim() }
                  : {},
              })
            }
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
          >
            {t("save")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminIntegratorDetailPage() {
  const t = useTranslations("admin.integratorDetail");
  const params = useParams<{ id: string }>();
  const integratorId = Number(params.id);
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isSuper = user?.role === "superadmin";
  const [override, setOverride] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);

  const { data, isPending } = useQuery({
    queryKey: ["a-integrator", integratorId],
    queryFn: () => fetchIntegratorDetail(integratorId),
    enabled: Number.isFinite(integratorId),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["a-integrator", integratorId] });
  const patch = useMutation({
    mutationFn: (body: Parameters<typeof patchIntegrator>[1]) =>
      patchIntegrator(integratorId, body),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["a-integrators"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });
  const payout = useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: number;
      action: "approve" | "reject" | "mark-paid";
    }) => payoutAction(id, action),
    onSuccess: invalidate,
  });

  if (isPending)
    return <div className="h-64 animate-pulse rounded-lg bg-surface-2" />;
  if (!data) return null;
  const info = data.integrator;

  return (
    <div data-testid="admin-integrator-detail">
      <Link
        href="/admin/integrators"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-accent"
      >
        <ArrowLeft className="size-4" /> {t("back")}
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            {info.name}
            <button
              type="button"
              data-testid="edit-int-btn"
              onClick={() => setEditOpen(true)}
              aria-label={t("edit")}
              className="grid size-7 place-items-center rounded-md text-fg-muted hover:bg-surface-2 hover:text-accent"
            >
              <Pencil className="size-4" />
            </button>
          </h1>
          <p className="mt-1 text-sm text-fg-muted">
            {info.email}
            {info.phone && <> · {info.phone}</>} · {t("code")}{" "}
            <code className="rounded bg-surface-2 px-1.5">
              {info.referral_code}
            </code>
          </p>
          <p className="tnum mt-1 text-sm">
            {t("rate")}:{" "}
            <b data-testid="effective-percent">
              {effectivePercentLabel(
                info.override_percent,
                info.default_percent,
                t("defaultSuffix"),
              )}
            </b>
            {" · "}
            {t("lifetime")}: <b>{formatUzs(info.lifetime_cashback_uzs)} UZS</b>
            {" · "}
            {t("balance")}: <b>{formatUzs(info.balance_uzs)} UZS</b>
          </p>
        </div>
        <button
          type="button"
          data-testid="int-suspend"
          onClick={() =>
            patch.mutate({
              status: info.status === "active" ? "suspended" : "active",
            })
          }
          className={
            info.status === "active"
              ? "rounded-md border border-danger/40 px-3 py-1.5 text-sm text-danger"
              : "rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg"
          }
        >
          {info.status === "active" ? t("suspend") : t("activate")}
        </button>
      </div>

      {isSuper && (
        <div className="mt-4 flex max-w-md items-end gap-2 rounded-lg border border-border bg-surface p-3">
          <label className="flex-1 text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("overrideLabel")}
            </span>
            <input
              type="number"
              step="0.5"
              data-testid="override-input"
              value={override ?? info.override_percent ?? ""}
              onChange={(e) => setOverride(e.target.value)}
              className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
          <button
            type="button"
            data-testid="override-save"
            disabled={override === null}
            onClick={() =>
              patch.mutate({
                cashback_percent_override: override === "" ? null : override,
              })
            }
            className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
          >
            OK
          </button>
        </div>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
            {t("companies")}
          </p>
          <ul className="divide-y divide-border">
            {data.companies.map((c) => (
              <li key={c.id} className="px-4 py-2 text-sm">
                <span className="font-medium">{c.name}</span>
                <span className="tnum float-right text-accent">
                  {formatUzs(c.cashback_uzs)}
                </span>
                <p className="text-xs text-fg-faint">
                  {c.status} · {c.acquired_via}
                </p>
              </li>
            ))}
            {data.companies.length === 0 && (
              <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>
            )}
          </ul>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
            {t("accruals")}
          </p>
          <ul className="divide-y divide-border" data-testid="accrual-ledger">
            {data.accruals.slice(0, 15).map((a) => (
              <li
                key={a.id}
                className="flex items-center gap-2 px-4 py-2 text-sm"
              >
                <span className="min-w-0 flex-1 truncate text-xs">
                  {a.company}
                </span>
                <span className="tnum">{formatUzs(a.amount_uzs)}</span>
                <span className="tnum text-xs text-fg-faint">{a.percent}%</span>
                <span className="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px]">
                  {a.status}
                </span>
              </li>
            ))}
            {data.accruals.length === 0 && (
              <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>
            )}
          </ul>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
            {t("payouts")}
          </p>
          <ul className="divide-y divide-border">
            {data.payouts.map((p) => (
              <li
                key={p.id}
                className="flex items-center gap-2 px-4 py-2 text-sm"
              >
                <span className="tnum flex-1">
                  {formatUzs(p.amount_uzs)} UZS
                </span>
                <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">
                  {p.status}
                </span>
                {isSuper && p.status === "pending" && (
                  <>
                    <button
                      type="button"
                      data-testid={`d-payout-approve-${p.id}`}
                      onClick={() =>
                        payout.mutate({ id: p.id, action: "approve" })
                      }
                      className="rounded bg-accent px-2 py-0.5 text-xs font-semibold text-accent-fg"
                    >
                      ✓
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        payout.mutate({ id: p.id, action: "reject" })
                      }
                      className="rounded border border-danger/40 px-2 py-0.5 text-xs text-danger"
                    >
                      ✗
                    </button>
                  </>
                )}
                {isSuper && p.status === "approved" && (
                  <button
                    type="button"
                    data-testid={`d-payout-paid-${p.id}`}
                    onClick={() =>
                      payout.mutate({ id: p.id, action: "mark-paid" })
                    }
                    className="rounded bg-accent px-2 py-0.5 text-xs font-semibold text-accent-fg"
                  >
                    {t("markPaid")}
                  </button>
                )}
              </li>
            ))}
            {data.payouts.length === 0 && (
              <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>
            )}
          </ul>
        </section>
      </div>

      {editOpen && (
        <EditIntegratorDialog
          initial={{
            name: info.name,
            email: info.email,
            phone: info.phone,
            card: info.payout_details?.card ?? "",
          }}
          onClose={() => setEditOpen(false)}
          onSubmit={(body) => {
            patch.mutate(body);
            setEditOpen(false);
          }}
        />
      )}
    </div>
  );
}
