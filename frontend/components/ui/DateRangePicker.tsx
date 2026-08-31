"use client";

/** Lightweight date-range control: two native date inputs + quick presets. */

import { useTranslations } from "next-intl";

export interface DateRange {
  from: string; // YYYY-MM-DD or ""
  to: string;
}

function daysAgoIso(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

export function DateRangePicker({
  value,
  onChange,
}: {
  value: DateRange;
  onChange: (range: DateRange) => void;
}) {
  const t = useTranslations("period");
  const today = daysAgoIso(0);

  const presets = [
    { key: "today", from: today },
    { key: "3d", from: daysAgoIso(3) },
    { key: "7d", from: daysAgoIso(7) },
  ] as const;

  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      data-testid="date-range"
    >
      {presets.map((preset) => {
        const active = value.from === preset.from && value.to === today;
        return (
          <button
            key={preset.key}
            type="button"
            onClick={() => onChange({ from: preset.from, to: today })}
            className={`rounded-full px-3 py-1.5 text-xs font-medium ${
              active
                ? "bg-accent text-accent-fg"
                : "border border-border text-fg-muted hover:bg-surface-2"
            }`}
          >
            {t(preset.key)}
          </button>
        );
      })}
      <input
        type="date"
        aria-label="from"
        value={value.from}
        onChange={(event) => onChange({ ...value, from: event.target.value })}
        className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs"
      />
      <span className="text-fg-faint">—</span>
      <input
        type="date"
        aria-label="to"
        value={value.to}
        onChange={(event) => onChange({ ...value, to: event.target.value })}
        className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs"
      />
    </div>
  );
}
