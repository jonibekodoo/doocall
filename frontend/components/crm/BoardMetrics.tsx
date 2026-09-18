"use client";

import { useTranslations } from "next-intl";

import type { BoardStats } from "@/lib/api/sales";

export function BoardMetrics({ stats }: { stats?: BoardStats }) {
  const t = useTranslations("crmui");
  const tiles: { key: keyof BoardStats; label: string; tone: string }[] = [
    { key: "today_tasks", label: t("m_today_tasks"), tone: "text-accent" },
    { key: "no_task_leads", label: t("m_no_task"), tone: "text-warning" },
    { key: "overdue_tasks", label: t("m_overdue"), tone: "text-danger" },
    { key: "leads_today", label: t("m_leads_today"), tone: "text-fg" },
    { key: "leads_yesterday", label: t("m_leads_yesterday"), tone: "text-fg" },
  ];
  return (
    <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {tiles.map((tile) => (
        <div key={tile.key} className="rounded-lg border border-border bg-surface px-3 py-2">
          <p className="truncate text-[11px] font-medium uppercase text-fg-faint">{tile.label}</p>
          <p className={`tnum text-xl font-bold ${tile.tone}`}>{stats ? stats[tile.key] : "…"}</p>
        </div>
      ))}
    </div>
  );
}
