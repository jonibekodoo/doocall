"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { RichTextEditor } from "@/components/ui/RichTextEditor";
import { useToastStore } from "@/components/ui/Toast";
import { fetchOffer, saveOffer } from "@/lib/api/admin";

/** Legacy offers were stored as plain text — lift them into HTML once. */
function toEditorHtml(raw: string): string {
  if (/<[a-z][\s\S]*>/i.test(raw)) return raw;
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .split("\n")
    .map((line) => `<p>${line || "<br>"}</p>`)
    .join("");
}

export default function AdminOfferPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["a-offer"], queryFn: fetchOffer });
  const [content, setContent] = useState<string | null>(null);

  useEffect(() => {
    if (data && content === null) setContent(toEditorHtml(data.content));
  }, [data, content]);

  const save = useMutation({
    mutationFn: () => saveOffer(content ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-offer"] });
      useToastStore.getState().push({ kind: "success", text: t("offerPage.saved") });
    },
  });

  return (
    <div className="max-w-3xl" data-testid="admin-offer">
      <h1 className="mb-1 text-xl font-semibold">{t("offerPage.title")}</h1>
      <p className="mb-4 text-sm text-fg-muted">
        {t("offerPage.hint")} {data && <span className="tnum">v{data.version}</span>}
      </p>
      <RichTextEditor value={content ?? ""} onChange={setContent} />
      <button
        type="button"
        disabled={content === null || save.isPending}
        onClick={() => save.mutate()}
        className="mt-3 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
      >
        {t("offerPage.save")}
      </button>
      <p className="mt-2 text-xs text-fg-faint">{t("offerPage.note")}</p>
    </div>
  );
}
