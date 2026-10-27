/** Call outcome wording — the owner's rule:
 *  - inbound (client → manager) not answered  → "missed" (O'tkazib yuborilgan / Пропущен)
 *  - outbound (manager → client) not answered → "not reached" (Javob bermadi / Не дозвонился)
 * One place for the rule so every screen labels and colours calls the same. */

export type CallOutcome = "answered" | "missed" | "not_reached";

/** Per call: answered, or — by direction — missed vs not reached. Any
 * non-answered status (no_answer, busy, failed) counts as unanswered. */
export function callOutcome(status: string, direction: string): CallOutcome {
  if (status === "answered") return "answered";
  return direction === "inbound" ? "missed" : "not_reached";
}

/** Badge colours: answered green, missed red, not reached amber. */
export const OUTCOME_CLASS: Record<CallOutcome, string> = {
  answered: "bg-accent-soft text-accent",
  missed: "bg-danger/10 text-danger",
  not_reached: "bg-warning/15 text-warning",
};

/** Counts that may carry the new split (missed_inbound / not_reached). */
export interface UnansweredCounts {
  missed: number;
  missed_inbound?: number | null;
  not_reached?: number | null;
}

/** Split an aggregate's unanswered count. With the new backend fields the
 * split is exact; without them the old `missed` (all unanswered) is shown as
 * missed and not-reached is unknown (null). */
export function splitUnanswered(row: UnansweredCounts): {
  missed: number;
  notReached: number | null;
} {
  if (
    typeof row.missed_inbound === "number" ||
    typeof row.not_reached === "number"
  ) {
    return {
      missed: row.missed_inbound ?? 0,
      notReached: row.not_reached ?? 0,
    };
  }
  return { missed: row.missed, notReached: null };
}

/** The same split for a {all, inbound, outbound} block: without the new
 * fields it is exact anyway — inbound unanswered = missed, outbound
 * unanswered = not reached. */
export function splitByDirection(block: {
  all: UnansweredCounts;
  inbound: UnansweredCounts;
  outbound: UnansweredCounts;
}): { missed: number; notReached: number } {
  const exact = splitUnanswered(block.all);
  if (exact.notReached !== null) {
    return { missed: exact.missed, notReached: exact.notReached };
  }
  return { missed: block.inbound.missed, notReached: block.outbound.missed };
}
