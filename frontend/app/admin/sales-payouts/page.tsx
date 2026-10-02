"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Pagination, usePagination } from "@/components/ui/Pagination";
import { useToastStore } from "@/components/ui/Toast";
import { fetchAdminSalesPayouts, salesPayoutAction } from "@/lib/api/admin";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = {
  pending: "bg-warning/15 text-warning",
  approved: "bg-accent-soft text-accent",
  paid: "bg-accent-soft text-accent",
  rejected: "bg-danger/10 text-danger",
};

export default function AdminSalesPayoutsPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({ queryKey: ["a-sales-payouts"], queryFn: () => fetchAdminSalesPayouts() });
  const paged = usePagination(data?.payouts ?? []);

  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "approve" | "reject" | "mark-paid" }) =>
      salesPayoutAction(id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-sales-payouts"] });
      useToastStore.getState().push({ kind: "success", text: t("salesPay.updated") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  return (
    <div data-testid="admin-sales-payouts">
      <h1 className="mb-4 text-xl font-semibold">{t("salesPay.title")}</h1>
      <div className="space-y-3">
        {isPending ? (
          Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-2" />)
        ) : (data?.payouts ?? []).length === 0 ? (
          <p className="rounded-xl border border-border bg-surface px-4 py-10 text-center text-sm text-fg-faint">
            {t("salesPay.empty")}
          </p>
        ) : (
          paged.slice.map((p) => (
            <div key={p.id} className="rounded-xl border border-border bg-surface p-4 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{p.sales_manager}</span>
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_TONE[p.status] ?? "bg-surface-3")}>
                      {t(`salesM.payout_${p.status}` as "salesM.payout_pending")}
                    </span>
                  </div>
                  <p className="tnum mt-1 text-lg font-bold text-accent">{formatUzs(p.amount_uzs)} UZS</p>
                  <p className="tnum mt-1 text-xs text-fg-faint">
                    {t("salesM.bank_card")}: {p.bank.card || "—"} · MFO: {p.bank.mfo || "—"} · INN: {p.bank.inn || "—"} ·{" "}
                    {t("salesM.bank_transit")}: {p.bank.transit || "—"}
                  </p>
                  <p className="mt-1 text-xs text-fg-faint">{p.requested_at.slice(0, 16).replace("T", " ")}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {p.status === "pending" && (
                    <>
                      <button type="button" onClick={() => act.mutate({ id: p.id, action: "approve" })} className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg">
                        {t("salesPay.approve")}
                      </button>
                      <button type="button" onClick={() => act.mutate({ id: p.id, action: "reject" })} className="rounded-md border border-danger/40 px-3 py-1.5 text-xs text-danger">
                        {t("salesPay.reject")}
                      </button>
                    </>
                  )}
                  {p.status === "approved" && (
                    <button type="button" onClick={() => act.mutate({ id: p.id, action: "mark-paid" })} className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg">
                      {t("salesPay.markPaid")}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
      <Pagination
        page={paged.page}
        pages={paged.pages}
        total={paged.total}
        start={paged.start}
        end={paged.end}
        onPage={paged.setPage}
      />
    </div>
  );
}
