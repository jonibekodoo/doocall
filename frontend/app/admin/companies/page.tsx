"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  Hourglass,
  PauseCircle,
  TimerOff,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { type AdminCompanyStats, fetchAdminCompanies } from "@/lib/api/admin";
import { cn } from "@/lib/utils";

const STATUS_TONES: Record<string, string> = {
  active: "bg-accent-soft text-accent",
  trial: "bg-warning/15 text-warning",
  suspended: "bg-danger/10 text-danger",
};

/** Headline cards: one per status; clicking one filters the table below
 * (click again — or "all" — to clear). */
const STAT_CARDS: Array<{
  key: keyof AdminCompanyStats;
  filter: string;
  icon: typeof Building2;
  tone: string;
}> = [
  { key: "total", filter: "", icon: Building2, tone: "text-fg" },
  { key: "active", filter: "active", icon: CheckCircle2, tone: "text-accent" },
  { key: "trial", filter: "trial", icon: Hourglass, tone: "text-warning" },
  { key: "expired", filter: "expired", icon: TimerOff, tone: "text-danger" },
  { key: "suspended", filter: "suspended", icon: PauseCircle, tone: "text-danger" },
];

export default function AdminCompaniesPage() {
  const t = useTranslations("admin");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const params = `?q=${encodeURIComponent(q)}${status ? `&status=${status}` : ""}`;
  const { data, isPending } = useQuery({
    queryKey: ["a-companies", q, status],
    queryFn: () => fetchAdminCompanies(params),
  });
  const stats = data?.stats;

  return (
    <div data-testid="admin-companies">
      <h1 className="mb-4 text-xl font-semibold">{t("companies.title")}</h1>

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {STAT_CARDS.map(({ key, filter, icon: Icon, tone }) => {
          const selected = status === filter;
          return (
            <button
              key={key}
              type="button"
              data-testid={`companies-stat-${key}`}
              aria-pressed={selected}
              onClick={() => setStatus(selected && filter ? "" : filter)}
              className={cn(
                "flex items-center gap-3 rounded-lg border bg-surface px-3.5 py-3 text-left transition hover:bg-surface-2",
                selected
                  ? "border-accent ring-2 ring-accent/30"
                  : "border-border",
              )}
            >
              <Icon className={cn("size-5 shrink-0", tone)} />
              <span className="min-w-0">
                <span className="block truncate text-[11px] font-medium uppercase tracking-wide text-fg-muted">
                  {t(`companies.stat_${key}`)}
                </span>
                <span className={cn("tnum block text-xl font-semibold", tone)}>
                  {stats ? stats[key] : "—"}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="mb-3 flex gap-2">
        <input
          type="search"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder={t("common.searchPlaceholder")}
          className="w-64 rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          aria-label={t("common.status")}
          className="rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        >
          <option value="">{t("common.allStatuses")}</option>
          <option value="active">{t("companies.statusActive")}</option>
          <option value="trial">{t("companies.statusTrial")}</option>
          <option value="expired">{t("companies.statusExpired")}</option>
          <option value="suspended">{t("companies.statusSuspended")}</option>
        </select>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">№</th>
              <th className="px-3 py-2 text-left">{t("common.company")}</th>
              <th className="px-3 py-2 text-left">{t("companies.colPhone")}</th>
              <th className="px-3 py-2 text-left">{t("common.status")}</th>
              <th className="px-3 py-2 text-left">{t("companies.colEnds")}</th>
              <th className="px-3 py-2 text-right">
                {t("companies.colSeats")}
              </th>
              <th className="px-3 py-2 text-left">
                {t("companies.colAcquired")}
              </th>
              <th className="px-3 py-2 text-right">
                {t("companies.colIntegrations")}
              </th>
              <th className="px-3 py-2 text-left">
                {t("companies.colCreated")}
              </th>
            </tr>
          </thead>
          <tbody>
            {isPending
              ? Array.from({ length: 8 }).map((_, index) => (
                  <tr key={index}>
                    <td colSpan={9} className="px-3 py-2.5">
                      <div className="h-3.5 animate-pulse rounded bg-surface-3" />
                    </td>
                  </tr>
                ))
              : (data?.companies ?? []).map((company, index) => (
                  <tr
                    key={company.id}
                    className="border-t border-border hover:bg-surface-2/60"
                  >
                    <td className="px-3 py-2.5 text-fg-faint">{index + 1}</td>
                    <td className="px-3 py-2.5">
                      <Link
                        href={`/admin/companies/${company.id}`}
                        className="font-medium text-accent hover:underline"
                      >
                        {company.name}
                      </Link>
                    </td>
                    <td className="tnum px-3 py-2.5 text-xs text-fg-muted">
                      {company.phone ? (
                        <a
                          href={`tel:${company.phone.replace(/\s/g, "")}`}
                          className="hover:text-accent hover:underline"
                        >
                          {company.phone}
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          company.trial_expired
                            ? "bg-danger/10 text-danger"
                            : (STATUS_TONES[company.status] ?? "bg-surface-3"),
                        )}
                      >
                        {company.trial_expired
                          ? t("companies.statusExpired")
                          : t(
                              `companies.status${
                                company.status.charAt(0).toUpperCase() +
                                company.status.slice(1)
                              }` as "companies.statusActive",
                            )}
                      </span>
                    </td>
                    <td
                      className={cn(
                        "tnum px-3 py-2.5 text-xs",
                        company.trial_expired
                          ? "font-medium text-danger"
                          : "text-fg-muted",
                      )}
                    >
                      {(company.status === "trial"
                        ? company.trial_ends_at
                        : company.period_end
                      )?.slice(0, 10) ?? "—"}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {company.seats}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-fg-muted">
                      {company.acquired_via}
                      {company.integrator_id && (
                        <span
                          title={`Integrator #${company.integrator_id}`}
                          className="ml-1.5 rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent"
                        >
                          {company.integrator_name ?? `INT #${company.integrator_id}`}
                          {company.integrator_company && (
                            <span className="font-normal opacity-80">
                              {" "}· {company.integrator_company}
                            </span>
                          )}
                        </span>
                      )}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {company.integrations_count > 0 ? (
                        <span className="rounded bg-accent-soft px-1.5 py-0.5 text-xs font-semibold text-accent">
                          {company.integrations_count}
                        </span>
                      ) : (
                        <span className="text-fg-faint">0</span>
                      )}
                    </td>
                    <td className="tnum px-3 py-2.5 text-xs text-fg-muted">
                      {company.created_at.slice(0, 10)}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
        {!isPending && (data?.companies ?? []).length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-fg-faint">
            {t("common.nothingFound")}
          </p>
        )}
      </div>
    </div>
  );
}
