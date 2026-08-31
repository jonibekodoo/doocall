"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthCard, Field, SubmitButton } from "@/components/AuthCard";
import { useAuth } from "@/lib/auth";
import { readRefCookie } from "@/components/landing/RefCapture";

export default function RegisterPage() {
  const t = useTranslations("auth");
  const router = useRouter();
  const { register } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError(null);
    try {
      await register({
        company_name: String(form.get("company_name")),
        admin_email: String(form.get("admin_email")),
        phone: String(form.get("phone")),
        password: String(form.get("password")),
        ...(readRefCookie() ? { ref: readRefCookie() } : {}),
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
