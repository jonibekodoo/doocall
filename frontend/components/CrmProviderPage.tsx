"use client";

/** Shared shell for the dedicated CRM connector pages
 * (Settings → Integration → amoCRM / Bitrix24 / Odoo), moizvonki-style:
 * back link, guide note, info box, region radios, config form, connect/test. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useToastStore } from "@/components/ui/Toast";
import {
  fetchIntegrations,
  saveIntegration,
  testIntegration,
} from "@/lib/api/endpoints";

export interface CrmField {
  key: string;
  label: string;
  placeholder?: string;
  secret?: boolean;
}

export interface CrmRegion {
  value: string;
  label: string;
}

export function CrmProviderPage({
  provider,
  title,
  info,
  regions,
  fields,
  guideHref,
  downloadHref,
}: {
  provider: "amocrm" | "bitrix24" | "odoo";
  title: string;
  info: string;
  regions?: { label: string; options: CrmRegion[] };
  fields: CrmField[];
  guideHref?: string;
  downloadHref?: string;
}) {
  const t = useTranslations("crm");
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["s-integrations"],
    queryFn: fetchIntegrations,
  });
  const row = data?.integrations.find(
    (integration) => integration.provider === provider,
  );

  const [form, setForm] = useState<Record<string, string>>({});
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    if (row) {
      setForm({ ...row.config });
      setEnabled(row.is_enabled);
    }
  }, [row]);

  const save = useMutation({
    mutationFn: () =>
      saveIntegration(provider, { is_enabled: enabled, config: form }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["s-integrations"] });
      useToastStore.getState().push({ kind: "success", text: t("saved") });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });

  const test = useMutation({
    mutationFn: () => testIntegration(provider),
    onSuccess: (body) => {
      queryClient.invalidateQueries({ queryKey: ["s-integrations"] });
      useToastStore.getState().push({
        kind: body.success ? "success" : "error",
        text: body.success
          ? `${t("testOk")}: ${body.detail ?? ""}`
          : `${t("testFail")}: ${body.error ?? ""}`,
      });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });

  const set = (key: string, value: string) =>
    setForm((previous) => ({ ...previous, [key]: value }));

  return (
    <div className="max-w-3xl" data-testid={`crm-page-${provider}`}>
      <h1 className="text-xl font-semibold">
        {t("pageTitle")} — {title}
      </h1>
      <Link
        href="/cabinet/settings"
        className="mt-1 inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
      >
        <ArrowLeft className="size-4" /> {t("back")}
      </Link>

      {guideHref && (
        <p className="mt-3 text-sm">
          {t("guideNote")}{" "}
          <a
            href={guideHref}
            target="_blank"
            rel="noreferrer noopener"
            className="font-semibold text-accent hover:underline"
          >
            {t("guideLink")}
          </a>
          .
        </p>
      )}

      <div className="mt-4 rounded-md border-l-4 border-accent bg-accent-soft/40 p-4 text-sm leading-relaxed text-fg">
        {info}
      </div>

      {downloadHref && (
        <a
          href={downloadHref}
          data-testid="crm-app-download"
          className="mt-4 inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg hover:opacity-90"
        >
          ⬇ {t("downloadApp")}
        </a>
      )}

      {regions && (
        <div className="mt-5 space-y-2">
          <p className="text-sm font-medium">{regions.label}</p>
          {regions.options.map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-2 text-sm"
            >
              <input
                type="radio"
                name={`${provider}-region`}
                checked={(form.region ?? regions.options[0].value) === option.value}
                onChange={() => set("region", option.value)}
                className="accent-[var(--accent)]"
              />
              {option.label}
            </label>
          ))}
        </div>
      )}

      <div className="mt-5 space-y-3">
        {fields.map((field) => (
          <label key={field.key} className="block max-w-md text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {field.label}
            </span>
            <input
              value={form[field.key] ?? ""}
              onChange={(event) => set(field.key, event.target.value)}
              placeholder={field.placeholder}
              autoComplete="off"
              data-testid={`crm-field-${field.key}`}
              className={
                "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" +
                (field.secret ? " font-mono" : "")
              }
            />
          </label>
        ))}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            data-testid="crm-enabled"
            className="size-4 accent-[var(--accent)]"
          />
          {t("enabled")}
        </label>
      </div>

      <div className="mt-5 flex items-center gap-2">
        <button
          type="button"
          data-testid="crm-connect"
          disabled={save.isPending}
          onClick={() => save.mutate()}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-50"
        >
          {t("connect")}
        </button>
        <button
          type="button"
          data-testid="crm-test"
          disabled={!row?.configured || test.isPending}
          onClick={() => test.mutate()}
          className="rounded-md border border-border px-4 py-2 text-sm disabled:opacity-50"
        >
          {t("test")}
        </button>
        {row?.last_status === "ok" && (
          <span className="rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent">
            {t("statusOk")}
          </span>
        )}
        {row?.last_status === "error" && (
          <span
            title={row.last_error}
            className="max-w-xs truncate rounded-full bg-danger/10 px-2.5 py-1 text-xs font-semibold text-danger"
          >
            {t("statusError")}: {row.last_error}
          </span>
        )}
      </div>
      {row?.last_delivery_at && (
        <p className="mt-2 text-xs text-fg-faint">
          {t("lastDelivery")}: {row.last_delivery_at.slice(0, 16).replace("T", " ")}
        </p>
      )}
    </div>
  );
}
