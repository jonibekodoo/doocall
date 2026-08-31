"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import { createIntegrator, fetchIntegrators } from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";

function CreateDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const t = useTranslations("admin");
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    password: "",
    override: "",
  });
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const valid =
    form.name.trim() && form.email.includes("@") && form.password.length >= 8;
  const create = useMutation({
    mutationFn: async () => {
      const body = await createIntegrator({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone: form.phone,
      });
      if (form.override) {
        const { patchIntegrator } = await import("@/lib/api/admin");
        await patchIntegrator(body.integrator.id, {
          cashback_percent_override: form.override,
        });
      }
      return body;
    },
    onSuccess: (body) => {
      useToastStore.getState().push({
        kind: "success",
        text: t("integrators.codeToast", {
          code: body.integrator.referral_code,
        }),
      });
      onCreated();
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-5 shadow-lg">
        <h2 className="mb-3 text-base font-semibold">
          {t("integrators.newTitle")}
        </h2>
        {(["name", "email", "phone", "password"] as const).map((key) => (
          <label key={key} className="mb-2 block text-sm">
            <span className="mb-1 block text-xs capitalize text-fg-muted">
              {
                {
                  name: t("integrators.name"),
                  email: t("integrators.email"),
                  phone: t("integrators.phone"),
                  password: t("integrators.password"),
                }[key]
              }
            </span>
            <input
              type={key === "password" ? "password" : "text"}
              value={form[key]}
              onChange={set(key)}
              data-testid={`int-${key}`}
              className="w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
        ))}
        <label className="mb-2 block text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("integrators.overrideLabel")}
          </span>
          <input
            type="number"
            step="0.5"
            value={form.override}
            onChange={set("override")}
            data-testid="int-override"
            placeholder={t("integrators.overridePlaceholder")}
            className="tnum w-full rounded-md border border-border bg-surface px-3 py-2"
          />
        </label>
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-sm"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            data-testid="int-create"
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

export default function AdminIntegratorsPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["a-integrators"],
    queryFn: fetchIntegrators,
  });
  const [open, setOpen] = useState(false);

  return (
    <div data-testid="admin-integrators">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("integrators.title")}</h1>
        <button
          type="button"
          data-testid="new-integrator"
          onClick={() => setOpen(true)}
          className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-fg"
        >
          {t("integrators.new")}
        </button>
      </div>
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">{t("integrators.name")}</th>
              <th className="px-3 py-2 text-left">{t("integrators.code")}</th>
              <th className="px-3 py-2 text-right">
                {t("integrators.colCompanies")}
              </th>
              <th className="px-3 py-2 text-right">Override %</th>
              <th className="px-3 py-2 text-right">
                {t("integrators.balance")}
              </th>
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
              : (data?.integrators ?? []).map((row) => (
                  <tr
                    key={row.id}
                    className="border-t border-border hover:bg-surface-2/60"
                  >
                    <td className="px-3 py-2.5">
                      <Link
                        href={`/admin/integrators/${row.id}`}
                        className="font-medium text-accent hover:underline"
                      >
                        {row.name}
                      </Link>
                    </td>
                    <td className="tnum px-3 py-2.5 font-mono text-xs">
                      {row.referral_code}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {row.companies}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {row.override_percent ?? "—"}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {formatUzs(row.balance_uzs)}
                    </td>
                    <td className="px-3 py-2.5 text-xs">{row.status}</td>
                  </tr>
                ))}
          </tbody>
        </table>
        {!isPending && (data?.integrators ?? []).length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-fg-faint">
            {t("integrators.empty")}
          </p>
        )}
      </div>
      {open && (
        <CreateDialog
          onClose={() => setOpen(false)}
          onCreated={() =>
            queryClient.invalidateQueries({ queryKey: ["a-integrators"] })
          }
        />
      )}
    </div>
  );
}
