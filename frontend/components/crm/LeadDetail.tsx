"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Calendar,
  Check,
  CheckCircle2,
  ClipboardList,
  GitBranch,
  MessageSquare,
  Pencil,
  Phone,
  Plus,
  Trash2,
  UserCheck,
  X,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { PriorityStars } from "@/components/crm/PriorityStars";
import { confirmDialog, promptDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import type { CrmMeta, LeadDetailData } from "@/lib/api/sales";
import { cn } from "@/lib/utils";

export interface LeadApi {
  fetch: (id: number) => Promise<{ lead: LeadDetailData }>;
  patch: (id: number, body: Record<string, unknown>) => Promise<unknown>;
  addNote: (id: number, text: string) => Promise<unknown>;
  addTask: (id: number, title: string, due_at?: string, type_id?: number) => Promise<unknown>;
  completeTask: (taskId: number) => Promise<unknown>;
  cancelTask: (taskId: number, reason: string) => Promise<unknown>;
  editTask: (taskId: number, body: { title?: string }) => Promise<unknown>;
  remove?: (id: number) => Promise<unknown>;
}

const EVENT_STYLE: Record<string, { icon: React.ComponentType<{ className?: string }>; tone: string }> = {
  created: { icon: Plus, tone: "bg-accent-soft text-accent" },
  note: { icon: MessageSquare, tone: "bg-warning/15 text-warning" },
  stage: { icon: GitBranch, tone: "bg-accent-soft text-accent" },
  task: { icon: ClipboardList, tone: "bg-accent-soft text-accent" },
  task_done: { icon: CheckCircle2, tone: "bg-accent-soft text-accent" },
  cancelled: { icon: XCircle, tone: "bg-danger/10 text-danger" },
  field: { icon: Pencil, tone: "bg-surface-3 text-fg-muted" },
  assigned: { icon: UserCheck, tone: "bg-accent-soft text-accent" },
};

const TYPE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  phone: Phone,
  calendar: Calendar,
  message: MessageSquare,
  bell: Bell,
  clipboard: ClipboardList,
};

const TEXT_FIELDS = ["full_name", "contact_name", "phone", "email", "company"] as const;

export function LeadDetail({
  leadId,
  queryKey,
  api,
  stages,
  meta,
  managers,
  onChanged,
  onClose,
}: {
  leadId: number;
  queryKey: string;
  api: LeadApi;
  stages: { id: number; name: string; color: string }[];
  meta: CrmMeta;
  managers?: { id: number; name: string }[];
  onChanged?: () => void;
  onClose: () => void;
}) {
  const t = useTranslations("crmui");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: [queryKey, "lead", leadId], queryFn: () => api.fetch(leadId) });
  const lead = data?.lead;

  const [form, setForm] = useState<Record<string, string>>({});
  const [composer, setComposer] = useState<"note" | "task">("note");
  const [text, setText] = useState("");
  const [due, setDue] = useState("");
  const [typeId, setTypeId] = useState("");

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: [queryKey, "lead", leadId] });
    onChanged?.();
  };
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(leadId, body),
    onSuccess: () => { setForm({}); refresh(); useToastStore.getState().push({ kind: "success", text: t("saved") }); },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });
  const note = useMutation({ mutationFn: (v: string) => api.addNote(leadId, v), onSuccess: () => { setText(""); refresh(); } });
  const task = useMutation({
    mutationFn: (v: { title: string; due?: string; type?: number }) => api.addTask(leadId, v.title, v.due, v.type),
    onSuccess: () => { setText(""); setDue(""); setTypeId(""); refresh(); },
  });
  const taskAct = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: refresh,
  });

  if (!lead) {
    return (
      <div className="fixed inset-0 z-50 grid place-items-center bg-black/40">
        <div className="h-40 w-40 animate-pulse rounded-xl bg-surface-2" />
      </div>
    );
  }

  const val = (k: string) => form[k] ?? (lead as unknown as Record<string, string>)[k] ?? "";
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));
  const dirty = Object.keys(form).length > 0;
  const tagIds = new Set(lead.tag_ids);

  const cancelTask = async (taskId: number) => {
    const reason = await promptDialog(t("cancelReasonPrompt"), "");
    if (reason === null) return;
    taskAct.mutate(() => api.cancelTask(taskId, reason.trim()));
  };
  const editTask = async (taskId: number, current: string) => {
    const title = await promptDialog(t("editTaskPrompt"), current);
    if (title && title.trim()) taskAct.mutate(() => api.editTask(taskId, { title: title.trim() }));
  };

  return (
    <div className="fixed inset-0 z-50 flex bg-black/40" onClick={onClose}>
      <div className="ml-auto flex h-full w-full max-w-4xl flex-col bg-bg shadow-2xl sm:flex-row" onClick={(e) => e.stopPropagation()}>
        {/* Left — lead fields */}
        <div className="flex w-full flex-col overflow-y-auto border-r border-border bg-surface p-5 sm:w-[46%]">
          {/* Tags + source ABOVE the name */}
          <div className="mb-3 flex flex-wrap items-center gap-1.5">
            {meta.tags
              .filter((tag) => tagIds.has(tag.id))
              .map((tag) => (
                <span key={tag.id} className="inline-flex items-center gap-1 rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-accent-fg">
                  {tag.name}
                  <button
                    type="button"
                    onClick={() => patch.mutate({ tag_ids: [...tagIds].filter((x) => x !== tag.id) })}
                    className="hover:opacity-70"
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
            <select
              value=""
              onChange={(e) => e.target.value && patch.mutate({ tag_ids: [...tagIds, Number(e.target.value)] })}
              className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-fg-muted"
            >
              <option value="">+ {t("f_tags")}</option>
              {meta.tags
                .filter((tag) => !tagIds.has(tag.id))
                .map((tag) => (
                  <option key={tag.id} value={tag.id}>{tag.name}</option>
                ))}
            </select>
          </div>
          <label className="mb-3 block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">{t("f_source")}</span>
            <select
              value={lead.source_id ?? ""}
              onChange={(e) => patch.mutate({ source_id: e.target.value ? Number(e.target.value) : null })}
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
            >
              <option value="">—</option>
              {meta.sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>

          <div className="mb-3 flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <input
                value={val("full_name")}
                onChange={set("full_name")}
                className="w-full rounded-md border border-transparent bg-transparent text-lg font-semibold hover:border-border focus:border-accent focus:outline-none"
              />
              <PriorityStars value={lead.priority} onChange={(p) => patch.mutate({ priority: p })} />
            </div>
            <button type="button" onClick={onClose} className="text-fg-faint hover:text-fg sm:hidden"><X className="size-5" /></button>
          </div>

          <label className="mb-3 block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">{t("stage")}</span>
            <select value={lead.stage_id ?? ""} onChange={(e) => patch.mutate({ stage_id: Number(e.target.value) })} className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm">
              {stages.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          {managers && (
            <label className="mb-3 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">{t("manager")}</span>
              <select value={lead.sales_manager_id ?? ""} onChange={(e) => patch.mutate({ sales_manager_id: Number(e.target.value) })} className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm">
                {managers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
          )}
          {TEXT_FIELDS.map((k) => (
            <label key={k} className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">{t(`f_${k}`)}</span>
              <input value={val(k)} onChange={set(k)} className="w-full rounded-md border border-border bg-surface px-3 py-2" />
            </label>
          ))}
          <label className="mb-3 block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">{t("f_note")}</span>
            <textarea value={val("note")} onChange={set("note")} rows={2} className="w-full resize-none rounded-md border border-border bg-surface px-3 py-2" />
          </label>

          <div className="mt-auto flex items-center gap-2 pt-2">
            <button type="button" disabled={!dirty || patch.isPending} onClick={() => patch.mutate(form)} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40">{t("save")}</button>
            {api.remove && (
              <button type="button" onClick={async () => { if (await confirmDialog(t("deleteLeadConfirm"), { danger: true })) { await api.remove!(leadId); onChanged?.(); onClose(); } }} className="inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-2 text-sm text-danger"><Trash2 className="size-4" /> {t("delete")}</button>
            )}
          </div>
        </div>

        {/* Right — chatter */}
        <div className="flex w-full flex-1 flex-col bg-surface-2/30">
          <header className="flex items-center justify-between border-b border-border px-4 py-3">
            <h3 className="text-sm font-semibold">{t("chatter")}</h3>
            <button type="button" onClick={onClose} className="text-fg-faint hover:text-fg"><X className="size-5" /></button>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {/* Open tasks (actionable) */}
            {lead.open_tasks.length > 0 && (
              <div className="space-y-2 rounded-lg border border-accent/30 bg-accent-soft/20 p-2.5">
                <p className="text-xs font-semibold text-accent">{t("openTasks")}</p>
                {lead.open_tasks.map((tk) => {
                  if (!tk) return null;
                  const TIcon = tk.type ? TYPE_ICON[tk.type.icon] ?? ClipboardList : ClipboardList;
                  return (
                    <div key={tk.id} className="flex items-center gap-2 rounded-md border border-border bg-surface p-2">
                      <TIcon className="size-4 shrink-0 text-accent" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm">{tk.title}</p>
                        {tk.due_at && <p className="tnum text-[11px] text-fg-faint">{tk.due_at.slice(0, 16).replace("T", " ")}</p>}
                      </div>
                      <button type="button" title={t("complete")} onClick={() => taskAct.mutate(() => api.completeTask(tk.id))} className="text-accent hover:opacity-70"><Check className="size-4" /></button>
                      <button type="button" title={t("editTask")} onClick={() => editTask(tk.id, tk.title)} className="text-fg-faint hover:text-fg"><Pencil className="size-3.5" /></button>
                      <button type="button" title={t("cancelTask")} onClick={() => cancelTask(tk.id)} className="text-fg-faint hover:text-danger"><XCircle className="size-4" /></button>
                    </div>
                  );
                })}
              </div>
            )}

            {lead.events.length === 0 && <p className="py-8 text-center text-sm text-fg-faint">{t("noEvents")}</p>}
            {[...lead.events].reverse().map((e) => {
              const style = EVENT_STYLE[e.kind] ?? EVENT_STYLE.field;
              const Icon = style.icon;
              return (
                <div key={e.id} className="flex gap-3">
                  <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", style.tone)}><Icon className="size-3.5" /></span>
                  <div className="min-w-0 flex-1 rounded-lg border border-border bg-surface p-2.5">
                    <div className="flex items-center justify-between gap-2 text-xs text-fg-faint">
                      <span className="font-medium text-fg">{e.actor}</span>
                      <span className="tnum">{e.created_at.slice(0, 16).replace("T", " ")}</span>
                    </div>
                    <p className="mt-1 text-sm">
                      {e.kind === "field" || e.kind === "stage" ? (
                        <>
                          <span className="text-fg-muted">{t(`ev_${e.kind}` as "ev_note")}</span>{" "}
                          <span className="tnum">{e.text}</span>
                        </>
                      ) : (
                        <>
                          <span className="text-fg-muted">{t(`ev_${e.kind}` as "ev_note")}</span>
                          {e.text && <>: {e.text}</>}
                        </>
                      )}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Composer */}
          <div className="border-t border-border bg-surface p-3">
            <div className="mb-2 flex gap-2">
              {(["note", "task"] as const).map((c) => (
                <button key={c} type="button" onClick={() => setComposer(c)} className={cn("rounded-full px-3 py-1 text-xs font-medium", composer === c ? "bg-accent text-accent-fg" : "bg-surface-2 text-fg-muted")}>{t(c)}</button>
              ))}
            </div>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder={composer === "note" ? t("notePlaceholder") : t("taskPlaceholder")} className="w-full resize-none rounded-md border border-border bg-surface px-3 py-2 text-sm" />
            {composer === "task" && (
              <div className="mt-2 flex flex-wrap gap-2">
                <select value={typeId} onChange={(e) => setTypeId(e.target.value)} className="rounded-md border border-border bg-surface px-2 py-1.5 text-sm">
                  <option value="">{t("taskType")}</option>
                  {meta.task_types.map((tt) => <option key={tt.id} value={tt.id}>{tt.name}</option>)}
                </select>
                <input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm" />
              </div>
            )}
            <button
              type="button"
              disabled={(composer === "note" && text.trim().length < 2) || note.isPending || task.isPending}
              onClick={() => composer === "note" ? note.mutate(text.trim()) : task.mutate({ title: text.trim(), due: due || undefined, type: typeId ? Number(typeId) : undefined })}
              className="mt-2 w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
            >{t("send")}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
