"use client";

/** Tiny dependency-light sparkline (SVG polyline on the DS tokens). */

export function Sparkline({
  data,
  height = 48,
}: {
  data: number[];
  height?: number;
}) {
  if (!data.length) return null;
  const width = 300;
  const max = Math.max(...data, 1);
  const step = width / Math.max(data.length - 1, 1);
  const points = data
    .map(
      (value, index) =>
        `${(index * step).toFixed(1)},${(height - (value / max) * (height - 4) - 2).toFixed(1)}`,
    )
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-12 w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label="sparkline"
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
