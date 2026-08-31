"use client";

/** A.5 Accruals — filterable ledger, totals footer, CSV export. */

import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { fetchPartnerAccruals, fetchPartnerCompanies } from "@/lib/api/partner";
import { formatUzs } from "@/lib/format";

export default function PartnerAccrualsPage() {
  const t = useTranslations("partner");
  const [status, setStatus] = useState("");
  const [company, setCompany] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const params = `?status=${status}&company=${company}${dateFrom ? `&date_from=${dateFrom}` : ""}`;
  const { data, isPending } = useQuery({
    queryKey: ["p-accruals", status, company, dateFrom],
    queryFn: () => fetchPartnerAccruals(params),
  });
  const { data: companies } = useQuery({
    queryKey: ["p-companies"],
    queryFn: fetchPartnerCompanies,
  });

  const rows = data?.accruals ?? [];
  const total = rows
    .filter((r) => r.status !== "reversed")
    .reduce((sum, r) => sum + r.amount_uzs, 0);

  const exportCsv = () => {
    const header = "company,created_at,percent,amount_uzs,status";
    const lines = rows.map(
      (r) =>
        `"${r.company}",${r.created_at},${r.percent},${r.amount_uzs},${r.status}`,
    );
    const blob = new Blob(["﻿" + [header, ...lines].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "accruals.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <div data-testid="partner-accruals">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("accruals")}</h1>
        <button
          type="button"
          data-testid="accruals-csv"
          onClick={exportCsv}
          className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-surface-2"
        >
          <Download className="size-3.5" /> {t("exportCsv")}
        </button>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label="status"
          className="rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        >
          <option value="">—</option>
          <option value="accrued">accrued</option>
          <option value="paid_out">paid_out</option>
          <option value="reversed">reversed</option>
        </select>
        <select
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          aria-label="company"
          className="rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        >
          <option value="">—</option>
          {(companies?.companies ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          aria-label="from"
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">—</th>
              <th className="px-3 py-2 text-left">{t("date")}</th>
              <th className="px-3 py-2 text-right">%</th>
              <th className="px-3 py-2 text-right">UZS</th>
              <th className="px-3 py-2 text-left">{t("status")}</th>
            </tr>
          </thead>
          <tbody>
            {isPending
              ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={5} className="px-3 py-2.5">
                      <div className="h-3.5 animate-pulse rounded bg-surface-3" />
                    </td>
                  </tr>
                ))
              : rows.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="px-3 py-2.5">{r.company}</td>
                    <td className="tnum px-3 py-2.5 text-xs">
                      {r.created_at.slice(0, 10)}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">{r.percent}</td>
                    <td className="tnum px-3 py-2.5 text-right font-medium text-accent">
                      {formatUzs(r.amount_uzs)}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">
                        {r.status}
                      </span>
                    </td>
                  </tr>
                ))}
          </tbody>
          {rows.length > 0 && (
            <tfoot className="border-t-2 border-border bg-surface-2 font-semibold">
              <tr>
                <td className="px-3 py-2" colSpan={3}>
                  {t("totalFooter")}
                </td>
                <td
                  className="tnum px-3 py-2 text-right"
                  data-testid="accruals-total"
                >
                  {formatUzs(total)}
                </td>
                <td />
              </tr>
            </tfoot>
          )}
        </table>
        {!isPending && rows.length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-fg-faint">
            {t("noAccruals")}
          </p>
        )}
      </div>
    </div>
  );
}
