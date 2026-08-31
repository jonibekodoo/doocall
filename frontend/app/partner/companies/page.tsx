"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { fetchPartnerCompanies } from "@/lib/api/partner";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const TONES: Record<string, string> = {
  active: "bg-accent-soft text-accent",
  trial: "bg-warning/15 text-warning",
  suspended: "bg-danger/10 text-danger",
};

export default function PartnerCompaniesPage() {
  const t = useTranslations("partner");
  const { data, isPending } = useQuery({
    queryKey: ["p-companies"],
    queryFn: fetchPartnerCompanies,
  });

  return (
    <div data-testid="partner-companies">
      <h1 className="mb-4 text-xl font-semibold">{t("companies")}</h1>
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">—</th>
              <th className="px-3 py-2 text-left">{t("status")}</th>
              <th className="px-3 py-2 text-right">{t("operators")}</th>
              <th className="px-3 py-2 text-right">{t("accruedFrom")}</th>
              <th className="px-3 py-2 text-left">—</th>
            </tr>
          </thead>
          <tbody>
            {isPending
              ? Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={5} className="px-3 py-2.5">
                      <div className="h-3.5 animate-pulse rounded bg-surface-3" />
                    </td>
                  </tr>
                ))
              : (data?.companies ?? []).map((c) => (
                  <tr
                    key={c.id}
                    className="border-t border-border hover:bg-surface-2/60"
                  >
                    <td className="px-3 py-2.5">
                      <Link
                        href={`/partner/companies/${c.id}`}
                        className="font-medium text-accent hover:underline"
                      >
                        {c.name}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          TONES[c.status] ?? "bg-surface-3",
                        )}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">{c.seats}</td>
                    <td className="tnum px-3 py-2.5 text-right text-accent">
                      {formatUzs(c.my_cashback_uzs)}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-fg-faint">
                      {c.acquired_via}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
        {!isPending && (data?.companies ?? []).length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-fg-faint">
            {t("noCompanies")}
          </p>
        )}
      </div>
    </div>
  );
}
