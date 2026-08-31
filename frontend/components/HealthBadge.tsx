import { cn } from "@/lib/utils";

/** Trivial component used by the Vitest smoke test and the landing page. */
export function HealthBadge({ label = "healthy" }: { label?: string }) {
  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium",
        "border-green-600 text-green-700",
      )}
    >
      {label}
    </span>
  );
}
