"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import { fetchAdminPayouts, payoutAction } from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";

export default function AdminPayoutsPage() {
  const t = useTranslations("admin");
  const [status, setStatus] = useState("pending");
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["a-payouts", status],
    queryFn: () => fetchAdminPayouts(status ? `?status=${status}` : ""),
  });
  const act = useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: number;
      action: "approve" | "reject" | "mark-paid";
    }) => payoutAction(id, action),
    onSuccess: (body) => {
      queryClient.invalidateQueries({ queryKey: ["a-payouts"] });
      useToastStore.getState().push({
        kind: "success",
        text: t("payouts.statusToast", { status: body.status }),
      });
    },
  });

  return (
    <div data-testid="admin-payouts">
      <h1 className="mb-4 text-xl font-semibold">{t("payouts.title")}</h1>
      <select
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        aria-label={t("common.status")}
        className="mb-3 rounded-md border border-border bg-surface px-2.5 py-2 text-sm"
      >
        <option value="pending">{t("payouts.statusPending")}</option>
        <option value="approved">{t("payouts.statusApproved")}</option>
        <option value="paid">{t("payouts.statusPaid")}</option>
        <option value="rejected">{t("payouts.statusRejected")}</option>
        <option value="">{t("common.all")}</option>
      </select>
      <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
        {isPending
          ? Array.from({ length: 4 }).map((_, i) => (
              <li key={i} className="px-4 py-3">
                <div className="h-4 animate-pulse rounded bg-surface-3" />
              </li>
            ))
          : (data?.payouts ?? []).map((payout) => (
              <li
                key={payout.id}
                className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm"
              >
                <span className="min-w-32 flex-1 font-medium">
                  {payout.integrator}
                </span>
                <span className="tnum font-semibold">
                  {formatUzs(payout.amount_uzs)} UZS
                </span>
                <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs">
                  {payout.status}
                </span>
                <span className="tnum max-w-52 truncate text-xs text-fg-faint">
                  {Object.values(payout.payout_details).join(" · ") ||
                    t("payouts.noDetails")}
                </span>
                <span className="flex gap-1.5">
                  {payout.status === "pending" && (
                    <>
                      <button
                        type="button"
                        data-testid={`payout-approve-${payout.id}`}
                        onClick={() =>
                          act.mutate({ id: payout.id, action: "approve" })
                        }
                        className="rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-accent-fg"
                      >
                        {t("payouts.approve")}
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          act.mutate({ id: payout.id, action: "reject" })
                        }
                        className="rounded-md border border-danger/40 px-2.5 py-1 text-xs text-danger"
                      >
                        {t("payouts.reject")}
                      </button>
                    </>
                  )}
                  {payout.status === "approved" && (
                    <button
                      type="button"
                      data-testid={`payout-paid-${payout.id}`}
                      onClick={() =>
                        act.mutate({ id: payout.id, action: "mark-paid" })
                      }
                      className="rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-accent-fg"
                    >
                      {t("payouts.markPaid")}
                    </button>
                  )}
                </span>
              </li>
            ))}
        {!isPending && (data?.payouts ?? []).length === 0 && (
          <li className="px-4 py-10 text-center text-sm text-fg-faint">
            {t("payouts.empty")}
          </li>
        )}
      </ul>
    </div>
  );
}
