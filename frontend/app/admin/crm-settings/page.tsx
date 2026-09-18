"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { confirmDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import { createCrmMetaItem, deleteCrmMetaItem, fetchAdminCrmMeta } from "@/lib/api/admin";

const ICONS = ["phone", "calendar", "message", "bell", "clipboard"] as const;

function Section({
  title,
  kind,
  items,
  withIcon,
  onChanged,
}: {
  title: string;
  kind: "tag" | "source" | "task_type";
  items: { id: number; name: string; icon?: string }[];
  withIcon?: boolean;
  onChanged: () => void;
}) {
  const t = useTranslations("admin");
  const [name, setName] = useState("");
  const [icon, setIcon] = useState<string>("phone");

  const add = useMutation({
    mutationFn: () => createCrmMetaItem(kind, name.trim(), withIcon ? { icon } : undefined),
    onSuccess: () => { setName(""); onChanged(); },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteCrmMetaItem(kind, id),
    onSuccess: onChanged,
  });

  return (
    <section className="rounded-xl border border-border bg-surface">
      <header className="border-b border-border px-4 py-2.5 text-sm font-semibold">{title}</header>
      <ul className="divide-y divide-border">
        {items.map((it) => (
          <li key={it.id} className="flex items-center gap-2 px-4 py-2 text-sm">
            {withIcon && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-fg-muted">{it.icon}</span>}
            <span className="flex-1">{it.name}</span>
            <button
              type="button"
              onClick={async () => { if (await confirmDialog(t("crmSettings.deleteConfirm"), { danger: true })) remove.mutate(it.id); }}
              className="text-fg-faint hover:text-danger"
            >
              <X className="size-4" />
            </button>
          </li>
        ))}
        {items.length === 0 && <li className="px-4 py-4 text-center text-xs text-fg-faint">—</li>}
      </ul>
      <div className="flex flex-wrap items-center gap-2 border-t border-border p-3">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && name.trim() && add.mutate()}
          placeholder={t("crmSettings.namePlaceholder")}
          className="flex-1 rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
        />
        {withIcon && (
          <select value={icon} onChange={(e) => setIcon(e.target.value)} className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
            {ICONS.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
        )}
        <button type="button" disabled={!name.trim() || add.isPending} onClick={() => add.mutate()} className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg disabled:opacity-40">
          <Plus className="size-4" /> {t("crmSettings.add")}
        </button>
      </div>
    </section>
  );
}

export default function AdminCrmSettingsPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["a-crm-meta"], queryFn: fetchAdminCrmMeta });
  const onChanged = () => queryClient.invalidateQueries({ queryKey: ["a-crm-meta"] });

  return (
    <div data-testid="admin-crm-settings">
      <h1 className="mb-4 text-xl font-semibold">{t("crmSettings.title")}</h1>
      <div className="grid gap-4 lg:grid-cols-3">
        <Section title={t("crmSettings.sources")} kind="source" items={data?.sources ?? []} onChanged={onChanged} />
        <Section title={t("crmSettings.tags")} kind="tag" items={data?.tags ?? []} onChanged={onChanged} />
        <Section title={t("crmSettings.taskTypes")} kind="task_type" items={data?.task_types ?? []} withIcon onChanged={onChanged} />
      </div>
    </div>
  );
}
