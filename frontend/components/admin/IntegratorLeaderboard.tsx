"use client";

/** Integrator statistics dashboard: summary tiles, two headline rankings
 * (by companies onboarded and by payments), and a per-integrator table with
 * a company-status breakdown. */

import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  Coins,
  Handshake,
  TrendingUp,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import {
  type IntegratorStatRow,
  fetchIntegratorStats,
} from "@/lib/api/admin";
import { formatDuration, formatUzs } from "@/lib/format";

const MEDALS = ["🥇", "🥈", "🥉"];
const STATUS_COLORS: Record<string, string> = {
  active: "var(--accent)",
  trial: "var(--warning)",
  expired: "var(--danger-500)",
  suspended: "var(--fg-faint)",
};

function Tile({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center gap-2 text-xs font-medium uppercase text-fg-faint">
        <span className="text-accent">{icon}</span>
        {label}
      </div>
      <p className="tnum mt-1.5 text-xl font-bold">{value}</p>
    </div>
  );
}

/** A "top N" ranking card — horizontal bars, one metric. */
function RankCard({
  title,
  rows,
  metric,
  format,
  accent,
}: {
  title: string;
  rows: IntegratorStatRow[];
  metric: "companies" | "revenue_uzs";
  format: (n: number) => string;
  accent: string;
}) {
  const top = [...rows].sort((a, b) => b[metric] - a[metric]).slice(0, 5);
  const max = Math.max(1, ...top.map((r) => r[metric]));
  return (
    <section className="rounded-xl border border-border bg-surface shadow-sm">
      <header className="border-b border-border px-4 py-2.5 text-sm font-semibold">
        {title}
      </header>
      <ul className="space-y-3 p-4">
        {top.map((r, i) => (
          <li key={r.id} className="flex items-center gap-3">
            <span className="w-5 shrink-0 text-center text-sm">
              {i < 3 ? MEDALS[i] : <span className="text-fg-faint">{i + 1}</span>}
            </span>
            <Link
              href={`/admin/integrators/${r.id}`}
              className="w-28 shrink-0 truncate text-sm font-medium text-accent hover:underline"
            >
              {r.name}
            </Link>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(r[metric] / max) * 100}%`,
                  background: accent,
                }}
              />
            </div>
            <span className="tnum w-24 shrink-0 text-right text-sm font-semibold">
              {format(r[metric])}
            </span>
          </li>
        ))}
        {top.length === 0 && (
          <li className="py-6 text-center text-sm text-fg-faint">—</li>
        )}
      </ul>
    </section>
  );
}

/** Segmented status bar + counts for one integrator's companies. */
function StatusBar({
  breakdown,
  labels,
}: {
  breakdown: IntegratorStatRow["company_status"];
  labels: Record<string, string>;
}) {
  const order: Array<keyof IntegratorStatRow["company_status"]> = [
    "active",
    "trial",
    "expired",
    "suspended",
  ];
  const total = order.reduce((s, k) => s + breakdown[k], 0);
  if (total === 0) return <span className="text-fg-faint">—</span>;
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="flex h-2.5 w-24 overflow-hidden rounded-full bg-surface-2">
        {order.map((k) =>
          breakdown[k] > 0 ? (
            <div
              key={k}
              title={`${labels[k]}: ${breakdown[k]}`}
              style={{
                width: `${(breakdown[k] / total) * 100}%`,
                background: STATUS_COLORS[k],
              }}
            />
          ) : null,
        )}
      </div>
      <span className="tnum flex gap-1.5 text-xs">
        {order.map((k) =>
          breakdown[k] > 0 ? (
            <span key={k} style={{ color: STATUS_COLORS[k] }}>
              {breakdown[k]}
            </span>
          ) : null,
        )}
      </span>
    </div>
  );
}

export function IntegratorLeaderboard() {
  const t = useTranslations("admin");
  const { data, isPending } = useQuery({
    queryKey: ["a-integrator-stats"],
    queryFn: fetchIntegratorStats,
  });

  if (isPending) {
    return <div className="mb-5 h-48 animate-pulse rounded-xl bg-surface-2" />;
  }
  if (!data || data.integrators.length === 0) return null;

  const statusLabels = {
    active: t("integratorStats.stActive"),
    trial: t("integratorStats.stTrial"),
    expired: t("integratorStats.stExpired"),
    suspended: t("integratorStats.stSuspended"),
  };
  const byCompanies = [...data.integrators].sort(
    (a, b) => b.companies - a.companies,
  );

  return (
    <div className="mb-6 space-y-4" data-testid="integrator-leaderboard">
      {/* Summary tiles */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          icon={<Handshake className="size-4" />}
          label={t("integratorStats.integrators")}
          value={String(data.totals.integrators)}
        />
        <Tile
          icon={<Building2 className="size-4" />}
          label={t("integratorStats.companies")}
          value={String(data.totals.companies)}
        />
        <Tile
          icon={<TrendingUp className="size-4" />}
          label={t("integratorStats.revenue")}
          value={`${formatUzs(data.totals.revenue_uzs)} UZS`}
        />
        <Tile
          icon={<Coins className="size-4" />}
          label={t("integratorStats.cashback")}
          value={`${formatUzs(data.totals.cashback_uzs)} UZS`}
        />
      </div>

      {/* Two headline rankings */}
      <div className="grid gap-4 lg:grid-cols-2">
        <RankCard
          title={t("integratorStats.topByCompanies")}
          rows={data.integrators}
          metric="companies"
          format={(n) => String(n)}
          accent="var(--accent)"
        />
        <RankCard
          title={t("integratorStats.topByRevenue")}
          rows={data.integrators}
          metric="revenue_uzs"
          format={(n) => `${formatUzs(n)}`}
          accent="var(--accent-700)"
        />
      </div>

      {/* Full table with company-status breakdown */}
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
        <header className="border-b border-border px-4 py-2.5 text-sm font-semibold">
          {t("integratorStats.allIntegrators")}
        </header>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
              <tr>
                <th className="px-3 py-2 text-left">№</th>
                <th className="px-3 py-2 text-left">
                  {t("integratorStats.name")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("integratorStats.colCompanies")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("integratorStats.colStatus")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("integratorStats.colRevenue")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("integratorStats.colCashback")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("integratorStats.colCallTime")}
                </th>
              </tr>
            </thead>
            <tbody>
              {byCompanies.map((r, index) => (
                <tr
                  key={r.id}
                  className="border-t border-border hover:bg-surface-2/60"
                >
                  <td className="px-3 py-2.5 text-fg-faint">{index + 1}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <span className="grid size-8 shrink-0 place-items-center overflow-hidden rounded-md border border-border bg-surface-2 text-xs font-bold text-fg-muted">
                        {r.logo_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={r.logo_url}
                            alt=""
                            className="size-full object-contain"
                          />
                        ) : (
                          (r.company_name || r.name).slice(0, 1).toUpperCase()
                        )}
                      </span>
                      <span className="min-w-0">
                        <Link
                          href={`/admin/integrators/${r.id}`}
                          className="block truncate font-medium text-accent hover:underline"
                        >
                          {r.name}
                        </Link>
                        <span className="block truncate text-xs text-fg-faint">
                          {r.company_name || r.referral_code}
                        </span>
                      </span>
                    </div>
                  </td>
                  <td className="tnum px-3 py-2.5 text-right font-semibold">
                    {r.companies}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBar
                      breakdown={r.company_status}
                      labels={statusLabels}
                    />
                  </td>
                  <td className="tnum px-3 py-2.5 text-right">
                    {formatUzs(r.revenue_uzs)}
                  </td>
                  <td className="tnum px-3 py-2.5 text-right">
                    {formatUzs(r.cashback_uzs)}
                  </td>
                  <td className="tnum px-3 py-2.5 text-right text-fg-muted">
                    {formatDuration(r.call_seconds)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Legend */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-4 py-2 text-xs text-fg-muted">
          {(["active", "trial", "expired", "suspended"] as const).map((k) => (
            <span key={k} className="flex items-center gap-1.5">
              <span
                className="size-2.5 rounded-full"
                style={{ background: STATUS_COLORS[k] }}
              />
              {statusLabels[k]}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
