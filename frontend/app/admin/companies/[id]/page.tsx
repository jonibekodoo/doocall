"use client";

/** Company detail: subscription, seats, payments, actions, edit, impersonation. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Eye, KeyRound, Pencil, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { useToastStore } from "@/components/ui/Toast";
import {
  companyAction,
  deleteAdminCompany,
  fetchAdminCompany,
  impersonate,
  resetCompanyUserPassword,
  updateAdminCompany,
} from "@/lib/api/admin";
import { setAccessToken } from "@/lib/api/client";
import { formatUzs } from "@/lib/format";
import { useAuth } from "@/lib/auth";

function ExtendTrialDialog({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (days: number, reason: string) => void;
}) {
  const t = useTranslations("admin.companyDetail");
  const [days, setDays] = useState("7");
  const [reason, setReason] = useState("");
  const valid = Number(days) > 0 && reason.trim().length >= 3;
  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">{t("extendTrial")}</h2>
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">{t("days")}</span>
          <input
            type="number"
            min={1}
            value={days}
            onChange={(event) => setDays(event.target.value)}
            data-testid="extend-days"
            className="w-full rounded-md border border-border bg-surface px-3 py-2"
          />
        </label>
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("reasonRequired")}
          </span>
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            data-testid="extend-reason"
            className="w-full rounded-md border border-border bg-surface px-3 py-2"
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
            data-testid="extend-submit"
            disabled={!valid}
            onClick={() => onSubmit(Number(days), reason.trim())}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
          >
            {t("extend")}
          </button>
        </div>
      </div>
    </div>
  );
}

function EditCompanyDialog({
  initialName,
  initialRetention,
  onClose,
  onSubmit,
}: {
  initialName: string;
  initialRetention: number | null;
  onClose: () => void;
  onSubmit: (name: string, retention: number | null) => void;
}) {
  const t = useTranslations("admin.companyDetail");
  const [name, setName] = useState(initialName);
  const [retention, setRetention] = useState(
    initialRetention == null ? "" : String(initialRetention),
  );
  const retentionValid =
    retention.trim() === "" ||
    (Number.isInteger(Number(retention)) && Number(retention) >= 1);
  const valid = name.trim().length >= 2 && retentionValid;
  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">{t("editTitle")}</h2>
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("nameLabel")}
          </span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            data-testid="edit-company-name"
            className="w-full rounded-md border border-border bg-surface px-3 py-2"
          />
        </label>
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("retentionLabel")}
          </span>
          <input
            type="number"
            min={1}
            value={retention}
            onChange={(event) => setRetention(event.target.value)}
            placeholder={t("retentionDefault")}
            data-testid="edit-company-retention"
            className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
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
            data-testid="edit-company-submit"
            disabled={!valid}
            onClick={() =>
              onSubmit(
                name.trim(),
                retention.trim() === "" ? null : Number(retention),
              )
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

function DeleteCompanyDialog({
  name,
  slug,
  onClose,
  onSubmit,
}: {
  name: string;
  slug: string;
  onClose: () => void;
  onSubmit: (confirm: string) => void;
}) {
  const t = useTranslations("admin.companyDetail");
  const [confirm, setConfirm] = useState("");
  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-danger/40 bg-surface p-5 shadow-lg">
        <h2 className="mb-2 text-base font-semibold text-danger">
          {t("deleteCompany")}
        </h2>
        <p className="mb-3 text-sm text-fg-muted">
          {t("deleteWarning", { name })}
        </p>
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("deleteConfirmLabel", { slug })}
          </span>
          <input
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            data-testid="delete-confirm"
            autoComplete="off"
            className="w-full rounded-md border border-border bg-surface px-3 py-2"
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
            data-testid="delete-submit"
            disabled={confirm !== slug}
            onClick={() => onSubmit(confirm)}
            className="rounded-md bg-danger px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            {t("deleteForever")}
          </button>
        </div>
      </div>
    </div>
  );
}

function ResetPasswordDialog({
  email,
  onClose,
  onSubmit,
}: {
  email: string;
  onClose: () => void;
  onSubmit: (password: string) => void;
}) {
  const t = useTranslations("admin.companyDetail");
  const [password, setPassword] = useState("");
  const generate = () => {
    const alphabet =
      "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
    const bytes = new Uint8Array(12);
    crypto.getRandomValues(bytes);
    setPassword(
      Array.from(bytes, (b) => alphabet[b % alphabet.length]).join(""),
    );
  };
  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-1 text-base font-semibold">{t("resetPassword")}</h2>
        <p className="mb-3 text-sm text-fg-muted">{email}</p>
        <label className="mb-2 block text-sm">
          <span className="mb-1 flex items-center justify-between text-xs text-fg-muted">
            {t("newPassword")}
            <button
              type="button"
              onClick={generate}
              data-testid="password-generate"
              className="font-semibold text-accent hover:underline"
            >
              {t("generatePassword")}
            </button>
          </span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            data-testid="password-input"
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
            data-testid="password-submit"
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

export default function AdminCompanyDetailPage() {
  const t = useTranslations("admin.companyDetail");
  const params = useParams<{ id: string }>();
  const companyId = Number(params.id);
  const queryClient = useQueryClient();
  const router = useRouter();
  const { user } = useAuth();
  const isSuper = user?.role === "superadmin";
  const [extendOpen, setExtendOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState<{
    id: number;
    email: string;
  } | null>(null);

  const { data, isPending } = useQuery({
    queryKey: ["a-company", companyId],
    queryFn: () => fetchAdminCompany(companyId),
    enabled: Number.isFinite(companyId),
  });

  const act = useMutation({
    mutationFn: ({ action, body }: { action: string; body?: unknown }) =>
      companyAction(companyId, action, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-company", companyId] });
      useToastStore.getState().push({ kind: "success", text: t("done") });
    },
  });

  const edit = useMutation({
    mutationFn: (body: { name: string; audio_retention_days: number | null }) =>
      updateAdminCompany(companyId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-company", companyId] });
      queryClient.invalidateQueries({ queryKey: ["a-companies"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });

  const destroy = useMutation({
    mutationFn: (confirm: string) => deleteAdminCompany(companyId, confirm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-companies"] });
      useToastStore.getState().push({ kind: "success", text: t("deleted") });
      router.push("/admin/companies");
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });

  const resetPassword = useMutation({
    mutationFn: ({ userId, password }: { userId: number; password: string }) =>
      resetCompanyUserPassword(companyId, userId, password),
    onSuccess: () => {
      useToastStore
        .getState()
        .push({ kind: "success", text: t("passwordSaved") });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });

  const startImpersonation = async () => {
    const body = await impersonate(companyId);
    // Persist for the cabinet banner + restore path back to admin.
    sessionStorage.setItem(
      "doocall_impersonation",
      JSON.stringify({
        token: body.access,
        company: body.company,
        user: body.impersonated_user,
      }),
    );
    setAccessToken(body.access);
    router.push("/cabinet");
  };

  if (isPending)
    return <div className="h-64 animate-pulse rounded-lg bg-surface-2" />;
  if (!data) return null;
  const company = data.company;

  return (
    <div data-testid="admin-company-detail">
      <Link
        href="/admin/companies"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-accent"
      >
        <ArrowLeft className="size-4" /> {t("back")}
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            {company.name}
            <button
              type="button"
              data-testid="edit-company-btn"
              onClick={() => setEditOpen(true)}
              aria-label={t("edit")}
              className="grid size-7 place-items-center rounded-md text-fg-muted hover:bg-surface-2 hover:text-accent"
            >
              <Pencil className="size-4" />
            </button>
          </h1>
          <p className="mt-1 text-sm text-fg-muted">
            {company.status} · {t("subscription")}:{" "}
            {company.subscription_status ?? "—"} · {t("operatorsCount")}:{" "}
            <b className="tnum">{company.seats}</b>
            {company.status === "trial" && company.trial_ends_at && (
              <span
                className={
                  company.trial_expired ? "ml-2 font-semibold text-danger" : "ml-2"
                }
              >
                {company.trial_expired
                  ? t("trialExpiredAt", {
                      date: company.trial_ends_at.slice(0, 10),
                    })
                  : t("trialEndsAt", {
                      date: company.trial_ends_at.slice(0, 10),
                    })}
              </span>
            )}
            {company.integrator_id && (
              <span className="ml-2 rounded bg-accent-soft px-1.5 py-0.5 text-xs font-semibold text-accent">
                {t("integrator")} #{company.integrator_id} ·{" "}
                {company.acquired_via}
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          {company.status !== "suspended" ? (
            <button
              type="button"
              data-testid="suspend-btn"
              onClick={() =>
                window.confirm(t("suspendConfirm")) &&
                act.mutate({ action: "suspend" })
              }
              className="rounded-md border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/5"
            >
              {t("suspend")}
            </button>
          ) : (
            <button
              type="button"
              data-testid="activate-btn"
              onClick={() => act.mutate({ action: "activate" })}
              className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg"
            >
              {t("activate")}
            </button>
          )}
          <button
            type="button"
            onClick={() => setExtendOpen(true)}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
          >
            {t("extendTrial")}
          </button>
          {isSuper && (
            <button
              type="button"
              data-testid="impersonate-btn"
              onClick={startImpersonation}
              className="flex items-center gap-1.5 rounded-md border border-warning/50 px-3 py-1.5 text-sm font-medium text-warning hover:bg-warning/10"
            >
              <Eye className="size-4" /> {t("impersonate")}
            </button>
          )}
          {isSuper && (
            <button
              type="button"
              data-testid="delete-btn"
              onClick={() => setDeleteOpen(true)}
              className="flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/5"
            >
              <Trash2 className="size-4" /> {t("deleteCompany")}
            </button>
          )}
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
            {t("users")}
          </p>
          <ul className="divide-y divide-border">
            {company.users.map((cabinetUser) => (
              <li
                key={cabinetUser.id}
                className="flex items-center gap-2 px-4 py-2 text-sm"
              >
                <span className="flex-1 truncate">{cabinetUser.email}</span>
                {cabinetUser.is_company_admin && (
                  <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">
                    {t("companyAdmin")}
                  </span>
                )}
                {!cabinetUser.is_active && (
                  <span className="rounded-full bg-surface-3 px-2 py-0.5 text-xs">
                    {t("inactive")}
                  </span>
                )}
                {isSuper && (
                  <button
                    type="button"
                    data-testid={`reset-password-${cabinetUser.id}`}
                    onClick={() =>
                      setPasswordUser({
                        id: cabinetUser.id,
                        email: cabinetUser.email,
                      })
                    }
                    aria-label={t("resetPassword")}
                    title={t("resetPassword")}
                    className="grid size-7 place-items-center rounded-md text-fg-muted hover:bg-surface-2 hover:text-accent"
                  >
                    <KeyRound className="size-4" />
                  </button>
                )}
              </li>
            ))}
            {company.users.length === 0 && (
              <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>
            )}
          </ul>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
            {t("operators")}
          </p>
          <ul className="divide-y divide-border">
            {company.operators.map((operator) => (
              <li
                key={operator.id}
                className="flex items-center gap-2 px-4 py-2 text-sm"
              >
                <span className="flex-1">{operator.user_name}</span>
                <span className="text-xs text-fg-muted">
                  {operator.full_name}
                </span>
                {!operator.is_active && (
                  <span className="rounded-full bg-surface-3 px-2 py-0.5 text-xs">
                    {t("inactive")}
                  </span>
                )}
              </li>
            ))}
            {company.operators.length === 0 && (
              <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>
            )}
          </ul>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
            {t("payments")}
          </p>
          <ul className="divide-y divide-border">
            {company.payments.map((payment) => (
              <li
                key={payment.id}
                className="flex items-center gap-2 px-4 py-2 text-sm"
              >
                <span className="flex-1 capitalize">{payment.provider}</span>
                <span className="tnum">
                  {formatUzs(payment.amount_uzs)} UZS
                </span>
                <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">
                  {payment.status}
                </span>
              </li>
            ))}
            {company.payments.length === 0 && (
              <li className="px-4 py-6 text-center text-xs text-fg-faint">—</li>
            )}
          </ul>
        </section>
      </div>

      {extendOpen && (
        <ExtendTrialDialog
          onClose={() => setExtendOpen(false)}
          onSubmit={(days, reason) => {
            act.mutate({ action: "extend-trial", body: { days, reason } });
            setExtendOpen(false);
          }}
        />
      )}
      {passwordUser && (
        <ResetPasswordDialog
          email={passwordUser.email}
          onClose={() => setPasswordUser(null)}
          onSubmit={(password) => {
            resetPassword.mutate({ userId: passwordUser.id, password });
            setPasswordUser(null);
          }}
        />
      )}
      {deleteOpen && (
        <DeleteCompanyDialog
          name={company.name}
          slug={company.slug}
          onClose={() => setDeleteOpen(false)}
          onSubmit={(confirm) => {
            destroy.mutate(confirm);
            setDeleteOpen(false);
          }}
        />
      )}
      {editOpen && (
        <EditCompanyDialog
          initialName={company.name}
          initialRetention={company.audio_retention_days}
          onClose={() => setEditOpen(false)}
          onSubmit={(name, retention) => {
            edit.mutate({ name, audio_retention_days: retention });
            setEditOpen(false);
          }}
        />
      )}
    </div>
  );
}
