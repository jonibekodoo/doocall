"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, Coins, Wallet } from "lucide-react";
import { useTranslations } from "next-intl";

import { Pagination, usePagination } from "@/components/ui/Pagination";
import { fetchSalesNotifications, markSalesNotificationsRead } from "@/lib/api/sales";

const KIND_ICON: Record<string, React.ReactNode> = {
  balance_warning: <AlertTriangle className="size-4 text-warning" />,
  payout_status: <Wallet className="size-4 text-accent" />,
  commission: <Coins className="size-4 text-accent" />,
};

export default function SalesNotificationsPage() {
  const t = useTranslations("sales");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["sales-notifications"], queryFn: fetchSalesNotifications });

  const markRead = useMutation({
    mutationFn: markSalesNotificationsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales-notifications"] }),
  });

  const rows = data?.notifications ?? [];
  const paged = usePagination(rows);

  return (
    <div data-testid="sales-notifications">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("notifications")}</h1>
        {(data?.unread ?? 0) > 0 && (
          <button
            type="button"
            onClick={() => markRead.mutate()}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
          >
            {t("markAllRead")}
          </button>
        )}
      </div>
      <ul className="space-y-2">
        {paged.slice.map((n) => (
          <li
            key={n.id}
            className={
              n.is_read
                ? "flex items-start gap-3 rounded-xl border border-border bg-surface p-4"
                : "flex items-start gap-3 rounded-xl border border-accent/30 bg-accent-soft/30 p-4"
            }
          >
            <span className="mt-0.5">{KIND_ICON[n.kind] ?? <Bell className="size-4 text-fg-muted" />}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm">{n.message}</p>
              <p className="mt-1 text-xs text-fg-faint">{n.created_at.slice(0, 16).replace("T", " ")}</p>
            </div>
          </li>
        ))}
        {rows.length === 0 && (
          <li className="rounded-xl border border-border bg-surface px-4 py-10 text-center text-sm text-fg-faint">
            {t("noNotifications")}
          </li>
        )}
      </ul>
      <Pagination page={paged.page} pages={paged.pages} total={paged.total} start={paged.start} end={paged.end} onPage={paged.setPage} />
    </div>
  );
}
