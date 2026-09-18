"use client";

/** Integrator detail: profile, effective-% editor (superadmin), contact
 * editing, companies, accrual ledger, payout actions, suspend toggle. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Globe, ImageIcon, KeyRound, Pencil } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { useToastStore } from "@/components/ui/Toast";
import {
  fetchIntegratorDetail,
  fetchSalesManagers,
  patchIntegrator,
  payoutAction,
  resetIntegratorPassword,
  uploadIntegratorLogo,
} from "@/lib/api/admin";
import { effectivePercentLabel } from "@/lib/admin-shared";
import { formatUzs } from "@/lib/format";
import { useAuth } from "@/lib/auth";

function EditIntegratorDialog({
  initial,
  onClose,
  onSubmit,
}: {
  initial: {
    name: string;
    company_name: string;
    email: string;
    phone: string;
    card: string;
  };
  onClose: () => void;
  onSubmit: (body: {
    name: string;
    company_name: string;
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
    { key: "company_name" as const, label: t("companyLabel") },
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
                company_name: form.company_name.trim(),
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

function ResetPasswordDialog({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (password: string) => void;
}) {
  const t = useTranslations("admin.integratorDetail");
  const [password, setPassword] = useState("");
  const generate = () => {
    const alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
    const bytes = new Uint8Array(12);
    crypto.getRandomValues(bytes);
    setPassword(Array.from(bytes, (b) => alphabet[b % alphabet.length]).join(""));
  };
  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">{t("resetPassword")}</h2>
        <label className="mb-2 block text-sm">
          <span className="mb-1 flex items-center justify-between text-xs text-fg-muted">
            {t("newPassword")}
            <button
              type="button"
              onClick={generate}
              className="font-semibold text-accent hover:underline"
            >
              {t("generatePassword")}
            </button>
          </span>
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-testid="int-password-input"
            autoComplete="off"
            className="w-full rounded-md border border-border bg-surface px-3 py-2 font-mono"
          />
        </label>
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
            data-testid="int-password-submit"
            disabled={password.length < 8}
            onClick={() => onSubmit(password)}
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
  const [passwordOpen, setPasswordOpen] = useState(false);

  const { data, isPending } = useQuery({
    queryKey: ["a-integrator", integratorId],
    queryFn: () => fetchIntegratorDetail(integratorId),
    enabled: Number.isFinite(integratorId),
  });
  const { data: managers } = useQuery({
    queryKey: ["a-sales-managers"],
    queryFn: fetchSalesManagers,
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
  const resetPw = useMutation({
    mutationFn: (password: string) =>
      resetIntegratorPassword(integratorId, password),
    onSuccess: () => {
      useToastStore
        .getState()
        .push({ kind: "success", text: t("passwordSaved") });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });
  const logoUpload = useMutation({
    mutationFn: (file: File) => uploadIntegratorLogo(integratorId, file),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["a-integrators"] });
      queryClient.invalidateQueries({ queryKey: ["a-integrator-stats"] });
      useToastStore.getState().push({ kind: "success", text: t("logoSaved") });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
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
        <div className="flex items-start gap-3">
          {/* Logo (click to upload) */}
          <label
            className="group relative grid size-14 shrink-0 cursor-pointer place-items-center overflow-hidden rounded-xl border border-border bg-surface-2"
            title={t("uploadLogo")}
          >
            {info.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={info.logo_url}
                alt={info.company_name || info.name}
                className="size-full object-contain"
              />
            ) : (
              <ImageIcon className="size-5 text-fg-faint" />
            )}
            <input
              type="file"
              accept="image/png,image/jpeg,image/svg+xml,image/webp"
              className="hidden"
              data-testid="int-logo-input"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) logoUpload.mutate(file);
                e.target.value = "";
              }}
            />
            <span className="absolute inset-x-0 bottom-0 hidden bg-black/50 py-0.5 text-center text-[9px] font-medium text-white group-hover:block">
              {logoUpload.isPending ? "…" : t("logoEdit")}
            </span>
          </label>
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
          {info.company_name && (
            <p className="text-sm font-medium text-fg-muted">
              {info.company_name}
            </p>
          )}
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
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="int-publish"
            onClick={() => patch.mutate({ is_public: !info.is_public })}
            className={
              info.is_public
                ? "inline-flex items-center gap-1.5 rounded-md bg-accent-soft px-3 py-1.5 text-sm font-semibold text-accent"
                : "inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
            }
          >
            <Globe className="size-4" />
            {info.is_public ? t("publishedOnSite") : t("publishOnSite")}
          </button>
          {isSuper && (
            <button
              type="button"
              data-testid="int-reset-password"
              onClick={() => setPasswordOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
            >
              <KeyRound className="size-4" /> {t("resetPassword")}
            </button>
          )}
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

      {/* Sales manager assignment + bank + offer */}
      <section className="mt-6 rounded-lg border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-semibold">{t("salesManagerLabel")}:</span>
          <select
            value={info.sales_manager_id ?? ""}
            onChange={(e) =>
              patch.mutate({
                sales_manager_id: e.target.value ? Number(e.target.value) : null,
              })
            }
            className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm"
          >
            <option value="">{t("salesManagerNone")}</option>
            {(managers?.managers ?? []).map((mgr) => (
              <option key={mgr.id} value={mgr.id}>
                {mgr.name} ({mgr.commission_percent}%)
              </option>
            ))}
          </select>
          {info.offer_accepted_at && (
            <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
              {t("offerAcceptedBadge")}
            </span>
          )}
        </div>
        {(info.bank_card || info.bank_mfo || info.bank_inn || info.bank_transit) && (
          <p className="tnum mt-2 text-xs text-fg-faint">
            {t("bankCard")}: {info.bank_card || "—"} · MFO: {info.bank_mfo || "—"} · INN:{" "}
            {info.bank_inn || "—"} · {t("bankTransit")}: {info.bank_transit || "—"}
          </p>
        )}
      </section>

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
                  {t(`st_${c.status}` as "st_active")} · {c.acquired_via}
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
                  {t(`acc_${a.status}` as "acc_accrued")}
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
                  {t(`po_${p.status}` as "po_pending")}
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
            company_name: info.company_name ?? "",
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
      {passwordOpen && (
        <ResetPasswordDialog
          onClose={() => setPasswordOpen(false)}
          onSubmit={(password) => {
            resetPw.mutate(password);
            setPasswordOpen(false);
          }}
        />
      )}
    </div>
  );
}
