"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";

import { DocLangEditor } from "@/components/admin/DocLangEditor";
import { useToastStore } from "@/components/ui/Toast";
import { type DocContents, fetchOffer, saveOffer } from "@/lib/api/admin";

export default function AdminOfferPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["a-offer"], queryFn: fetchOffer });
  const [drafts, setDrafts] = useState<DocContents | null>(null);
  const onChange = useCallback((next: DocContents) => setDrafts(next), []);

  const save = useMutation({
    mutationFn: () => saveOffer(drafts as DocContents),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["a-offer"] });
      useToastStore.getState().push({ kind: "success", text: t("offerPage.saved") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  return (
    <div className="max-w-3xl" data-testid="admin-offer">
      <h1 className="mb-1 text-xl font-semibold">{t("offerPage.title")}</h1>
      <p className="mb-4 text-sm text-fg-muted">
        {t("offerPage.hint")} {data && <span className="tnum">v{data.version}</span>}
      </p>
      <DocLangEditor initial={data?.contents} onChange={onChange} />
      <button
        type="button"
        disabled={drafts === null || save.isPending}
        onClick={() => save.mutate()}
        className="mt-3 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
      >
        {t("offerPage.save")}
      </button>
      <p className="mt-2 text-xs text-fg-faint">{t("offerPage.note")}</p>
    </div>
  );
}
