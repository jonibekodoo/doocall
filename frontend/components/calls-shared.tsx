"use client";

/** Shared call-list pieces used by dashboard, calls, reports, my-calls. */

import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { useTranslations } from "next-intl";

import type { DashboardResponse } from "@/lib/api/types";
import {
  callOutcome,
  OUTCOME_CLASS,
  splitByDirection,
} from "@/lib/call-status";
import { cn } from "@/lib/utils";

/** Stacked direction bars: answered / missed (inbound unanswered) /
 * not reached (outbound unanswered). Inbound has no "not reached" and
 * outbound no "missed" by definition. */
export function directionBars(general: DashboardResponse["general"]) {
  const all = splitByDirection(general);
  return [
    {
      key: "all",
      answered: general.all.answered,
      missed: all.missed,
      notReached: all.notReached,
      total: general.all.total,
    },
    {
      key: "inbound",
      answered: general.inbound.answered,
      missed: general.inbound.missed,
      notReached: 0,
      total: general.inbound.total,
    },
    {
      key: "outbound",
      answered: general.outbound.answered,
      missed: 0,
      notReached: general.outbound.missed,
      total: general.outbound.total,
    },
  ];
}

/** "Javob berilgan" / "O'tkazib yuborilgan" (inbound) / "Javob bermadi"
 * (outbound) — the one status badge used across the cabinet. */
export function CallStatusBadge({
  status,
  direction,
  className,
}: {
  status: string;
  direction: string;
  className?: string;
}) {
  const t = useTranslations("calls");
  const outcome = callOutcome(status, direction);
  const label =
    outcome === "answered"
      ? t("answered")
      : outcome === "missed"
        ? t("missed")
        : t("notReached");
  return (
    <span
      data-testid="call-status"
      data-outcome={outcome}
      className={cn(
        "inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium",
        OUTCOME_CLASS[outcome],
        className,
      )}
    >
      {label}
    </span>
  );
}

export function DirectionIcon({ direction }: { direction: string }) {
  return direction === "inbound" ? (
    <ArrowDownLeft className="size-3.5 text-accent" aria-label="inbound" />
  ) : (
    <ArrowUpRight className="size-3.5 text-fg-muted" aria-label="outbound" />
  );
}
