"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthCard, Field, SubmitButton } from "@/components/AuthCard";
import { homeFor, useAuth } from "@/lib/auth";

export default function LoginPage() {
  const t = useTranslations("auth");
  const router = useRouter();
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError(null);
    try {
      await login(String(form.get("email")), String(form.get("password")));
      const portal = document.cookie.match(/doocall_portal=(\w+)/)?.[1];
      router.replace(homeFor(portal));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthCard
      title={t("loginTitle")}
      footer={
        <>
          {t("noAccount")}{" "}
          <Link
            href="/register"
            className="font-medium text-accent hover:underline"
          >
            {t("register")}
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} data-testid="login-form">
        <Field
          label={t("email")}
          name="email"
          type="email"
          required
          autoComplete="email"
        />
        <Field
          label={t("password")}
          name="password"
          type="password"
          required
          autoComplete="current-password"
        />
        {error && (
          <p role="alert" className="mb-2 text-sm text-danger">
            {error}
          </p>
        )}
        <SubmitButton loading={loading}>{t("login")}</SubmitButton>
        <p className="mt-3 text-center">
          <Link
            href="/reset-password"
            className="text-xs text-fg-muted hover:text-accent"
          >
            {t("forgotPassword")}
          </Link>
        </p>
      </form>
    </AuthCard>
  );
}
