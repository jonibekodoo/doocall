"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { fetchAudit } from "@/lib/api/admin";

export default function AdminAuditPage() {
  const t = useTranslations("admin");
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const params = `?action=${encodeURIComponent(action)}${dateFrom ? `&date_from=${dateFrom}` : ""}`;
  const { data, isPending } = useQuery({
    queryKey: ["a-audit", action, dateFrom],
    queryFn: () => fetchAudit(params),
  });

  return (
    <div data-testid="admin-audit">
      <h1 className="mb-4 text-xl font-semibold">{t("audit.title")}</h1>
      <div className="mb-3 flex gap-2">
        <input
          type="search"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder={t("audit.filterPlaceholder")}
          data-testid="audit-filter"
          className="w-72 rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          aria-label={t("audit.fromDate")}
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>
      <ul
        className="divide-y divide-border rounded-lg border border-border bg-surface"
        data-testid="audit-list"
      >
        {isPending
          ? Array.from({ length: 8 }).map((_, i) => (
              <li key={i} className="px-4 py-2.5">
                <div className="h-3.5 animate-pulse rounded bg-surface-3" />
              </li>
            ))
          : (data?.entries ?? []).map((entry) => (
              <li
                key={entry.id}
                className="flex items-center gap-3 px-4 py-2 text-sm"
              >
                <code className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">
                  {entry.action}
                </code>
                <span className="min-w-0 flex-1 truncate text-xs text-fg-muted">
                  {entry.company ?? "—"} · {entry.actor ?? t("audit.system")}
                </span>
                <span className="tnum shrink-0 text-xs text-fg-faint">
                  {entry.created_at.slice(0, 16).replace("T", " ")}
                </span>
              </li>
            ))}
        {!isPending && (data?.entries ?? []).length === 0 && (
          <li className="px-4 py-10 text-center text-sm text-fg-faint">
            {t("audit.empty")}
          </li>
        )}
      </ul>
    </div>
  );
}
