"use client";

/** A.4 Profile — hero card + contacts, payout details, password reset. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgePercent,
  Check,
  Copy,
  CreditCard,
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
  const [phone, setPhone] = useState<string | null>(null);
  const [card, setCard] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      savePartnerProfile({
        ...(name !== null ? { name } : {}),
        ...(phone !== null ? { phone } : {}),
        ...(card !== null ? { payout_details: { card } } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["p-profile"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
  });

  const changePassword = useMutation({
    mutationFn: () =>
      post("/auth/password-reset", { email: data?.email ?? "" }),
    onSuccess: () =>
      useToastStore.getState().push({ kind: "info", text: t("resetSent") }),
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
