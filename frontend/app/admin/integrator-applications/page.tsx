"use client";

/** Integrator applications — CRM-style Kanban board. Drag a card between
 * columns (new → contacted → approved / rejected) to change its status. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import {
  type IntegratorApplicationRow,
  type SalesManagerRow,
  assignApplication,
  fetchIntegratorApplications,
  fetchSalesManagers,
  updateIntegratorApplication,
} from "@/lib/api/admin";
import { cn } from "@/lib/utils";

const COLUMNS = [
  { key: "new", accent: "bg-warning", soft: "bg-warning/10" },
  { key: "contacted", accent: "bg-accent", soft: "bg-accent-soft" },
  { key: "approved", accent: "bg-accent", soft: "bg-accent-soft" },
  { key: "rejected", accent: "bg-danger", soft: "bg-danger/10" },
] as const;

function Card({
  app,
  onDragStart,
  managers,
  onAssign,
  assignLabel,
}: {
  app: IntegratorApplicationRow;
  onDragStart: (id: number) => void;
  managers: SalesManagerRow[];
  onAssign: (id: number, sm: number | null) => void;
  assignLabel: string;
}) {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", String(app.id));
        e.dataTransfer.effectAllowed = "move";
        onDragStart(app.id);
      }}
      data-testid={`app-card-${app.id}`}
      className="cursor-grab rounded-lg border border-border bg-surface p-3 shadow-sm active:cursor-grabbing"
    >
      <p className="text-sm font-semibold">{app.full_name}</p>
      <div className="mt-1 space-y-0.5 text-xs text-fg-muted">
        <a
          href={`tel:${app.phone.replace(/\s/g, "")}`}
          className="tnum block hover:text-accent hover:underline"
        >
          {app.phone}
        </a>
        {app.email && (
          <a
            href={`mailto:${app.email}`}
            className="block truncate hover:text-accent hover:underline"
          >
            {app.email}
          </a>
        )}
        {app.company && <p className="truncate">{app.company}</p>}
      </div>
      {app.message && (
        <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-xs text-fg">
          {app.message}
        </p>
      )}
      <p className="mt-2 text-[10px] text-fg-faint">
        {app.created_at.slice(0, 16).replace("T", " ")}
      </p>
      <select
        value={app.sales_manager_id ?? ""}
        onChange={(e) => onAssign(app.id, e.target.value ? Number(e.target.value) : null)}
        onClick={(e) => e.stopPropagation()}
        className="mt-2 w-full rounded-md border border-border bg-surface px-2 py-1 text-xs"
      >
        <option value="">{assignLabel}</option>
        {managers.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function AdminIntegratorApplicationsPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const [dragId, setDragId] = useState<number | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);
  const { data, isPending } = useQuery({
    queryKey: ["a-integrator-apps"],
    queryFn: () => fetchIntegratorApplications(),
  });
  const { data: managersData } = useQuery({
    queryKey: ["a-sales-managers"],
    queryFn: fetchSalesManagers,
  });
  const managers = managersData?.managers ?? [];

  const mutate = useMutation({
    mutationFn: ({ id, next }: { id: number; next: string }) =>
      updateIntegratorApplication(id, next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-integrator-apps"] });
      useToastStore
        .getState()
        .push({ kind: "success", text: t("applications.updated") });
    },
  });

  const assign = useMutation({
    mutationFn: ({ id, sm }: { id: number; sm: number | null }) =>
      assignApplication(id, sm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-integrator-apps"] });
      useToastStore
        .getState()
        .push({ kind: "success", text: t("applications.assigned") });
    },
  });

  const label = (s: string) =>
    t(`applications.status_${s}` as "applications.status_new");

  const apps = data?.applications ?? [];
  const byStatus = (s: string) => apps.filter((a) => a.status === s);

  const drop = (status: string) => {
    setOverCol(null);
    if (dragId == null) return;
    const app = apps.find((a) => a.id === dragId);
    setDragId(null);
    if (app && app.status !== status) mutate.mutate({ id: app.id, next: status });
  };

  return (
    <div data-testid="admin-integrator-applications">
      <div className="mb-4 flex items-center gap-3">
        <h1 className="text-xl font-semibold">{t("applications.title")}</h1>
        {data && data.new_count > 0 && (
          <span className="rounded-full bg-warning/15 px-2.5 py-0.5 text-xs font-bold text-warning">
            {data.new_count} {t("applications.newBadge")}
          </span>
        )}
      </div>

      {isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {COLUMNS.map((c) => (
            <div key={c.key} className="h-64 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {COLUMNS.map((col) => {
            const items = byStatus(col.key);
            return (
              <div
                key={col.key}
                onDragOver={(e) => {
                  e.preventDefault();
                  setOverCol(col.key);
                }}
                onDragLeave={() => setOverCol((c) => (c === col.key ? null : c))}
                onDrop={() => drop(col.key)}
                className={cn(
                  "flex min-h-64 flex-col rounded-xl border bg-surface-2/40 transition-colors",
                  overCol === col.key
                    ? "border-accent bg-accent-soft/40"
                    : "border-border",
                )}
              >
                <header className="flex items-center gap-2 border-b border-border px-3 py-2.5">
                  <span className={cn("size-2.5 rounded-full", col.accent)} />
                  <h3 className="text-sm font-semibold">{label(col.key)}</h3>
                  <span className="tnum ml-auto rounded-full bg-surface-3 px-2 py-0.5 text-xs text-fg-muted">
                    {items.length}
                  </span>
                </header>
                <div className="flex-1 space-y-2.5 p-2.5">
                  {items.map((app) => (
                    <Card
                      key={app.id}
                      app={app}
                      onDragStart={setDragId}
                      managers={managers}
                      onAssign={(id, sm) => assign.mutate({ id, sm })}
                      assignLabel={t("applications.assignTo")}
                    />
                  ))}
                  {items.length === 0 && (
                    <p className="py-8 text-center text-xs text-fg-faint">—</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-3 text-xs text-fg-faint">{t("applications.dragHint")}</p>
    </div>
  );
}
