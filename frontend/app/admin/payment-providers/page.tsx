"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, ImagePlus, Loader2 } from "lucide-react";
import { useRef } from "react";
import { useTranslations } from "next-intl";

import { useToastStore } from "@/components/ui/Toast";
import {
  fetchPaymentProviders,
  updatePaymentProvider,
  uploadProviderLogo,
  type PaymentProviderRow,
} from "@/lib/api/admin";
import { cn } from "@/lib/utils";

function ProviderCard({
  row,
  onChanged,
}: {
  row: PaymentProviderRow;
  onChanged: () => void;
}) {
  const t = useTranslations("admin");
  const fileRef = useRef<HTMLInputElement>(null);

  const toggle = useMutation({
    mutationFn: () =>
      updatePaymentProvider({ provider: row.provider, is_enabled: !row.is_enabled }),
    onSuccess: onChanged,
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });
  const logo = useMutation({
    mutationFn: (file: File) => uploadProviderLogo(row.provider, file),
    onSuccess: () => {
      useToastStore.getState().push({ kind: "success", text: t("paymentProviders.logoSaved") });
      onChanged();
    },
    onError: (e: Error) => useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  return (
    <div
      className={cn(
        "flex flex-col gap-4 rounded-2xl border p-5 transition-colors",
        row.is_enabled
          ? "border-accent/40 bg-accent-soft/40"
          : "border-border bg-surface",
      )}
    >
      <div className="flex items-center gap-3">
        <span
          className={cn(
            "grid size-12 shrink-0 place-items-center overflow-hidden rounded-xl",
            row.is_enabled ? "bg-accent text-accent-fg" : "bg-surface-2 text-fg-muted",
          )}
        >
          {row.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={row.logo_url} alt={row.label} className="h-8 w-auto" />
          ) : (
            <CreditCard className="size-6" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-semibold">{row.label}</p>
          <p className="font-mono text-xs text-fg-faint">{row.provider}</p>
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide",
            row.is_enabled ? "bg-success/15 text-success" : "bg-surface-3 text-fg-faint",
          )}
        >
          {row.is_enabled ? t("paymentProviders.on") : t("paymentProviders.off")}
        </span>
      </div>

      <div className="mt-auto flex items-center gap-2">
        <button
          type="button"
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          className={cn(
            "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
            row.is_enabled ? "bg-accent" : "bg-surface-3",
          )}
          aria-pressed={row.is_enabled}
        >
          <span
            className={cn(
              "inline-block size-5 transform rounded-full bg-white shadow transition-transform",
              row.is_enabled ? "translate-x-5" : "translate-x-0.5",
            )}
          />
        </button>
        <span className="text-sm text-fg-muted">
          {row.is_enabled ? t("paymentProviders.enabled") : t("paymentProviders.disabled")}
        </span>

        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={logo.isPending}
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-fg-muted hover:bg-surface-2 hover:text-fg"
        >
          {logo.isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <ImagePlus className="size-3.5" />
          )}
          {t("paymentProviders.logo")}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/svg+xml,image/webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) logo.mutate(f);
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}

export default function AdminPaymentProvidersPage() {
  const t = useTranslations("admin");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["a-payment-providers"], queryFn: fetchPaymentProviders });
  const onChanged = () =>
    queryClient.invalidateQueries({ queryKey: ["a-payment-providers"] });

  return (
    <div data-testid="admin-payment-providers">
      <h1 className="text-xl font-semibold">{t("paymentProviders.title")}</h1>
      <p className="mb-5 mt-1 text-sm text-fg-muted">{t("paymentProviders.subtitle")}</p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {(data?.providers ?? []).map((row) => (
          <ProviderCard key={row.provider} row={row} onChanged={onChanged} />
        ))}
      </div>
    </div>
  );
}
