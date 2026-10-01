"use client";

/** "Going offline within 3 days" list shared by the partner, sales and admin
 * dashboards: trial about to end or prepaid balance about to run out. */

import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import type { ExpiringCompany } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function ExpiringCompanies({
  rows,
  hrefFor,
  showIntegrator = false,
  className,
}: {
  rows: ExpiringCompany[];
  /** Link target for a row; omit to render plain names. */
  hrefFor?: (row: ExpiringCompany) => string;
  /** Admin view: name the integrator next to the company. */
  showIntegrator?: boolean;
  className?: string;
}) {
  const t = useTranslations("common.expiring");
  const urgent = rows.length > 0;
  return (
    <section
      className={cn(
        "rounded-lg border bg-surface",
        urgent ? "border-warning/50" : "border-border",
        className,
      )}
      data-testid="expiring-companies"
    >
      <p className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-sm font-semibold">
        <AlertTriangle className={cn("size-4", urgent ? "text-warning" : "text-fg-faint")} />
        {t("title")}
        {urgent && (
          <span className="tnum ml-auto rounded-full bg-warning/15 px-2 py-0.5 text-xs font-semibold text-warning">
            {rows.length}
          </span>
        )}
      </p>
      <ul className="divide-y divide-border">
        {rows.map((c) => (
          <li key={`${c.reason}-${c.id}`} className="flex items-center gap-3 px-4 py-2.5 text-sm">
            <span className="min-w-0 flex-1">
              {hrefFor ? (
                <Link href={hrefFor(c)} className="block truncate font-medium text-accent hover:underline">
                  {c.name}
                </Link>
              ) : (
                <span className="block truncate font-medium">{c.name}</span>
              )}
              {showIntegrator && c.integrator && (
                <span className="block truncate text-xs text-fg-faint">{c.integrator}</span>
              )}
            </span>
            <span className="hidden text-xs text-fg-muted sm:inline">
              {t(c.reason === "trial" ? "trial" : "balance")}
            </span>
            <span className="tnum text-xs text-fg-faint">{c.ends_on}</span>
            <span
              className={cn(
                "tnum shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold",
                c.days_left <= 1 ? "bg-danger/10 text-danger" : "bg-warning/15 text-warning",
              )}
            >
              {c.days_left === 0 ? t("today") : t("days", { n: c.days_left })}
            </span>
          </li>
        ))}
        {rows.length === 0 && (
          <li className="px-4 py-5 text-center text-xs text-fg-faint">{t("none")}</li>
        )}
      </ul>
    </section>
  );
}
