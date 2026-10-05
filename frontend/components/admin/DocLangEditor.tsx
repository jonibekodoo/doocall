"use client";

/** Rich-text editor for a document kept in three languages (uz / ru / en):
 * a language switch above one editor, each language with its own draft.
 * Shared by the public-offer and legal-pages admin screens. */

import { useEffect, useState } from "react";

import { RichTextEditor } from "@/components/ui/RichTextEditor";
import { DOC_LANGS, type DocContents, type DocLang } from "@/lib/api/admin";
import { cn } from "@/lib/utils";

const LANG_LABEL: Record<DocLang, string> = { uz: "O'zbekcha", ru: "Русский", en: "English" };

/** Legacy documents were stored as plain text — lift them into HTML once. */
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

export function DocLangEditor({
  initial,
  onChange,
}: {
  /** Server contents; the drafts are initialised from it once it arrives. */
  initial: DocContents | undefined;
  onChange: (drafts: DocContents) => void;
}) {
  const [lang, setLang] = useState<DocLang>("uz");
  const [drafts, setDrafts] = useState<DocContents | null>(null);

  useEffect(() => {
    if (initial && drafts === null) {
      const next = {
        uz: toEditorHtml(initial.uz),
        ru: toEditorHtml(initial.ru),
        en: toEditorHtml(initial.en),
      };
      setDrafts(next);
      onChange(next);
    }
  }, [initial, drafts, onChange]);

  const update = (value: string) => {
    if (!drafts) return;
    const next = { ...drafts, [lang]: value };
    setDrafts(next);
    onChange(next);
  };

  return (
    <div>
      <div className="mb-2 inline-flex rounded-lg border border-border bg-surface p-1" data-testid="doc-lang-tabs">
        {DOC_LANGS.map((code) => {
          const filled = Boolean(drafts?.[code]?.replace(/<[^>]*>/g, "").trim());
          return (
            <button
              key={code}
              type="button"
              onClick={() => setLang(code)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors",
                lang === code ? "bg-accent text-accent-fg" : "text-fg-muted hover:text-fg",
              )}
            >
              {LANG_LABEL[code]}
              {/* dot = this language still has no text */}
              {!filled && <span className="size-1.5 rounded-full bg-warning" />}
            </button>
          );
        })}
      </div>
      {/* keyed so switching language swaps the editor's content cleanly */}
      <RichTextEditor key={lang} value={drafts?.[lang] ?? ""} onChange={update} />
    </div>
  );
}
