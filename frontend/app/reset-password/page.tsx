"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthCard, Field, SubmitButton } from "@/components/AuthCard";
import { post } from "@/lib/api/client";

function ResetInner() {
  const t = useTranslations("auth");
  const params = useSearchParams();
  const uid = params.get("uid");
  const token = params.get("token");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const request = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    try {
      await post("/auth/password-reset", { email: String(form.get("email")) });
      setDone(true);
    } finally {
      setLoading(false);
    }
  };

  const confirm = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError(null);
    try {
      await post("/auth/password-reset/confirm", {
        uid,
        token,
        new_password: String(form.get("new_password")),
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthCard
      title={t("resetTitle")}
      footer={
        <Link href="/login" className="font-medium text-accent hover:underline">
          {t("login")}
        </Link>
      }
    >
      {done ? (
        <p className="text-sm text-fg-muted">{t("resetSent")}</p>
      ) : uid && token ? (
        <form onSubmit={confirm}>
          <Field
            label={t("newPassword")}
            name="new_password"
            type="password"
            required
            minLength={8}
          />
          {error && (
            <p role="alert" className="mb-2 text-sm text-danger">
              {error}
            </p>
          )}
          <SubmitButton loading={loading}>{t("resetConfirm")}</SubmitButton>
        </form>
      ) : (
        <form onSubmit={request}>
          <Field label={t("email")} name="email" type="email" required />
          <SubmitButton loading={loading}>{t("resetSend")}</SubmitButton>
        </form>
      )}
    </AuthCard>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetInner />
    </Suspense>
  );
}
