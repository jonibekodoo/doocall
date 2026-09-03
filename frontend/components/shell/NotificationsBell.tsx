"use client";

/** Cabinet bell: shows ONLY unread billing notifications. Clicking one
 * marks it read; the footer links to the full notifications page. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  fetchNotifications,
  markNotificationRead,
} from "@/lib/api/endpoints";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

export const KIND_COLOR: Record<string, string> = {
  charge_settled: "bg-accent",
  payment_received: "bg-accent",
  payment_requested: "bg-accent",
  tariff_changed: "bg-warning",
  payment_due: "bg-warning",
  blocked: "bg-danger",
};

export function NotificationsBell() {
  const t = useTranslations("notifications");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    refetchInterval: 60_000,
  });
  const readOne = useMutation({
    mutationFn: (id: number) => markNotificationRead(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const unreadRows = (data?.notifications ?? []).filter(
    (note) => !note.is_read,
  );
  const unread = data?.unread ?? 0;

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        data-testid="bell-btn"
        aria-label={t("title")}
        onClick={() => setOpen((value) => !value)}
        className="relative grid size-8 place-items-center rounded-md text-fg-muted hover:bg-surface-2"
      >
        <Bell className="size-4" />
        {unread > 0 && (
          <span
            data-testid="bell-badge"
            className="absolute -right-0.5 -top-0.5 grid min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-bold leading-4 text-white"
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 z-30 w-80 overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
          <p className="border-b border-border px-3 py-2 text-sm font-semibold">
            {t("title")}
          </p>
          <ul className="max-h-96 divide-y divide-border overflow-y-auto">
            {unreadRows.map((note) => (
              <li key={note.id}>
                <button
                  type="button"
                  data-testid={`note-${note.id}`}
                  onClick={() => readOne.mutate(note.id)}
                  className="flex w-full items-start gap-2 px-3 py-2.5 text-left hover:bg-surface-2"
                >
                  <span
                    className={cn(
                      "mt-1.5 size-2 shrink-0 rounded-full",
                      KIND_COLOR[note.kind] ?? "bg-fg-faint",
                    )}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm leading-snug">
                      {note.message}
                    </span>
                    <span className="tnum mt-0.5 block text-xs text-fg-faint">
                      {note.created_at.slice(0, 16).replace("T", " ")}
                      {note.amount_uzs != null &&
                        ` · ${formatUzs(note.amount_uzs)} UZS`}
                    </span>
                  </span>
                </button>
              </li>
            ))}
            {unreadRows.length === 0 && (
              <li className="px-3 py-8 text-center text-xs text-fg-faint">
                {t("noUnread")}
              </li>
            )}
          </ul>
          <Link
            href="/cabinet/notifications"
            onClick={() => setOpen(false)}
            data-testid="bell-view-all"
            className="block border-t border-border px-3 py-2 text-center text-sm font-semibold text-accent hover:bg-surface-2"
          >
            {t("viewAll")}
          </Link>
        </div>
      )}
    </div>
  );
}
