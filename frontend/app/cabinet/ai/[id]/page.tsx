"use client";

/** One Kotib AI analysis: score header (+ our own call audio), criteria with
 * expandable comments, transcript as chat bubbles, client portrait. */

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ExternalLink,
  ShieldAlert,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";

import { CallAudioButton } from "@/components/CallAudioButton";
import { DirectionIcon } from "@/components/calls-shared";
import { fetchAiAnalysis, type AiAnalysisDetail } from "@/lib/api/endpoints";
import { formatDuration, formatPhone } from "@/lib/format";
import { cn } from "@/lib/utils";

import { formatAnswer, parseTranscript, ScoreBadge } from "../ai-shared";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Section({
  title,
  testId,
  children,
}: {
  title: string;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      className="rounded-lg border border-border bg-surface p-4"
    >
      <h2 className="mb-3 text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Criteria({ analysis }: { analysis: AiAnalysisDetail }) {
  const t = useTranslations("ai");
  if (!analysis.prompt_scores.length) {
    return <p className="text-sm text-fg-faint">{t("noCriteria")}</p>;
  }
  return (
    <ul className="divide-y divide-border">
      {analysis.prompt_scores.map((item) => (
        <li
          key={item.key}
          data-testid={`ai-criterion-${item.key}`}
          className="py-2.5"
        >
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center gap-3">
              <span className="flex-1 text-sm font-medium">{item.name}</span>
              {item.is_violation && (
                <span className="inline-flex items-center gap-1 rounded-full bg-danger/10 px-2 py-0.5 text-xs font-semibold text-danger">
                  <AlertTriangle className="size-3" /> {t("violation")}
                </span>
              )}
              {item.score === null ? (
                <span className="text-xs text-fg-faint">—</span>
              ) : (
                <ScoreBadge score={item.score} />
              )}
              {item.comment_html && (
                <span className="text-xs text-fg-faint group-open:rotate-180">
                  ▾
                </span>
              )}
            </summary>
            {item.comment_html && (
              <div
                data-testid={`ai-comment-${item.key}`}
                className="mt-2 rounded-md bg-surface-2 px-3 py-2 text-sm leading-relaxed text-fg [&_a]:text-accent [&_a]:underline [&_b]:font-semibold [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5"
                // Sanitised by the backend with an allowlist; the ONLY raw HTML
                // rendered anywhere on this page.
                dangerouslySetInnerHTML={{ __html: item.comment_html }}
              />
            )}
          </details>
        </li>
      ))}
    </ul>
  );
}

function Transcript({ text }: { text: string }) {
  const t = useTranslations("ai");
  const turns = parseTranscript(text);
  if (!turns.length) {
    return <p className="text-sm text-fg-faint">{t("noTranscript")}</p>;
  }
  return (
    <div className="space-y-2">
      {turns.map((turn, index) => (
        <div
          key={index}
          data-testid="ai-turn"
          data-speaker={turn.speaker}
          className={cn(
            "flex",
            turn.speaker === "client" ? "justify-end" : "justify-start",
          )}
        >
          <div
            className={cn(
              "max-w-[80%] rounded-2xl px-3.5 py-2 text-sm",
              turn.speaker === "agent" && "rounded-bl-sm bg-surface-2",
              turn.speaker === "client" && "rounded-br-sm bg-accent-soft",
              turn.speaker === "other" && "bg-surface-2 text-fg-muted",
            )}
          >
            {turn.speaker !== "other" && (
              <p className="mb-0.5 text-[11px] font-semibold uppercase tracking-wide text-fg-faint">
                {turn.speaker === "agent"
                  ? t("speakerAgent")
                  : t("speakerClient")}
              </p>
            )}
            <p className="whitespace-pre-line">{turn.text}</p>
            {turn.time && (
              <p className="tnum mt-0.5 text-right text-[11px] text-fg-faint">
                {turn.time}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function Portrait({ analysis }: { analysis: AiAnalysisDetail }) {
  const t = useTranslations("ai");
  const data = analysis.client_data;
  if (!data || (!data.summary && !data.answers.length)) {
    return <p className="text-sm text-fg-faint">{t("noPortrait")}</p>;
  }
  return (
    <div className="space-y-3">
      {data.summary && (
        <p className="text-sm leading-relaxed">{data.summary}</p>
      )}
      {data.answers.length > 0 && (
        <table className="w-full text-sm" data-testid="ai-answers">
          <tbody>
            {data.answers.map((answer) => (
              <tr key={answer.key} className="border-t border-border">
                <th className="w-1/2 py-2 pr-3 text-left font-normal text-fg-muted">
                  {answer.name}
                </th>
                <td className="py-2">
                  {formatAnswer(answer.value, { yes: t("yes"), no: t("no") })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function AiAnalysisDetailPage() {
  const t = useTranslations("ai");
  const tCalls = useTranslations("calls");
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { data, isPending, isError } = useQuery({
    queryKey: ["ai-analysis", id],
    queryFn: () => fetchAiAnalysis(id),
    enabled: Number.isFinite(id),
  });

  const back = (
    <Link
      href="/cabinet/ai"
      className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
    >
      <ArrowLeft className="size-4" /> {t("back")}
    </Link>
  );

  if (isPending) {
    return (
      <div data-testid="ai-detail-loading" className="space-y-3">
        {back}
        <div className="h-28 animate-pulse rounded-lg bg-surface-3" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="space-y-3">
        {back}
        <p className="text-sm text-fg-muted">{t("notFound")}</p>
      </div>
    );
  }

  const analysis = data.analysis;
  return (
    <div className="max-w-4xl space-y-4" data-testid="ai-detail">
      {back}

      <header className="flex flex-wrap items-start gap-4 rounded-lg border border-border bg-surface p-4">
        <ScoreBadge score={analysis.final_score} size="lg" />
        <div className="min-w-0 flex-1 space-y-1 text-sm">
          <p className="font-semibold">{formatDateTime(analysis.start_time)}</p>
          <p className="text-fg-muted">
            {t("operator")}: {analysis.operator?.full_name ?? "—"} ·{" "}
            {t("client")}:{" "}
            <span className="tnum">{formatPhone(analysis.phone)}</span>
          </p>
          {analysis.call && (
            <p className="flex items-center gap-1.5 text-fg-muted">
              <DirectionIcon direction={analysis.call.direction} />
              {tCalls("duration")}:{" "}
              <span className="tnum">
                {formatDuration(analysis.call.duration)}
              </span>
              <Link
                href={`/cabinet/calls?call=${analysis.call.id}`}
                data-testid="ai-open-call"
                className="ml-2 inline-flex items-center gap-1 font-medium text-accent hover:underline"
              >
                <ExternalLink className="size-3.5" /> {t("openCall")}
              </Link>
            </p>
          )}
          {analysis.summary && (
            <p className="pt-1 leading-relaxed">{analysis.summary}</p>
          )}
          {!analysis.signature_verified && (
            <p
              data-testid="ai-unsigned"
              className="inline-flex items-center gap-1.5 text-xs text-warning"
            >
              <ShieldAlert className="size-3.5" /> {t("unsigned")}
            </p>
          )}
        </div>
        {analysis.call?.has_audio && (
          // Our own stored recording — never Kotib's audio URL.
          <div className="shrink-0" data-testid="ai-audio">
            <CallAudioButton callId={analysis.call.id} />
          </div>
        )}
      </header>

      <Section title={t("criteria")} testId="ai-criteria">
        <Criteria analysis={analysis} />
      </Section>
      <Section title={t("transcript")} testId="ai-transcript">
        <Transcript text={analysis.conversation_text} />
      </Section>
      <Section title={t("portrait")} testId="ai-portrait">
        <Portrait analysis={analysis} />
      </Section>
      <p className="text-xs text-fg-faint">
        {t("receivedAt")}: {formatDateTime(analysis.received_at)}
      </p>
    </div>
  );
}
