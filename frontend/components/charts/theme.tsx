"use client";

/** Chart theme wrapper for Recharts — answered=accent teal, missed=warm red.
 * All chart components read these tokens so every chart matches the DS. */

import { ResponsiveContainer } from "recharts";

export const CHART_COLORS = {
  answered: "var(--accent)",
  missed: "var(--danger-500)",
  inbound: "var(--accent-400)",
  outbound: "var(--accent-700)",
  grid: "var(--border)",
  text: "var(--fg-muted)",
} as const;

export const chartAxisProps = {
  stroke: "var(--fg-faint)",
  fontSize: 11,
  tickLine: false,
  axisLine: { stroke: "var(--border)" },
} as const;

export const chartTooltipStyle = {
  contentStyle: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-md)",
    boxShadow: "var(--shadow-md)",
    fontSize: 12,
    color: "var(--fg)",
  },
  cursor: { fill: "var(--surface-2)" },
} as const;

export function ChartContainer({
  height = 260,
  children,
}: {
  height?: number;
  children: React.ReactElement;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <ResponsiveContainer width="100%" height={height}>
        {children}
      </ResponsiveContainer>
    </div>
  );
}
