"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, CreditCard, FileText, ImageIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useToastStore } from "@/components/ui/Toast";
import { fetchSalesProfile, saveSalesProfile, uploadSalesLogo } from "@/lib/api/sales";

const BANK_FIELDS = ["bank_card", "bank_mfo", "bank_inn", "bank_transit"] as const;

export default function SalesProfilePage() {
  const t = useTranslations("sales");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["sales-profile"], queryFn: fetchSalesProfile });
  const [form, setForm] = useState<Record<string, string> | null>(null);

  const save = useMutation({
    mutationFn: (body: Record<string, string>) =>
      saveSalesProfile(body as unknown as Parameters<typeof saveSalesProfile>[0]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-profile"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
  });
  const logoUpload = useMutation({
    mutationFn: (file: File) => uploadSalesLogo(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-profile"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });
  const acceptOffer = useMutation({
    mutationFn: () => saveSalesProfile({ accept_offer: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-profile"] });
      useToastStore.getState().push({ kind: "success", text: t("offerAccepted") });
    },
  });

  if (!data) return <div className="h-64 animate-pulse rounded-lg bg-surface-2" />;
  const val = (k: string) => form?.[k] ?? (data as unknown as Record<string, string>)[k] ?? "";
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...(f ?? {}), [k]: e.target.value }));

  return (
    <div className="max-w-2xl" data-testid="sales-profile">
      <h1 className="mb-4 text-xl font-semibold">{t("profile")}</h1>

      {/* Identity + logo */}
      <section className="mb-4 rounded-2xl border border-border bg-surface p-5">
        <div className="flex items-center gap-4">
          <label className="group relative grid size-16 shrink-0 cursor-pointer place-items-center overflow-hidden rounded-xl border border-border bg-surface-2" title={t("uploadLogo")}>
            {data.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={data.logo_url} alt="" className="size-full object-contain" />
            ) : (
              <ImageIcon className="size-6 text-fg-faint" />
            )}
            <input
              type="file"
              accept="image/png,image/jpeg,image/svg+xml,image/webp"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) logoUpload.mutate(file);
                e.target.value = "";
              }}
            />
          </label>
          <div>
            <h2 className="text-lg font-semibold">{data.name}</h2>
            <p className="text-sm text-fg-muted">{data.email}</p>
            <p className="tnum mt-1 text-xs text-fg-muted">{t("commissionPct", { p: data.commission_percent })}</p>
          </div>
        </div>
        <label className="mt-4 block text-sm">
          <span className="mb-1 flex items-center gap-1 text-xs font-medium text-fg-muted">
            <Building2 className="size-3" /> {t("companyName")}
          </span>
          <input value={val("company_name")} onChange={set("company_name")} className="w-full rounded-lg border border-border bg-surface px-3 py-2" />
        </label>
        <label className="mt-3 block text-sm">
          <span className="mb-1 block text-xs font-medium text-fg-muted">{t("phone")}</span>
          <input value={val("phone")} onChange={set("phone")} className="tnum w-full rounded-lg border border-border bg-surface px-3 py-2" />
        </label>
      </section>

      {/* Bank requisites */}
      <section className="mb-4 rounded-2xl border border-border bg-surface p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
          <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">
            <CreditCard className="size-4" />
          </span>
          {t("bankDetails")}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {BANK_FIELDS.map((k) => (
            <label key={k} className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-fg-muted">{t(k)}</span>
              <input value={val(k)} onChange={set(k)} className="tnum w-full rounded-lg border border-border bg-surface px-3 py-2" />
            </label>
          ))}
        </div>
      </section>

      <button
        type="button"
        disabled={!form || save.isPending}
        onClick={() => form && save.mutate(form)}
        className="mb-6 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg disabled:opacity-40"
      >
        {t("save")}
      </button>

      {/* Public offer */}
      <section className="rounded-2xl border border-border bg-surface p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">
            <FileText className="size-4" />
          </span>
          {t("offerTitle")}
        </h2>
        {data.offer.content ? (
          /<[a-z][\s\S]*>/i.test(data.offer.content) ? (
            <div
              className="max-h-64 overflow-y-auto rounded-lg border border-border bg-surface-2 p-4 text-sm text-fg-muted [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:font-semibold [&_p]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_a]:text-accent [&_a]:underline"
              // Sanitised server-side (allow-list) before storage.
              dangerouslySetInnerHTML={{ __html: data.offer.content }}
            />
          ) : (
            <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-2 p-4 text-sm text-fg-muted">
              {data.offer.content}
            </div>
          )
        ) : (
          <p className="text-sm text-fg-faint">{t("offerEmpty")}</p>
        )}
        {data.offer.accepted ? (
          <p className="mt-3 text-sm font-medium text-accent">
            ✓ {t("offerAcceptedOn", { date: (data.offer.accepted_at ?? "").slice(0, 10) })}
          </p>
        ) : (
          data.offer.content && (
            <button
              type="button"
              onClick={() => acceptOffer.mutate()}
              className="mt-3 rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg"
            >
              {t("acceptOffer")}
            </button>
          )
        )}
      </section>
    </div>
  );
}
