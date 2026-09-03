"use client";

import { Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthCard, Field, SubmitButton } from "@/components/AuthCard";
import { REF_COOKIE, readRefCookie } from "@/components/landing/RefCapture";
import { useAuth } from "@/lib/auth";

const REF_RE = /^[A-Za-z0-9]{4,12}$/;

export default function RegisterPage() {
  const t = useTranslations("auth");
  const router = useRouter();
  const { register } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [promo, setPromo] = useState("");
  // Arriving via a partner link/QR (?ref=…) locks the promo field.
  const [promoLocked, setPromoLocked] = useState(false);

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("ref");
    const code =
      fromUrl && REF_RE.test(fromUrl) ? fromUrl.toUpperCase() : readRefCookie();
    if (code) {
      setPromo(code);
      setPromoLocked(true);
      document.cookie = `${REF_COOKIE}=${code};path=/;max-age=${30 * 86400};samesite=lax`;
    }
  }, []);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const ref = promo.trim().toUpperCase();
    setLoading(true);
    setError(null);
    try {
      await register({
        company_name: String(form.get("company_name")),
        admin_email: String(form.get("admin_email")),
        phone: String(form.get("phone")),
        password: String(form.get("password")),
        ...(ref ? { ref } : {}),
      });
      router.replace("/cabinet/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthCard
      title={t("registerTitle")}
      footer={
        <>
          {t("haveAccount")}{" "}
          <Link
            href="/login"
            className="font-medium text-accent hover:underline"
          >
            {t("login")}
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} data-testid="register-form">
        <Field label={t("companyName")} name="company_name" required />
        <Field label={t("email")} name="admin_email" type="email" required />
        <Field
          label={t("phone")}
          name="phone"
          type="tel"
          required
          placeholder="+998 90 …"
        />
        <Field
          label={t("password")}
          name="password"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
        />
        <label className="mb-3 block text-sm">
          <span className="mb-1 flex items-center gap-1.5 text-xs text-fg-muted">
            {t("promoCode")}
            {promoLocked && <Lock className="size-3 text-accent" />}
          </span>
          <input
            name="promo"
            value={promo}
            onChange={(event) =>
              !promoLocked && setPromo(event.target.value.toUpperCase())
            }
            readOnly={promoLocked}
            maxLength={12}
            autoComplete="off"
            data-testid="register-promo"
            className={
              "tnum w-full rounded-md border border-border px-3 py-2 font-mono uppercase " +
              (promoLocked
                ? "bg-surface-2 text-accent"
                : "bg-surface")
            }
          />
          {promoLocked && (
            <span className="mt-1 block text-xs text-fg-faint">
              {t("promoLockedNote")}
            </span>
          )}
        </label>
        {error && (
          <p role="alert" className="mb-2 text-sm text-danger">
            {error}
          </p>
        )}
        <SubmitButton loading={loading}>{t("register")}</SubmitButton>
        <p className="mt-3 text-center text-xs text-fg-faint">
          {t("trialNote")}
        </p>
      </form>
    </AuthCard>
  );
}
