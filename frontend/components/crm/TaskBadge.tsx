"use client";

import { useTranslations } from "next-intl";

import type { TaskState } from "@/lib/api/sales";
import { cn } from "@/lib/utils";

export function TaskBadge({ state }: { state: TaskState }) {
  const t = useTranslations("crmui");
  const map: Record<TaskState["kind"], { tone: string; label: string }> = {
    none: { tone: "bg-surface-3 text-fg-faint", label: t("tb_none") },
    nodue: { tone: "bg-accent-soft text-accent", label: t("tb_nodue") },
    today: { tone: "bg-warning/15 text-warning", label: t("tb_today") },
    left: { tone: "bg-accent-soft text-accent", label: t("tb_left", { n: state.days }) },
    overdue: { tone: "bg-danger/10 text-danger", label: t("tb_overdue", { n: state.days }) },
  };
  const s = map[state.kind] ?? map.none;
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", s.tone)}>
      {s.label}
    </span>
  );
}
