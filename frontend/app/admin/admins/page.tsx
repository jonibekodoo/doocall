"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import {
  createPlatformAdmin,
  fetchPlatformAdmins,
  togglePlatformAdmin,
} from "@/lib/api/admin";

export default function AdminAdminsPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["a-admins"],
    queryFn: fetchPlatformAdmins,
  });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["a-admins"] });
  const create = useMutation({
    mutationFn: () => createPlatformAdmin({ email, password }),
    onSuccess: () => {
      setEmail("");
      setPassword("");
      invalidate();
    },
  });

  return (
    <div data-testid="admin-admins" className="max-w-lg">
      <h1 className="mb-4 text-xl font-semibold">{t("admins.title")}</h1>
      <div className="mb-4 flex gap-2 rounded-lg border border-border bg-surface p-3">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email"
          className="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t("admins.passwordPlaceholder")}
          className="w-40 rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
        <button
          type="button"
          disabled={!email || password.length < 8 || create.isPending}
          onClick={() => create.mutate()}
          className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
        >
          {t("common.create")}
        </button>
      </div>
      <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
        {(data?.admins ?? []).map((admin) => (
          <li
            key={admin.id}
            className="flex items-center gap-2 px-4 py-2.5 text-sm"
          >
            <span className={admin.is_active ? "flex-1" : "flex-1 opacity-50"}>
              {admin.email}
            </span>
            <button
              type="button"
              onClick={() =>
                togglePlatformAdmin(admin.id, !admin.is_active).then(invalidate)
              }
              className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-surface-2"
            >
              {admin.is_active ? t("admins.disable") : t("admins.enable")}
            </button>
          </li>
        ))}
        {(data?.admins ?? []).length === 0 && (
          <li className="px-4 py-8 text-center text-sm text-fg-faint">
            {t("admins.empty")}
          </li>
        )}
      </ul>
    </div>
  );
}
