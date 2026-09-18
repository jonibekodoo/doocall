"use client";

/** Public legal pages required by card acquirers (Visa/Mastercard):
 * Privacy policy · Terms & conditions · Refund/cancellation policy.
 * Each is edited with the rich-text editor and published at /legal/<kind>. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { RichTextEditor } from "@/components/ui/RichTextEditor";
import { useToastStore } from "@/components/ui/Toast";
import { fetchLegal, saveLegal, type LegalKind } from "@/lib/api/admin";
import { cn } from "@/lib/utils";

const KINDS: LegalKind[] = ["privacy", "terms", "refund"];

/** Legacy plain text → HTML once (mirrors the offer page). */
function toEditorHtml(raw: string): string {
  if (!raw) return "";
  if (/<[a-z][\s\S]*>/i.test(raw)) return raw;
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .split("\n")
    .map((line) => `<p>${line || "<br>"}</p>`)
    .join("");
}

function LegalEditor({ kind }: { kind: LegalKind }) {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["a-legal", kind], queryFn: () => fetchLegal(kind) });
  const [content, setContent] = useState<string | null>(null);

  useEffect(() => {
    if (data && content === null) setContent(toEditorHtml(data.content));
  }, [data, content]);

  const save = useMutation({
    mutationFn: () => saveLegal(kind, content ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-legal", kind] });
      useToastStore.getState().push({ kind: "success", text: t("legalPage.saved") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-fg-muted">
        <span>
          {t("legalPage.hint")}{" "}
          {data && <span className="tnum">v{data.version}</span>}
        </span>
        <a
          href={`/legal/${kind}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-accent hover:underline"
        >
          <ExternalLink className="size-3.5" /> /legal/{kind}
        </a>
      </div>
      <RichTextEditor value={content ?? ""} onChange={setContent} />
      <button
        type="button"
        disabled={content === null || save.isPending}
        onClick={() => save.mutate()}
        className="mt-3 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
      >
        {t("legalPage.save")}
      </button>
    </div>
  );
}

export default function AdminLegalPage() {
  const t = useTranslations("admin");
  const [kind, setKind] = useState<LegalKind>("privacy");

  return (
    <div className="max-w-4xl" data-testid="admin-legal">
      <h1 className="mb-1 text-xl font-semibold">{t("legalPage.title")}</h1>
      <p className="mb-4 text-sm text-fg-muted">{t("legalPage.subtitle")}</p>
      <div className="mb-4 inline-flex rounded-lg border border-border bg-surface p-1">
        {KINDS.map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setKind(k)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
              kind === k ? "bg-accent text-accent-fg" : "text-fg-muted hover:text-fg",
            )}
          >
            {t(`legalPage.tab_${k}`)}
          </button>
        ))}
      </div>
      {/* keyed so each tab keeps its own editor state */}
      <LegalEditor key={kind} kind={kind} />
    </div>
  );
}
