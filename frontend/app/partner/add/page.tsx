"use client";

/** A.4 Add client — referral tab (link+QR+promo) / manual tab. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  TempPasswordReveal,
  generateTempPassword,
} from "@/components/TempPasswordReveal";
import {
  fetchPartnerDashboard,
  referralLink,
  registerClientCompany,
} from "@/lib/api/partner";
import { cn } from "@/lib/utils";

function ReferralTab({ code }: { code: string }) {
  const t = useTranslations("partner");
  const link = referralLink(code, window.location.origin);
  const [copied, setCopied] = useState(false);
  // QR is generated locally (the external qrserver image was unreliable).
  const [qr, setQr] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    import("qrcode")
      .then((qrcode) =>
        qrcode.toDataURL(link, { width: 360, margin: 1, errorCorrectionLevel: "M" }),
      )
      .then((dataUrl) => !cancelled && setQr(dataUrl))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [link]);

  return (
    <div className="grid gap-4 md:grid-cols-2" data-testid="referral-tab">
      <div className="rounded-lg border border-border bg-surface p-4">
        <p className="text-xs font-semibold uppercase text-fg-faint">
          {t("yourLink")}
        </p>
        <div className="mt-2 flex items-center gap-2">
          <code
            data-testid="ref-link"
            className="tnum min-w-0 flex-1 truncate rounded bg-surface-2 px-3 py-2 text-xs"
          >
            {link}
          </code>
          <button
            type="button"
            data-testid="ref-copy"
            aria-label={t("copy")}
            onClick={() => {
              navigator.clipboard?.writeText(link);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
            className="grid size-9 shrink-0 place-items-center rounded-md border border-border hover:bg-surface-2"
          >
            {copied ? (
              <Check className="size-4 text-accent" />
            ) : (
              <Copy className="size-4" />
            )}
          </button>
        </div>
        <p className="mt-4 text-xs font-semibold uppercase text-fg-faint">
          {t("promoCode")}
        </p>
        <p
          className="tnum mt-1 font-mono text-2xl font-bold text-accent"
          data-testid="promo-code"
        >
          {code}
        </p>
        <p className="mt-4 text-xs font-semibold uppercase text-fg-faint">
          {t("howTitle")}
        </p>
        <p className="mt-1 text-sm text-fg-muted">{t("howText")}</p>
      </div>
      <div className="grid place-items-center rounded-lg border border-border bg-surface p-4">
        {qr ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={qr}
            alt="QR"
            width={180}
            height={180}
            data-testid="ref-qr"
            className="rounded-md"
          />
        ) : (
          <div className="size-[180px] animate-pulse rounded-md bg-surface-2" />
        )}
      </div>
    </div>
  );
}

function ManualTab() {
  const t = useTranslations("partner");
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    company_name: "",
    admin_email: "",
    phone: "",
  });
  const [issued, setIssued] = useState<{
    password: string;
    email: string;
  } | null>(null);
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const register = useMutation({
    mutationFn: async () => {
      const password = generateTempPassword();
      await registerClientCompany({ ...form, password });
      return { password, email: form.admin_email };
    },
    onSuccess: (result) => {
      setIssued(result);
      setForm({ company_name: "", admin_email: "", phone: "" });
      queryClient.invalidateQueries({ queryKey: ["p-companies"] });
    },
  });

  const valid = form.company_name.trim() && form.admin_email.includes("@");

  return (
    <div className="max-w-md" data-testid="manual-tab">
      <h2 className="mb-3 text-sm font-semibold">{t("regTitle")}</h2>
      {issued ? (
        <TempPasswordReveal
          password={issued.password}
          email={issued.email}
          note={t("tempPassword")}
          onDone={() => setIssued(null)}
        />
      ) : (
        <div className="rounded-lg border border-border bg-surface p-4">
          {(["company_name", "admin_email", "phone"] as const).map((key) => (
            <label key={key} className="mb-2 block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {
                  {
                    company_name: t("companyLabel"),
                    admin_email: "Email",
                    phone: t("phoneLabel"),
                  }[key]
                }
              </span>
              <input
                value={form[key]}
                onChange={set(key)}
                data-testid={`client-${key}`}
                className="w-full rounded-md border border-border bg-surface px-3 py-2"
              />
            </label>
          ))}
          <button
            type="button"
            data-testid="client-register"
            disabled={!valid || register.isPending}
            onClick={() => register.mutate()}
            className="mt-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
          >
            {t("regTitle")}
          </button>
        </div>
      )}
    </div>
  );
}

export default function PartnerAddPage() {
  const t = useTranslations("partner");
  const [tab, setTab] = useState<"ref" | "manual">("ref");
  const { data } = useQuery({
    queryKey: ["p-dashboard"],
    queryFn: fetchPartnerDashboard,
  });

  return (
    <div data-testid="partner-add">
      <h1 className="mb-4 text-xl font-semibold">{t("add")}</h1>
      <div className="mb-4 flex gap-1.5">
        {(
          [
            ["ref", t("refTab")],
            ["manual", t("manualTab")],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            data-testid={`tab-${key}`}
            onClick={() => setTab(key)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium",
              tab === key
                ? "bg-accent text-accent-fg"
                : "border border-border text-fg-muted hover:bg-surface-2",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "ref" && data && <ReferralTab code={data.referral_code} />}
      {tab === "manual" && <ManualTab />}
    </div>
  );
}
