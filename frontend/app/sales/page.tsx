"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Building2, Coins, Handshake, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { Cell, Pie, PieChart, Tooltip } from "recharts";

import { ChartBox, ReportCard, chartTooltipStyle } from "@/components/charts/theme";
import { fetchSalesDashboard } from "@/lib/api/sales";
import { formatUzs } from "@/lib/format";

function Tile({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center gap-2 text-xs font-medium uppercase text-fg-faint">
        <span className="text-accent">{icon}</span>
        {label}
      </div>
      <p className="tnum mt-1.5 text-2xl font-bold">{value}</p>
      {sub && <p className="tnum mt-0.5 text-xs text-fg-muted">{sub}</p>}
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  active: "var(--accent)",
  trial: "var(--warning)",
  expired: "var(--danger-500)",
  suspended: "var(--fg-faint)",
};

export default function SalesDashboardPage() {
  const t = useTranslations("sales");
  const { data, isPending } = useQuery({
    queryKey: ["sales-dashboard"],
    queryFn: fetchSalesDashboard,
  });

  if (isPending || !data) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-2" />
        ))}
      </div>
    );
  }

  const donut = (["active", "trial", "expired", "suspended"] as const)
    .map((k) => ({ name: t(`st_${k}`), value: data.company_status[k], color: STATUS_COLORS[k] }))
    .filter((s) => s.value > 0);

  return (
    <div className="space-y-5" data-testid="sales-dashboard">
      <h1 className="text-xl font-semibold">{t("overview")}</h1>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile icon={<Handshake className="size-4" />} label={t("integrators")} value={String(data.integrators)} />
        <Tile icon={<Building2 className="size-4" />} label={t("companies")} value={String(data.companies)} />
        <Tile icon={<Users className="size-4" />} label={t("operators")} value={String(data.operators)} />
        <Tile
          icon={<Coins className="size-4" />}
          label={t("balance")}
          value={`${formatUzs(data.balance_uzs)} UZS`}
          sub={t("commissionPct", { p: data.commission_percent })}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ReportCard title={t("companyStatus")}>
          {donut.length === 0 ? (
            <p className="py-10 text-center text-sm text-fg-faint">—</p>
          ) : (
            <>
              <ChartBox height={220}>
                <PieChart>
                  <Tooltip {...chartTooltipStyle} formatter={(v: number) => [String(v), ""]} />
                  <Pie data={donut} dataKey="value" nameKey="name" innerRadius="60%" outerRadius="88%" paddingAngle={2} strokeWidth={0}>
                    {donut.map((s) => (
                      <Cell key={s.name} fill={s.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ChartBox>
              <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs">
                {donut.map((s) => (
                  <span key={s.name} className="flex items-center gap-1.5">
                    <span className="size-2.5 rounded-full" style={{ background: s.color }} />
                    {s.name}: <b className="tnum">{s.value}</b>
                  </span>
                ))}
              </div>
            </>
          )}
        </ReportCard>

        <ReportCard
          title={t("expiringTitle")}
          icon={<AlertTriangle className="size-4 text-warning" />}
        >
          {data.expiring_soon.length === 0 ? (
            <p className="py-10 text-center text-sm text-fg-faint">{t("expiringEmpty")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {data.expiring_soon.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="truncate">{c.name}</span>
                  <span
                    className={
                      c.days_left <= 1
                        ? "shrink-0 rounded-full bg-danger/10 px-2 py-0.5 text-xs font-semibold text-danger"
                        : "shrink-0 rounded-full bg-warning/15 px-2 py-0.5 text-xs font-semibold text-warning"
                    }
                  >
                    {t("daysLeft", { n: c.days_left })}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </ReportCard>
      </div>

      <p className="text-sm text-fg-muted">
        {t("lifetimeCommission")}: <b className="tnum">{formatUzs(data.lifetime_uzs)} UZS</b> ·{" "}
        <Link href="/sales/payouts" className="text-accent hover:underline">
          {t("payouts")}
        </Link>
      </p>
    </div>
  );
}
