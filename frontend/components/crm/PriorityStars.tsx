"use client";

import { Star } from "lucide-react";

import { cn } from "@/lib/utils";

export function PriorityStars({
  value,
  onChange,
  px = 16,
}: {
  value: number;
  onChange?: (v: number) => void;
  px?: number;
}) {
  return (
    <span className="inline-flex items-center gap-0.5">
      {[1, 2, 3].map((n) => (
        <button
          key={n}
          type="button"
          disabled={!onChange}
          onClick={() => onChange?.(value === n ? 0 : n)}
          className={cn(!onChange && "cursor-default")}
          aria-label={`priority ${n}`}
        >
          <Star
            size={px}
            className={n <= value ? "fill-warning text-warning" : "text-fg-faint"}
          />
        </button>
      ))}
    </span>
  );
}
