"use client";

/** Full notifications page: every message (unread highlighted); clicking
 * an unread one marks it read; "mark all" clears the badge. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck } from "lucide-react";
import { useTranslations } from "next-intl";

import { KIND_COLOR } from "@/components/shell/NotificationsBell";
import {
  fetchNotifications,
  markNotificationRead,
  markNotificationsRead,
} from "@/lib/api/endpoints";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function NotificationsPage() {
  const t = useTranslations("notifications");
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
  });
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  const readOne = useMutation({
    mutationFn: (id: number) => markNotificationRead(id),
    onSuccess: invalidate,
  });
  const readAll = useMutation({
    mutationFn: markNotificationsRead,
    onSuccess: invalidate,
  });

  const rows = data?.notifications ?? [];

  return (
    <div className="max-w-2xl" data-testid="notifications-page">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        {(data?.unread ?? 0) > 0 && (
          <button
            type="button"
            data-testid="mark-all-read"
            onClick={() => readAll.mutate()}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-2"
          >
            <CheckCheck className="size-4" /> {t("markAll")}
          </button>
        )}
      </div>

      <div className="rounded-lg border border-border bg-surface">
        <ul className="divide-y divide-border">
          {isPending && (
            <li className="px-4 py-6">
              <div className="h-4 animate-pulse rounded bg-surface-3" />
            </li>
          )}
          {rows.map((note) => (
            <li key={note.id}>
              <button
                type="button"
                data-testid={`page-note-${note.id}`}
                onClick={() => !note.is_read && readOne.mutate(note.id)}
                className={cn(
                  "flex w-full items-start gap-3 px-4 py-3 text-left",
                  note.is_read
                    ? "opacity-60"
                    : "cursor-pointer bg-accent-soft/20 hover:bg-surface-2",
                )}
              >
                <span
                  className={cn(
                    "mt-1.5 size-2.5 shrink-0 rounded-full",
                    KIND_COLOR[note.kind] ?? "bg-fg-faint",
                    note.is_read && "opacity-40",
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span
                    className={cn(
                      "block text-sm leading-snug",
                      !note.is_read && "font-semibold",
                    )}
                  >
                    {note.message}
                  </span>
                  <span className="tnum mt-0.5 block text-xs text-fg-faint">
                    {note.created_at.slice(0, 16).replace("T", " ")}
                    {note.amount_uzs != null &&
                      ` · ${formatUzs(note.amount_uzs)} UZS`}
                  </span>
                </span>
                {!note.is_read && (
                  <span className="mt-1 rounded-full bg-danger px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">
                    {t("newBadge")}
                  </span>
                )}
              </button>
            </li>
          ))}
          {!isPending && rows.length === 0 && (
            <li className="px-4 py-10 text-center text-sm text-fg-faint">
              {t("empty")}
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
