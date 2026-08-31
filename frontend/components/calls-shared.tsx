"use client";

/** Shared call-list pieces used by dashboard, calls, reports, my-calls. */

import { ArrowDownLeft, ArrowUpRight } from "lucide-react";

import type { DashboardResponse } from "@/lib/api/types";

export function directionBars(general: DashboardResponse["general"]) {
  return [
    {
      key: "all",
      answered: general.all.answered,
      missed: general.all.missed,
      total: general.all.total,
    },
    {
      key: "inbound",
      answered: general.inbound.answered,
      missed: general.inbound.missed,
      total: general.inbound.total,
    },
    {
      key: "outbound",
      answered: general.outbound.answered,
      missed: general.outbound.missed,
      total: general.outbound.total,
    },
  ];
}

export function DirectionIcon({ direction }: { direction: string }) {
  return direction === "inbound" ? (
    <ArrowDownLeft className="size-3.5 text-accent" aria-label="inbound" />
  ) : (
    <ArrowUpRight className="size-3.5 text-fg-muted" aria-label="outbound" />
  );
}
