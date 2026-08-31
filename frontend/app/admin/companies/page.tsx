"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { fetchAdminCompanies } from "@/lib/api/admin";
import { cn } from "@/lib/utils";

const STATUS_TONES: Record<string, string> = {
  active: "bg-accent-soft text-accent",
  trial: "bg-warning/15 text-warning",
  suspended: "bg-danger/10 text-danger",
};

export default function AdminCompaniesPage() {
  const t = useTranslations("admin");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const params = `?q=${encodeURIComponent(q)}${status ? `&status=${status}` : ""}`;
  const { data, isPending } = useQuery({
    queryKey: ["a-companies", q, status],
    queryFn: () => fetchAdminCompanies(params),
  });

  return (
    <div data-testid="admin-companies">
      <h1 className="mb-4 text-xl font-semibold">{t("companies.title")}</h1>
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
          <option value="suspended">{t("companies.statusSuspended")}</option>
        </select>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">{t("common.company")}</th>
              <th className="px-3 py-2 text-left">{t("common.status")}</th>
              <th className="px-3 py-2 text-right">
                {t("companies.colSeats")}
              </th>
              <th className="px-3 py-2 text-left">
                {t("companies.colAcquired")}
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
                    <td colSpan={5} className="px-3 py-2.5">
                      <div className="h-3.5 animate-pulse rounded bg-surface-3" />
                    </td>
                  </tr>
                ))
              : (data?.companies ?? []).map((company) => (
                  <tr
                    key={company.id}
                    className="border-t border-border hover:bg-surface-2/60"
                  >
                    <td className="px-3 py-2.5">
                      <Link
                        href={`/admin/companies/${company.id}`}
                        className="font-medium text-accent hover:underline"
                      >
                        {company.name}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          STATUS_TONES[company.status] ?? "bg-surface-3",
                        )}
                      >
                        {company.status}
                      </span>
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {company.seats}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-fg-muted">
                      {company.acquired_via}
                      {company.integrator_id && (
                        <span className="ml-1.5 rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent">
                          INT #{company.integrator_id}
                        </span>
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
