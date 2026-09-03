/** Shared admin-portal helpers (kept out of page files: Next.js
 * restricts extra page exports via the .next/types check). */

import { type AdminKpis } from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";

type Translator = (
  key: string,
  values?: Record<string, string | number>,
) => string;

export function kpiCards(kpis: AdminKpis, t: Translator) {
  return [
    {
      key: "companies",
      label: t("dashboard.companies"),
      value: kpis.companies.total,
      hint: t("dashboard.companiesHint", {
        active: kpis.companies.active,
        trial: kpis.companies.trial,
        suspended: kpis.companies.suspended,
      }),
    },
    {
      key: "mrr",
      label: "MRR",
      value: `${formatUzs(kpis.mrr_uzs)} UZS`,
      hint: null,
    },
    {
      key: "payments30",
      label: t("dashboard.payments30"),
      value: `${formatUzs(kpis.payments_30d_uzs)} UZS`,
      hint: null,
    },
    {
      key: "calls",
      label: t("dashboard.callsToday"),
      value: kpis.calls_today,
      hint: null,
    },
    {
      key: "integrators",
      label: t("dashboard.integrators"),
      value: kpis.integrators,
      hint: null,
    },
    {
      key: "pendingPayments",
      label: t("dashboard.pendingPayments"),
      value: kpis.pending_payments ?? 0,
      hint: null,
    },
    {
      key: "payouts",
      label: t("dashboard.payoutsQueue"),
      value: kpis.pending_payouts,
      hint: null,
    },
  ];
}

export function effectivePercentLabel(
  override: string | null,
  fallback: string,
  defaultSuffix = "(по умолчанию)",
): string {
  return override !== null
    ? `${override} (override)`
    : `${fallback} ${defaultSuffix}`;
}

export function cashbackExample(percent: number, amount = 100000): string {
  return `${formatUzs(amount)} UZS × ${percent}% = ${formatUzs(Math.round((amount * percent) / 100))} UZS`;
}
