"use client";

/** Cabinet bell: billing notifications (charge deducted, tariff change,
 * payment due, blocked). Polls each minute; opening marks all read. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import {
  fetchNotifications,
  markNotificationsRead,
} from "@/lib/api/endpoints";
import { formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const KIND_COLOR: Record<string, string> = {
  charge_settled: "bg-accent",
  payment_received: "bg-accent",
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
  const markRead = useMutation({
    mutationFn: markNotificationsRead,
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

  const unread = data?.unread ?? 0;

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        data-testid="bell-btn"
        aria-label={t("title")}
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next && unread > 0) markRead.mutate();
        }}
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
            {(data?.notifications ?? []).map((note) => (
              <li key={note.id} className="px-3 py-2.5">
                <div className="flex items-start gap-2">
                  <span
                    className={cn(
                      "mt-1.5 size-2 shrink-0 rounded-full",
                      KIND_COLOR[note.kind] ?? "bg-fg-faint",
                      note.is_read && "opacity-30",
                    )}
                  />
                  <div className="min-w-0">
                    <p className="text-sm leading-snug">{note.message}</p>
                    <p className="tnum mt-0.5 text-xs text-fg-faint">
                      {note.created_at.slice(0, 16).replace("T", " ")}
                      {note.amount_uzs != null &&
                        ` · ${formatUzs(note.amount_uzs)} UZS`}
                    </p>
                  </div>
                </div>
              </li>
            ))}
            {(data?.notifications ?? []).length === 0 && (
              <li className="px-3 py-8 text-center text-xs text-fg-faint">
                {t("empty")}
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
