"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { BoardMetrics } from "@/components/crm/BoardMetrics";
import { LeadDetail, type LeadApi } from "@/components/crm/LeadDetail";
import { PriorityStars } from "@/components/crm/PriorityStars";
import { TaskBadge } from "@/components/crm/TaskBadge";
import { useToastStore } from "@/components/ui/Toast";
import {
  addLeadNote,
  addLeadTask,
  createLead,
  fetchBoardStats,
  fetchCrmMeta,
  fetchLead,
  fetchLeads,
  fetchPipelines,
  updateLead,
  updateTask,
} from "@/lib/api/sales";
import { cn } from "@/lib/utils";

const salesApi: LeadApi = {
  fetch: fetchLead,
  patch: (id, body) => updateLead(id, body),
  addNote: (id, text) => addLeadNote(id, text),
  addTask: (id, title, due, type) => addLeadTask(id, title, due, type),
  completeTask: (taskId) => updateTask(taskId, { action: "complete" }),
  cancelTask: (taskId, reason) => updateTask(taskId, { action: "cancel", reason }),
  editTask: (taskId, body) => updateTask(taskId, { action: "edit", ...body }),
};

export default function SalesCrmPage() {
  const t = useTranslations("crmui");
  const queryClient = useQueryClient();
  const [pipeId, setPipeId] = useState<number | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);
  const [overStage, setOverStage] = useState<number | null>(null);
  const [openLead, setOpenLead] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [fSource, setFSource] = useState("");
  const [fTag, setFTag] = useState("");
  const [fPrio, setFPrio] = useState("");

  const { data: pipesData } = useQuery({ queryKey: ["sales-pipelines"], queryFn: fetchPipelines });
  const { data: meta } = useQuery({ queryKey: ["sales-crm-meta"], queryFn: fetchCrmMeta });
  const { data: stats } = useQuery({ queryKey: ["sales-board-stats"], queryFn: fetchBoardStats });
  const pipelines = pipesData?.pipelines ?? [];
  const activePipe = pipelines.find((p) => p.id === pipeId) ?? pipelines[0];

  const query = new URLSearchParams({
    ...(activePipe ? { pipeline: String(activePipe.id) } : {}),
    ...(q ? { q } : {}),
    ...(fSource ? { source: fSource } : {}),
    ...(fTag ? { tag: fTag } : {}),
    ...(fPrio ? { priority: fPrio } : {}),
  }).toString();

  const { data: leadsData } = useQuery({
    queryKey: ["sales-leads", activePipe?.id, q, fSource, fTag, fPrio],
    queryFn: () => fetchLeads(`?${query}`),
    enabled: !!activePipe,
  });
  const leads = leadsData?.leads ?? [];
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["sales-leads"] });
    queryClient.invalidateQueries({ queryKey: ["sales-board-stats"] });
  };

  const move = useMutation({
    mutationFn: ({ id, stage_id }: { id: number; stage_id: number }) => updateLead(id, { stage_id }),
    onSuccess: invalidate,
  });
  const addLead = useMutation({
    mutationFn: (name: string) => createLead({ full_name: name }),
    onSuccess: () => { invalidate(); useToastStore.getState().push({ kind: "success", text: t("leadAdded") }); },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  const newLead = async () => {
    const { promptDialog } = await import("@/components/ui/Confirm");
    const name = await promptDialog(t("newLead"), "");
    if (name && name.trim()) addLead.mutate(name.trim());
  };

  return (
    <div data-testid="sales-crm" className="flex h-[calc(100vh-3rem)] flex-col">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">{t("crm")}</h1>
        <button type="button" onClick={newLead} className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg"><Plus className="size-4" /> {t("newLead")}</button>
      </div>

      <BoardMetrics stats={stats} />

      {/* Search + filters */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-faint" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchPlaceholder")} className="w-56 rounded-md border border-border bg-surface py-1.5 pl-8 pr-3 text-sm" />
        </div>
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
          <button key={p.id} type="button" onClick={() => setPipeId(p.id)} className={cn("rounded-full px-3 py-1.5 text-sm font-medium", activePipe?.id === p.id ? "bg-accent text-accent-fg" : "bg-surface-2 text-fg-muted hover:text-fg")}>{p.name}</button>
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
                onDrop={() => {
                  setOverStage(null);
                  if (dragId != null) {
                    const l = leads.find((x) => x.id === dragId);
                    if (l && l.stage_id !== stage.id) move.mutate({ id: dragId, stage_id: stage.id });
                  }
                  setDragId(null);
                }}
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
                      {lead.tags.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {lead.tags.map((tag) => <span key={tag.id} className="rounded-full bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent">{tag.name}</span>)}
                        </div>
                      )}
                      <div className="mt-2 flex justify-end">
                        <TaskBadge state={lead.task_state} />
                      </div>
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
        <LeadDetail leadId={openLead} queryKey="sales" api={salesApi} stages={activePipe.stages} meta={meta} onChanged={invalidate} onClose={() => setOpenLead(null)} />
      )}
    </div>
  );
}
