"use client";

/** A.4 Profile — hero card + contacts, payout details, password reset. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgePercent,
  Building2,
  Check,
  Copy,
  CreditCard,
  FileText,
  Globe,
  ImageIcon,
  KeyRound,
  Mail,
  Phone,
  UserRound,
  Wallet,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useToastStore } from "@/components/ui/Toast";
import { post } from "@/lib/api/client";
import {
  fetchPartnerDashboard,
  fetchPartnerProfile,
  savePartnerProfile,
  uploadPartnerLogo,
} from "@/lib/api/partner";
import { formatUzs } from "@/lib/format";

export default function PartnerProfilePage() {
  const t = useTranslations("partner");
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["p-profile"],
    queryFn: fetchPartnerProfile,
  });
  const { data: dash } = useQuery({
    queryKey: ["p-dashboard"],
    queryFn: fetchPartnerDashboard,
  });
  const [name, setName] = useState<string | null>(null);
  const [companyName, setCompanyName] = useState<string | null>(null);
  const [phone, setPhone] = useState<string | null>(null);
  const [card, setCard] = useState<string | null>(null);
  const [bank, setBank] = useState<Record<string, string> | null>(null);
  const [copied, setCopied] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      savePartnerProfile({
        ...(name !== null ? { name } : {}),
        ...(companyName !== null ? { company_name: companyName } : {}),
        ...(phone !== null ? { phone } : {}),
        ...(card !== null ? { payout_details: { card } } : {}),
        ...(bank?.bank_card !== undefined ? { bank_card: bank.bank_card } : {}),
        ...(bank?.bank_mfo !== undefined ? { bank_mfo: bank.bank_mfo } : {}),
        ...(bank?.bank_inn !== undefined ? { bank_inn: bank.bank_inn } : {}),
        ...(bank?.bank_transit !== undefined ? { bank_transit: bank.bank_transit } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["p-profile"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
  });

  const acceptOffer = useMutation({
    mutationFn: () => savePartnerProfile({ accept_offer: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["p-profile"] });
      useToastStore.getState().push({ kind: "success", text: t("offerAccepted") });
    },
  });

  const changePassword = useMutation({
    mutationFn: () =>
      post("/auth/password-reset", { email: data?.email ?? "" }),
    onSuccess: () =>
      useToastStore.getState().push({ kind: "info", text: t("resetSent") }),
  });

  const togglePublic = useMutation({
    mutationFn: (is_public: boolean) => savePartnerProfile({ is_public }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["p-profile"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
  });

  const logoUpload = useMutation({
    mutationFn: (file: File) => uploadPartnerLogo(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["p-profile"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
    onError: (e: Error) =>
      useToastStore.getState().push({ kind: "error", text: e.message }),
  });

  const copyCode = async () => {
    await navigator.clipboard.writeText(data?.referral_code ?? "");
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (!data)
    return <div className="h-64 animate-pulse rounded-lg bg-surface-2" />;

  const initial = (data.name || data.email).slice(0, 1).toUpperCase();

  return (
    <div data-testid="partner-profile" className="max-w-2xl">
      {/* Hero */}
      <div className="relative mb-5 overflow-hidden rounded-2xl border border-border bg-surface">
        <div className="h-20 bg-gradient-to-r from-accent via-accent/70 to-accent/40" />
        <div className="px-5 pb-5">
          <div className="-mt-9 mb-3 flex items-end gap-4">
            <span className="grid size-18 shrink-0 place-items-center rounded-2xl border-4 border-surface bg-accent text-2xl font-bold text-accent-fg shadow-md">
              {initial}
            </span>
            <div className="min-w-0 pb-0.5">
              <h1 className="truncate text-xl font-semibold">{data.name}</h1>
              <p className="truncate text-sm text-fg-muted">{data.email}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={copyCode}
              className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-3 py-1 text-xs font-semibold text-accent hover:opacity-80"
              title={t("copy")}
            >
              {copied ? (
                <Check className="size-3.5" />
              ) : (
                <Copy className="size-3.5" />
              )}
              {data.referral_code}
            </button>
            <span className="tnum inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1 text-xs font-semibold">
              <BadgePercent className="size-3.5 text-accent" />
              {t("yourPercent")}: {dash?.effective_percent ?? "…"}%
            </span>
            <span className="tnum inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1 text-xs font-semibold">
              <Wallet className="size-3.5 text-accent" />
              {t("balance")}: {formatUzs(dash?.balance_uzs ?? 0)} UZS
            </span>
          </div>
        </div>
      </div>

      {/* Publish on site */}
      <div className="mb-4 flex items-center justify-between gap-3 rounded-2xl border border-border bg-surface p-5">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
            <Globe className="size-4" />
          </span>
          <div>
            <p className="text-sm font-semibold">{t("publishTitle")}</p>
            <p className="text-xs text-fg-muted">{t("publishHint")}</p>
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={data.is_public}
          data-testid="partner-publish-toggle"
          onClick={() => togglePublic.mutate(!data.is_public)}
          className={
            data.is_public
              ? "relative h-6 w-11 shrink-0 rounded-full bg-accent transition-colors"
              : "relative h-6 w-11 shrink-0 rounded-full bg-surface-3 transition-colors"
          }
        >
          <span
            className={
              data.is_public
                ? "absolute top-0.5 left-0.5 size-5 translate-x-5 rounded-full bg-white transition-transform"
                : "absolute top-0.5 left-0.5 size-5 rounded-full bg-white transition-transform"
            }
          />
        </button>
      </div>

      {/* Company brand (shown in the public 'our integrators' section) */}
      <section className="mb-4 rounded-2xl border border-border bg-surface p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
          <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">
            <Building2 className="size-4" />
          </span>
          {t("companyBrand")}
        </h2>
        <div className="flex items-center gap-4">
          <label
            className="group relative grid size-16 shrink-0 cursor-pointer place-items-center overflow-hidden rounded-xl border border-border bg-surface-2"
            title={t("uploadLogo")}
          >
            {data.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={data.logo_url}
                alt=""
                className="size-full object-contain"
              />
            ) : (
              <ImageIcon className="size-6 text-fg-faint" />
            )}
            <input
              type="file"
              accept="image/png,image/jpeg,image/svg+xml,image/webp"
              className="hidden"
              data-testid="partner-logo-input"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) logoUpload.mutate(file);
                e.target.value = "";
              }}
            />
            <span className="absolute inset-x-0 bottom-0 hidden bg-black/50 py-0.5 text-center text-[9px] font-medium text-white group-hover:block">
              {logoUpload.isPending ? "…" : t("uploadLogo")}
            </span>
          </label>
          <label className="block flex-1 text-sm">
            <span className="mb-1 block text-xs font-medium text-fg-muted">
              {t("companyName")}
            </span>
            <input
              value={companyName ?? data.company_name}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder={t("companyNamePlaceholder")}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          </label>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Contacts */}
        <section className="rounded-2xl border border-border bg-surface p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
            <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">
              <UserRound className="size-4" />
            </span>
            {t("contacts")}
          </h2>
          <label className="mb-3 block text-sm">
            <span className="mb-1 block text-xs font-medium text-fg-muted">
              {t("nameLabel")}
            </span>
            <input
              value={name ?? data.name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          </label>
          <label className="mb-3 block text-sm">
            <span className="mb-1 flex items-center gap-1 text-xs font-medium text-fg-muted">
              <Phone className="size-3" /> {t("phoneLabel")}
            </span>
            <input
              value={phone ?? data.phone}
              onChange={(e) => setPhone(e.target.value)}
              className="tnum w-full rounded-lg border border-border bg-surface px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          </label>
        </section>

        {/* Payout details */}
        <section className="rounded-2xl border border-border bg-surface p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
            <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">
              <CreditCard className="size-4" />
            </span>
            {t("payoutDetails")}
          </h2>
          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-fg-muted">
              {t("cardNumber")}
            </span>
            <input
              value={card ?? data.payout_details.card ?? ""}
              onChange={(e) => setCard(e.target.value)}
              placeholder="8600 •••• •••• ••••"
              className="tnum w-full rounded-lg border border-border bg-surface px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          </label>
        </section>
      </div>

      {/* Bank requisites */}
      <section className="mt-4 rounded-2xl border border-border bg-surface p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
          <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">
            <CreditCard className="size-4" />
          </span>
          {t("bankDetails")}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {(["bank_card", "bank_mfo", "bank_inn", "bank_transit"] as const).map((k) => (
            <label key={k} className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-fg-muted">{t(k)}</span>
              <input
                value={bank?.[k] ?? (data as unknown as Record<string, string>)[k] ?? ""}
                onChange={(e) => setBank((b) => ({ ...(b ?? {}), [k]: e.target.value }))}
                className="tnum w-full rounded-lg border border-border bg-surface px-3 py-2"
              />
            </label>
          ))}
        </div>
        <button
          type="button"
          onClick={() => save.mutate()}
          className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg"
        >
          {t("save")}
        </button>
      </section>

      {/* Public offer */}
      <section className="mt-4 rounded-2xl border border-border bg-surface p-5">
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

      <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border border-border bg-surface p-4">
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          <span className="grid size-7 place-items-center rounded-lg bg-surface-2">
            <KeyRound className="size-4" />
          </span>
          {t("changePassword")}
          <button
            type="button"
            onClick={() => changePassword.mutate()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-surface-2"
          >
            <Mail className="size-3.5" /> {t("sendResetLink")}
          </button>
        </div>
        <button
          type="button"
          data-testid="profile-save"
          disabled={save.isPending}
          onClick={() => save.mutate()}
          className="rounded-lg bg-accent px-5 py-2 text-sm font-semibold text-accent-fg shadow-sm hover:opacity-90 disabled:opacity-40"
        >
          {t("save")}
        </button>
      </div>
    </div>
  );
}
