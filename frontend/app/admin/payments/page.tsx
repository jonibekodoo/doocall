"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import {
  Area,
  AreaChart,
  Cell,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  CHART_COLORS,
  ChartBox,
  ReportCard,
  chartAxisProps,
  chartTooltipStyle,
} from "@/components/charts/theme";
import { confirmDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import {
  approvePayment,
  fetchAdminPayments,
  fetchPaymentStats,
  refundPayment,
} from "@/lib/api/admin";
import { cn } from "@/lib/utils";
import { formatUzs, providerLabel } from "@/lib/format";

const STATUS_TONE: Record<string, string> = {
  approved: "bg-accent-soft text-accent",
  pending: "bg-warning/15 text-warning",
  rejected: "bg-danger/10 text-danger",
  failed: "bg-danger/10 text-danger",
};
const PROVIDER_COLORS = [
  CHART_COLORS.answered,
  CHART_COLORS.inbound,
  CHART_COLORS.outbound,
  CHART_COLORS.missed,
];

function PaymentStats() {
  const t = useTranslations("admin");
  const { data } = useQuery({
    queryKey: ["a-payment-stats"],
    queryFn: fetchPaymentStats,
  });
  if (!data) {
    return <div className="mb-5 h-40 animate-pulse rounded-xl bg-surface-2" />;
  }
  const series = data.revenue_series.map((v, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (data.revenue_series.length - 1 - i));
    return { d: `${d.getMonth() + 1}/${d.getDate()}`, v };
  });
  const providerData = data.by_provider.map((p, i) => ({
    name: providerLabel(p.provider),
    value: p.amount_uzs,
    color: PROVIDER_COLORS[i % PROVIDER_COLORS.length],
  }));

  return (
    <div className="mb-5 space-y-4">
      {/* Totals */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <p className="text-xs font-medium uppercase text-fg-faint">
            {t("payments.totalRevenue")}
          </p>
          <p className="tnum mt-1 text-2xl font-bold text-accent">
            {formatUzs(data.total_uzs)}{" "}
            <span className="text-sm font-medium text-fg-muted">UZS</span>
          </p>
          <p className="tnum mt-1 text-xs text-fg-muted">
            {data.total_count} {t("payments.paymentsCount")}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
          <p className="text-xs font-medium uppercase text-fg-faint">
            {t("payments.pendingSum")}
          </p>
          <p className="tnum mt-1 text-2xl font-bold text-warning">
            {formatUzs(data.pending_uzs)}{" "}
            <span className="text-sm font-medium text-fg-muted">UZS</span>
          </p>
          <p className="tnum mt-1 text-xs text-fg-muted">
            {data.pending_count} {t("payments.paymentsCount")}
          </p>
        </div>
        {/* By status chips */}
        <div className="rounded-xl border border-border bg-surface p-4 shadow-sm sm:col-span-2">
          <p className="mb-2 text-xs font-medium uppercase text-fg-faint">
            {t("payments.byStatus")}
          </p>
          <div className="flex flex-wrap gap-2">
            {data.by_status.map((s) => (
              <span
                key={s.status}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs font-medium",
                  STATUS_TONE[s.status] ?? "bg-surface-3",
                )}
              >
                {s.status}: <b className="tnum">{s.count}</b> ·{" "}
                {formatUzs(s.amount_uzs)}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Charts: provider donut + 30-day revenue area */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ReportCard title={t("payments.byProvider")}>
          {providerData.length === 0 ? (
            <p className="py-10 text-center text-sm text-fg-faint">—</p>
          ) : (
            <>
              <ChartBox height={220}>
                <PieChart>
                  <Tooltip
                    {...chartTooltipStyle}
                    formatter={(v: number) => [`${formatUzs(v)} UZS`, ""]}
                  />
                  <Pie
                    data={providerData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius="60%"
                    outerRadius="88%"
                    paddingAngle={2}
                    strokeWidth={0}
                  >
                    {providerData.map((p) => (
                      <Cell key={p.name} fill={p.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ChartBox>
              <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs">
                {providerData.map((p) => (
                  <span key={p.name} className="flex items-center gap-1.5">
                    <span
                      className="size-2.5 rounded-full"
                      style={{ background: p.color }}
                    />
                    {p.name}:{" "}
                    <b className="tnum">{formatUzs(p.value)} UZS</b>
                  </span>
                ))}
              </div>
            </>
          )}
        </ReportCard>

        <ReportCard title={t("payments.revenue30")}>
          <ChartBox height={220}>
            <AreaChart data={series}>
              <defs>
                <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_COLORS.answered} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={CHART_COLORS.answered} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis dataKey="d" {...chartAxisProps} interval={6} />
              <YAxis
                {...chartAxisProps}
                width={44}
                tickFormatter={(v: number) =>
                  v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)
                }
              />
              <Tooltip
                {...chartTooltipStyle}
                formatter={(v: number) => [`${formatUzs(v)} UZS`, ""]}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke={CHART_COLORS.answered}
                strokeWidth={2.5}
                fill="url(#revFill)"
                dot={false}
                activeDot={{ r: 4 }}
              />
            </AreaChart>
          </ChartBox>
        </ReportCard>
      </div>
    </div>
  );
}

export default function AdminPaymentsPage() {
  const t = useTranslations("admin");
  const [provider, setProvider] = useState("");
  const [status, setStatus] = useState("");
  const queryClient = useQueryClient();
  const params = `?provider=${provider}&status=${status}`;
  const { data, isPending } = useQuery({
    queryKey: ["a-payments", provider, status],
    queryFn: () => fetchAdminPayments(params),
  });

  const approve = useMutation({
    mutationFn: approvePayment,
    onSuccess: (body) => {
      queryClient.invalidateQueries({ queryKey: ["a-payments"] });
      queryClient.invalidateQueries({ queryKey: ["a-payment-stats"] });
      const note =
        body.cashback_accrued_uzs > 0
          ? t("payments.cashbackNote", {
              amount: formatUzs(body.cashback_accrued_uzs),
            })
          : "";
      useToastStore.getState().push({
        kind: "success",
        text: `${t("payments.approvedToast")}${note}`,
      });
    },
  });
  const refund = useMutation({
    mutationFn: refundPayment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-payments"] });
      queryClient.invalidateQueries({ queryKey: ["a-payment-stats"] });
      useToastStore
        .getState()
        .push({ kind: "success", text: t("payments.refundMarked") });
    },
  });

  return (
    <div data-testid="admin-payments">
      <h1 className="mb-4 text-xl font-semibold">{t("payments.title")}</h1>
      <PaymentStats />
      <div className="mb-3 flex gap-2">
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          aria-label={t("payments.provider")}
          className="rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        >
          <option value="">{t("payments.allProviders")}</option>
          <option value="manual">Manual</option>
          <option value="payme">Payme</option>
          <option value="click">Click</option>
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label={t("common.status")}
          className="rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
        >
          <option value="">{t("common.allStatuses")}</option>
          <option value="pending">{t("payments.statusPending")}</option>
          <option value="approved">{t("payments.statusApproved")}</option>
          <option value="rejected">{t("payments.statusRejected")}</option>
        </select>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">{t("common.company")}</th>
              <th className="px-3 py-2 text-left">{t("payments.provider")}</th>
              <th className="px-3 py-2 text-right">{t("common.amount")}</th>
              <th className="px-3 py-2 text-right">{t("payments.cashback")}</th>
              <th className="px-3 py-2 text-left">{t("common.status")}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {isPending
              ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={6} className="px-3 py-2.5">
                      <div className="h-3.5 animate-pulse rounded bg-surface-3" />
                    </td>
                  </tr>
                ))
              : (data?.payments ?? []).map((p) => (
                  <tr key={p.id} className="border-t border-border">
                    <td className="px-3 py-2.5">{p.company}</td>
                    <td className="px-3 py-2.5">{providerLabel(p.provider)}</td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {formatUzs(p.amount_uzs)}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right text-accent">
                      {p.cashback_uzs ? formatUzs(p.cashback_uzs) : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-xs">{p.status}</td>
                    <td className="px-3 py-2.5 text-right">
                      {p.status === "pending" && (
                        <button
                          type="button"
                          data-testid={`approve-${p.id}`}
                          onClick={async () =>
                            (await confirmDialog(
                              t("payments.confirmApprove", {
                                amount: formatUzs(p.amount_uzs),
                              }),
                            )) && approve.mutate(p.id)
                          }
                          className="rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-accent-fg"
                        >
                          {t("payments.approve")}
                        </button>
                      )}
                      {p.status === "approved" && (
                        <button
                          type="button"
                          onClick={async () =>
                            (await confirmDialog(t("payments.confirmRefund"), {
                              danger: true,
                            })) && refund.mutate(p.id)
                          }
                          className="rounded-md border border-danger/40 px-2.5 py-1 text-xs text-danger"
                        >
                          {t("payments.refund")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
        {!isPending && (data?.payments ?? []).length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-fg-faint">
            {t("payments.empty")}
          </p>
        )}
      </div>
    </div>
  );
}
