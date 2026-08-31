"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import {
  approvePayment,
  fetchAdminPayments,
  refundPayment,
} from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";

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
      useToastStore
        .getState()
        .push({ kind: "success", text: t("payments.refundMarked") });
    },
  });

  return (
    <div data-testid="admin-payments">
      <h1 className="mb-4 text-xl font-semibold">{t("payments.title")}</h1>
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
                    <td className="px-3 py-2.5 capitalize">{p.provider}</td>
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
                          onClick={() =>
                            window.confirm(
                              t("payments.confirmApprove", {
                                amount: formatUzs(p.amount_uzs),
                              }),
                            ) && approve.mutate(p.id)
                          }
                          className="rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-accent-fg"
                        >
                          {t("payments.approve")}
                        </button>
                      )}
                      {p.status === "approved" && (
                        <button
                          type="button"
                          onClick={() =>
                            window.confirm(t("payments.confirmRefund")) &&
                            refund.mutate(p.id)
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
