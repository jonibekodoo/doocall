/** Shared bits of the AI Tahlil (Kotib) screens and the Calls AI badge. */

import Link from "next/link";

import { cn } from "@/lib/utils";

/** ≥80 green, 50–79 amber, <50 red (Kotib scores can be negative). */
export function scoreTone(score: number): "good" | "mid" | "bad" {
  if (score >= 80) return "good";
  if (score >= 50) return "mid";
  return "bad";
}

const TONE_CLASS = {
  good: "bg-accent-soft text-accent",
  mid: "bg-warning/15 text-warning",
  bad: "bg-danger/10 text-danger",
} as const;

export function ScoreBadge({
  score,
  size = "sm",
  className,
}: {
  score: number;
  size?: "sm" | "lg";
  className?: string;
}) {
  return (
    <span
      data-testid="ai-score"
      data-tone={scoreTone(score)}
      className={cn(
        "tnum inline-flex items-center justify-center rounded-full font-semibold",
        size === "lg"
          ? "min-w-14 px-3 py-1 text-lg"
          : "min-w-9 px-2 py-0.5 text-xs",
        TONE_CLASS[scoreTone(score)],
        className,
      )}
    >
      {Math.round(score)}
    </span>
  );
}

/** Small "AI 87" chip for a call row, linking to its analysis. */
export function CallAiBadge({
  analysisId,
  score,
  title,
}: {
  analysisId: number;
  score: number;
  title: string;
}) {
  return (
    <Link
      href={`/cabinet/ai/${analysisId}`}
      title={title}
      data-testid={`call-ai-${analysisId}`}
      className={cn(
        "tnum rounded px-1.5 py-0.5 text-[10px] font-semibold hover:opacity-80",
        TONE_CLASS[scoreTone(score)],
      )}
    >
      AI {Math.round(score)}
    </Link>
  );
}

export interface TranscriptTurn {
  speaker: "agent" | "client" | "other";
  text: string;
  time: string | null;
}

const TURN_RE =
  /^(agent|client)\s*:\s*([\s\S]*?)\s*(?:\(?(\d{1,2}:\d{2}(?::\d{2})?)\)?)?\s*$/i;

/** Kotib's conversation_text: turns separated by blank lines, each
 * "Agent: … 00:12" / "Client: … 01:05" (trailing mm:ss optional). */
export function parseTranscript(text: string): TranscriptTurn[] {
  return text
    .split(/\r?\n\s*\r?\n/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const match = TURN_RE.exec(block);
      if (!match) return { speaker: "other" as const, text: block, time: null };
      return {
        speaker: match[1].toLowerCase() as "agent" | "client",
        text: match[2].trim(),
        time: match[3] ?? null,
      };
    });
}

/** Client-portrait answer value → display text. */
export function formatAnswer(
  value: unknown,
  labels: { yes: string; no: string },
): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? labels.yes : labels.no;
  if (Array.isArray(value)) {
    const items = value
      .filter((item) => item !== null && item !== undefined && item !== "")
      .map((item) => formatAnswer(item, labels));
    return items.length ? items.join(", ") : "—";
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
