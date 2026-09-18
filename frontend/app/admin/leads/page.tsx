"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { BoardMetrics } from "@/components/crm/BoardMetrics";
import { LeadDetail, type LeadApi } from "@/components/crm/LeadDetail";
import { PriorityStars } from "@/components/crm/PriorityStars";
import { TaskBadge } from "@/components/crm/TaskBadge";
import { confirmDialog, promptDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import {
  addAdminLeadNote,
  addAdminLeadTask,
  addAdminStage,
  cancelAdminTask,
  completeAdminTask,
  createAdminLead,
  createAdminPipeline,
  deleteAdminLead,
  deleteAdminPipeline,
  editAdminTask,
  fetchAdminBoardStats,
  fetchAdminCrmMeta,
  fetchAdminLead,
  fetchAdminLeads,
  fetchAdminPipelines,
  fetchSalesManagers,
  patchAdminLead,
} from "@/lib/api/admin";
import type { CrmMeta } from "@/lib/api/sales";
import { cn } from "@/lib/utils";

const adminApi: LeadApi = {
  fetch: fetchAdminLead,
  patch: (id, body) => patchAdminLead(id, body),
  addNote: addAdminLeadNote,
  addTask: (id, title, due, type) => addAdminLeadTask(id, title, due, type),
  completeTask: (taskId) => completeAdminTask(taskId),
  cancelTask: (taskId, reason) => cancelAdminTask(taskId, reason),
  editTask: (taskId, body) => editAdminTask(taskId, body),
  remove: deleteAdminLead,
};

export default function AdminCrmBoardPage() {
  const t = useTranslations("crmui");
  const queryClient = useQueryClient();
  const [pipeId, setPipeId] = useState<number | null>(null);
  const [manager, setManager] = useState("");
  const [q, setQ] = useState("");
  const [fSource, setFSource] = useState("");
  const [fTag, setFTag] = useState("");
  const [fPrio, setFPrio] = useState("");
  const [dragId, setDragId] = useState<number | null>(null);
  const [overStage, setOverStage] = useState<number | null>(null);
  const [openLead, setOpenLead] = useState<number | null>(null);

  const { data: pipesData } = useQuery({ queryKey: ["a-pipelines"], queryFn: fetchAdminPipelines });
  const { data: metaData } = useQuery({ queryKey: ["a-crm-meta"], queryFn: fetchAdminCrmMeta });
  const meta = metaData as CrmMeta | undefined;
  const pipelines = pipesData?.pipelines ?? [];
  const activePipe = pipelines.find((p) => p.id === pipeId) ?? pipelines[0];

  const { data: mgrData } = useQuery({ queryKey: ["a-sales-managers"], queryFn: fetchSalesManagers });
  const managers = (mgrData?.managers ?? []).map((m) => ({ id: m.id, name: m.name }));

  const query = new URLSearchParams({
    ...(activePipe ? { pipeline: String(activePipe.id) } : {}),
    ...(manager ? { sales_manager: manager } : {}),
    ...(q ? { q } : {}),
    ...(fSource ? { source: fSource } : {}),
    ...(fTag ? { tag: fTag } : {}),
    ...(fPrio ? { priority: fPrio } : {}),
  }).toString();

  const { data: leadsData } = useQuery({
    queryKey: ["a-crm-leads", activePipe?.id, manager, q, fSource, fTag, fPrio],
    queryFn: () => fetchAdminLeads(`?${query}`),
    enabled: !!activePipe,
  });
  const { data: stats } = useQuery({
    queryKey: ["a-board-stats", manager],
    queryFn: () => fetchAdminBoardStats(manager ? `?sales_manager=${manager}` : ""),
  });
  const leads = leadsData?.leads ?? [];
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["a-crm-leads"] });
    queryClient.invalidateQueries({ queryKey: ["a-board-stats"] });
  };

  const move = useMutation({ mutationFn: ({ id, stage_id }: { id: number; stage_id: number }) => patchAdminLead(id, { stage_id }), onSuccess: invalidate });
  const newPipeline = useMutation({ mutationFn: (n: string) => createAdminPipeline(n), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["a-pipelines"] }) });
  const rmPipeline = useMutation({ mutationFn: (id: number) => deleteAdminPipeline(id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["a-pipelines"] }) });
  const newStage = useMutation({ mutationFn: (n: string) => addAdminStage(activePipe!.id, n), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["a-pipelines"] }) });

  const addFunnel = async () => { const n = await promptDialog(t("funnelNamePrompt"), ""); if (n && n.trim()) newPipeline.mutate(n.trim()); };
  const addStageFn = async () => { const n = await promptDialog(t("stageNamePrompt"), ""); if (n && n.trim()) newStage.mutate(n.trim()); };
  const addLeadFn = async () => {
    if (managers.length === 0) {
      useToastStore.getState().push({ kind: "error", text: t("needSalesManager") });
      return;
    }
    const name = await promptDialog(t("newLead"), "");
    if (!name || !name.trim()) return;
    try {
      await createAdminLead({ sales_manager_id: managers[0].id, full_name: name.trim() });
      invalidate();
      useToastStore.getState().push({ kind: "success", text: t("leadAdded") });
    } catch (e) {
      useToastStore.getState().push({ kind: "error", text: (e as Error).message });
    }
  };

  return (
    <div data-testid="admin-crm" className="flex h-[calc(100vh-2rem)] flex-col">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">{t("crm")}</h1>
        <div className="ml-auto flex flex-wrap gap-2">
          <button type="button" onClick={addLeadFn} className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg"><Plus className="size-4" />{t("newLead")}</button>
          <button type="button" onClick={addStageFn} disabled={!activePipe} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-2 disabled:opacity-40"><Plus className="size-4" />{t("addStage")}</button>
          <button type="button" onClick={addFunnel} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-2"><Plus className="size-4" />{t("addFunnel")}</button>
        </div>
      </div>

      <BoardMetrics stats={stats} />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-faint" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchPlaceholder")} className="w-56 rounded-md border border-border bg-surface py-1.5 pl-8 pr-3 text-sm" />
        </div>
        <select value={manager} onChange={(e) => setManager(e.target.value)} className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
          <option value="">{t("allManagers")}</option>
          {managers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select value={fSource} onChange={(e) => setFSource(e.target.value)} className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
          <option value="">{t("f_source")}</option>
          {(meta?.sources ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select value={fTag} onChange={(e) => setFTag(e.target.value)} className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
          <option value="">{t("f_tags")}</option>
          {(meta?.tags ?? []).map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
        </select>
        <select value={fPrio} onChange={(e) => setFPrio(e.target.value)} className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm">
          <option value="">{t("priority")}</option>
          {[1, 2, 3].map((n) => <option key={n} value={n}>{"★".repeat(n)}</option>)}
        </select>
        {pipelines.map((p) => (
          <span key={p.id} className="group inline-flex items-center">
            <button type="button" onClick={() => setPipeId(p.id)} className={cn("rounded-full px-3 py-1.5 text-sm font-medium", activePipe?.id === p.id ? "bg-accent text-accent-fg" : "bg-surface-2 text-fg-muted hover:text-fg")}>{p.name}</button>
            {pipelines.length > 1 && <button type="button" onClick={async () => { if (await confirmDialog(t("deleteFunnelConfirm"), { danger: true })) rmPipeline.mutate(p.id); }} className="ml-0.5 hidden text-fg-faint hover:text-danger group-hover:inline">✕</button>}
          </span>
        ))}
      </div>

      {activePipe && (
        <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto pb-2">
          {activePipe.stages.map((stage) => {
            const items = leads.filter((l) => l.stage_id === stage.id);
            return (
              <div
                key={stage.id}
                onDragOver={(e) => { e.preventDefault(); setOverStage(stage.id); }}
                onDragLeave={() => setOverStage((s) => (s === stage.id ? null : s))}
                onDrop={() => { setOverStage(null); if (dragId != null) { const l = leads.find((x) => x.id === dragId); if (l && l.stage_id !== stage.id) move.mutate({ id: dragId, stage_id: stage.id }); } setDragId(null); }}
                className={cn("flex w-72 shrink-0 flex-col rounded-xl border bg-surface-2/40", overStage === stage.id ? "border-accent bg-accent-soft/40" : "border-border")}
              >
                <header className="flex items-center gap-2 border-b border-border px-3 py-2.5">
                  <span className="size-2.5 rounded-full" style={{ background: stage.color || "var(--accent)" }} />
                  <h3 className="truncate text-sm font-semibold">{stage.name}</h3>
                  <span className="tnum ml-auto rounded-full bg-surface-3 px-2 py-0.5 text-xs text-fg-muted">{items.length}</span>
                </header>
                <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto p-2.5">
                  {items.map((lead) => (
                    <div
                      key={lead.id}
                      draggable
                      onDragStart={(e) => { e.dataTransfer.effectAllowed = "move"; setDragId(lead.id); }}
                      onClick={() => setOpenLead(lead.id)}
                      className="cursor-pointer rounded-lg border border-border bg-surface p-3 shadow-sm hover:border-accent"
                    >
                      {lead.source && <p className="mb-1 text-[10px] font-medium uppercase text-fg-faint">{lead.source.name}</p>}
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold">{lead.full_name}</p>
                        {lead.priority > 0 && <PriorityStars value={lead.priority} px={12} />}
                      </div>
                      {lead.company && <p className="truncate text-xs text-fg-faint">{lead.company}</p>}
                      {lead.phone && <p className="tnum truncate text-xs text-fg-muted">{lead.phone}</p>}
                      <p className="mt-1 text-[11px] text-fg-muted">{lead.sales_manager}</p>
                      <div className="mt-2 flex justify-end"><TaskBadge state={lead.task_state} /></div>
                    </div>
                  ))}
                  {items.length === 0 && <p className="py-6 text-center text-xs text-fg-faint">—</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {openLead != null && activePipe && meta && (
        <LeadDetail leadId={openLead} queryKey="admin" api={adminApi} stages={activePipe.stages} meta={meta} managers={managers} onChanged={invalidate} onClose={() => setOpenLead(null)} />
      )}
    </div>
  );
}
