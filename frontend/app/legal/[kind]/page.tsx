"use client";

/** Public legal page: /legal/privacy · /legal/terms · /legal/refund.
 * Content is admin-authored HTML, sanitised server-side on save. */

import { ArrowLeft, PhoneCall } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

const KINDS = ["privacy", "terms", "refund"] as const;
type Kind = (typeof KINDS)[number];

type Doc = { content: string; version: number; updated_at: string };

export default function LegalPage() {
  const t = useTranslations("legal");
  const params = useParams<{ kind: string }>();
  const kind = (KINDS as readonly string[]).includes(params.kind)
    ? (params.kind as Kind)
    : null;
  const [doc, setDoc] = useState<Doc | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    if (!kind) {
      setState("error");
      return;
    }
    let alive = true;
    fetch(`/api/public/legal/${kind}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body: Doc) => {
        if (!alive) return;
        setDoc(body);
        setState("ready");
      })
      .catch(() => alive && setState("error"));
    return () => {
      alive = false;
    };
  }, [kind]);

  const title = kind ? t(kind) : t("notFound");

  return (
    <div className="min-h-screen bg-bg">
      <header className="mx-auto flex max-w-4xl items-center justify-between px-6 py-5">
        <Link href="/" className="flex items-center gap-2 font-[family-name:var(--font-display)] text-lg font-semibold">
          <span className="grid size-8 place-items-center rounded-md bg-accent text-accent-fg">
            <PhoneCall className="size-4" />
          </span>
          dooCall
        </Link>
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg">
          <ArrowLeft className="size-4" /> {t("back")}
        </Link>
      </header>

      <main className="mx-auto max-w-4xl px-6 pb-16">
        <h1 className="mb-2 text-3xl font-bold">{title}</h1>
        {doc && (
          <p className="tnum mb-8 text-xs text-fg-faint">
            {t("updated")}: {doc.updated_at.slice(0, 10)} · v{doc.version}
          </p>
        )}

        {state === "loading" && <div className="h-40 animate-pulse rounded-lg bg-surface-2" />}
        {state === "error" && <p className="text-sm text-fg-faint">{t("notFound")}</p>}
        {state === "ready" && doc && (
          doc.content ? (
            <article
              className="text-[15px] leading-relaxed text-fg [&_h1]:mb-3 [&_h1]:mt-6 [&_h1]:text-2xl [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:mt-6 [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:mt-4 [&_h3]:text-lg [&_h3]:font-semibold [&_p]:mb-3 [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_a]:text-accent [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_blockquote]:text-fg-muted"
              // Sanitised server-side (allow-list) before storage.
              dangerouslySetInnerHTML={{ __html: doc.content }}
            />
          ) : (
            <p className="text-sm text-fg-faint">{t("empty")}</p>
          )
        )}
      </main>
    </div>
  );
}
