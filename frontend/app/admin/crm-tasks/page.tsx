"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Calendar, ClipboardList, MessageSquare, Phone, Search, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { confirmDialog, promptDialog } from "@/components/ui/Confirm";
import { cancelAdminTask, completeAdminTask, deleteAdminTask, fetchAdminCrmMeta, fetchAdminCrmTasks } from "@/lib/api/admin";
import { cn } from "@/lib/utils";

const BUCKETS = [
  { key: "overdue", tone: "border-danger/40", dot: "bg-danger" },
  { key: "today", tone: "border-accent/40", dot: "bg-accent" },
  { key: "tomorrow", tone: "border-warning/40", dot: "bg-warning" },
  { key: "planned", tone: "border-border", dot: "bg-fg-faint" },
] as const;

const TYPE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  phone: Phone, calendar: Calendar, message: MessageSquare, bell: Bell, clipboard: ClipboardList,
};

export default function AdminCrmTasksPage() {
  const t = useTranslations("crmui");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["a-crm-tasks"], queryFn: () => fetchAdminCrmTasks() });
  const { data: meta } = useQuery({ queryKey: ["a-crm-meta"], queryFn: fetchAdminCrmMeta });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["a-crm-tasks"] });
  const complete = useMutation({ mutationFn: (id: number) => completeAdminTask(id), onSuccess: invalidate });
  const cancel = useMutation({ mutationFn: ({ id, reason }: { id: number; reason: string }) => cancelAdminTask(id, reason), onSuccess: invalidate });
  const remove = useMutation({ mutationFn: (id: number) => deleteAdminTask(id), onSuccess: invalidate });

  const [q, setQ] = useState("");
  const [fType, setFType] = useState("");
  const [fManager, setFManager] = useState("");
  const [autoOnly, setAutoOnly] = useState(false);

  const open = (data?.tasks ?? []).filter((x) => !x.is_done && !x.is_cancelled);
  const managers = useMemo(() => [...new Set(open.map((x) => x.sales_manager).filter(Boolean))].sort(), [open]);
  const tasks = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return open
      .filter((x) => !fType || x.type?.name === fType)
      .filter((x) => !fManager || x.sales_manager === fManager)
      .filter((x) => !autoOnly || x.auto)
      .filter((x) => !ql || x.title.toLowerCase().includes(ql) || (x.lead_name ?? "").toLowerCase().includes(ql));
  }, [open, q, fType, fManager, autoOnly]);

  const doCancel = async (id: number) => {
    const reason = await promptDialog(t("cancelReasonPrompt"), "");
    if (reason !== null) cancel.mutate({ id, reason: reason.trim() });
  };

  return (
    <div data-testid="admin-crm-tasks" className="flex h-[calc(100vh-2rem)] flex-col">
      <h1 className="mb-3 text-xl font-semibold">{t("tasks")}</h1>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-faint" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchTask")} className="w-56 rounded-md border border-border bg-surface py-1.5 pl-8 pr-3 text-sm" />
        </div>
        <select value={fManager} onChange={(e) => setFManager(e.target.value)} className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
          <option value="">{t("allManagers")}</option>
          {managers.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <select value={fType} onChange={(e) => setFType(e.target.value)} className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
          <option value="">{t("allTypes")}</option>
          {(meta?.task_types ?? []).map((tt) => <option key={tt.id} value={tt.name}>{tt.name}</option>)}
        </select>
        <label className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-fg-muted">
          <input type="checkbox" checked={autoOnly} onChange={(e) => setAutoOnly(e.target.checked)} className="accent-accent" />
          {t("autoOnly")}
        </label>
      </div>
      <div className="grid min-h-0 flex-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {BUCKETS.map((b) => {
          const items = tasks.filter((x) => x.bucket === b.key);
          return (
            <div key={b.key} className={cn("flex min-h-0 flex-col rounded-xl border bg-surface-2/40", b.tone)}>
              <header className="flex items-center gap-2 border-b border-border px-3 py-2.5">
                <span className={cn("size-2.5 rounded-full", b.dot)} />
                <h3 className="text-sm font-semibold">{t(`bucket_${b.key}` as "bucket_today")}</h3>
                <span className="tnum ml-auto rounded-full bg-surface-3 px-2 py-0.5 text-xs text-fg-muted">{items.length}</span>
              </header>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2.5">
                {items.map((task) => {
                  const TIcon = task.type ? TYPE_ICON[task.type.icon] ?? ClipboardList : ClipboardList;
                  return (
                    <div key={task.id} className="rounded-lg border border-border bg-surface p-3">
                      <div className="flex items-start gap-2">
                        <TIcon className="mt-0.5 size-4 shrink-0 text-accent" />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm">{task.title}</p>
                          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-fg-faint">
                            {task.auto && <span className="inline-flex items-center gap-0.5 text-warning"><Sparkles className="size-3" />{t("autoTask")}</span>}
                            {task.due_at && <span className="tnum">{task.due_at.slice(0, 16).replace("T", " ")}</span>}
                            <span>· {task.sales_manager}</span>
                            {task.lead_name && <span>· {task.lead_name}</span>}
                          </div>
                        </div>
                      </div>
                      <div className="mt-2 flex justify-end gap-2">
                        <button type="button" onClick={() => complete.mutate(task.id)} className="rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-accent-fg">{t("complete")}</button>
                        <button type="button" onClick={() => doCancel(task.id)} className="rounded-md border border-danger/40 px-2.5 py-1 text-xs text-danger">{t("cancelTask")}</button>
                        <button type="button" onClick={async () => { if (await confirmDialog(t("deleteTaskConfirm"), { danger: true })) remove.mutate(task.id); }} className="text-fg-faint hover:text-danger">✕</button>
                      </div>
                    </div>
                  );
                })}
                {items.length === 0 && <p className="py-6 text-center text-xs text-fg-faint">—</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
