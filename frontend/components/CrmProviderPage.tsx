"use client";

/** Shared shell for the dedicated CRM connector pages
 * (Settings → Integration → amoCRM / Bitrix24 / Odoo), moizvonki-style:
 * back link, guide note, info box, region radios, config form, connect/test. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, Unplug } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DirectionIcon } from "@/components/calls-shared";
import { confirmDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import {
  disconnectIntegration,
  fetchIntegrationDeliveries,
  fetchIntegrations,
  retryIntegrationDelivery,
  saveIntegration,
  testIntegration,
} from "@/lib/api/endpoints";
import { formatPhone } from "@/lib/format";

/** Per-call delivery log for one CRM: filter (all / errors), paging, retry. */
function DeliveryLog({ provider, canRetry }: { provider: string; canRetry: boolean }) {
  const t = useTranslations("crm.log");
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<"" | "error">("");
  const [page, setPage] = useState(1);
  const { data, isPending } = useQuery({
    queryKey: ["s-crm-deliveries", provider, status, page],
    queryFn: () => fetchIntegrationDeliveries(provider, { status, page }),
  });

  const retry = useMutation({
    mutationFn: (callId: number) => retryIntegrationDelivery(provider, callId),
    onSuccess: (body) => {
      queryClient.invalidateQueries({ queryKey: ["s-crm-deliveries", provider] });
      queryClient.invalidateQueries({ queryKey: ["s-integrations"] });
      queryClient.invalidateQueries({ queryKey: ["calls"] });
      useToastStore.getState().push({
        kind: body.success ? "success" : "error",
        text: body.success ? t("retryOk") : `${t("retryFail")}: ${body.error}`,
      });
    },
    onError: (error: Error) =>
      useToastStore.getState().push({ kind: "error", text: error.message }),
  });

  const rows = data?.deliveries ?? [];
  return (
    <section className="mt-8" data-testid="crm-delivery-log">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold">{t("title")}</h2>
        {data && (
          <span className="tnum text-xs text-fg-muted">
            {t("summary", { ok: data.summary.ok_30d, error: data.summary.error_30d })}
          </span>
        )}
        <div className="ml-auto flex gap-1 rounded-md border border-border p-0.5 text-xs">
          {(["", "error"] as const).map((value) => (
            <button
              key={value || "all"}
              type="button"
              onClick={() => {
                setStatus(value);
                setPage(1);
              }}
              className={
                status === value
                  ? "rounded bg-accent px-2.5 py-1 font-semibold text-accent-fg"
                  : "rounded px-2.5 py-1 text-fg-muted hover:bg-surface-2"
              }
            >
              {value ? t("onlyErrors") : t("all")}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-xs uppercase text-fg-muted">
            <tr>
              <th className="px-3 py-2 text-left">{t("sentAt")}</th>
              <th className="px-3 py-2 text-left">{t("call")}</th>
              <th className="px-3 py-2 text-left">{t("result")}</th>
              <th className="px-3 py-2 text-right" />
            </tr>
          </thead>
          <tbody>
            {isPending &&
              Array.from({ length: 4 }).map((_, index) => (
                <tr key={index}>
                  <td colSpan={4} className="px-3 py-2.5">
                    <div className="h-3.5 animate-pulse rounded bg-surface-3" />
                  </td>
                </tr>
              ))}
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-border">
                <td className="tnum whitespace-nowrap px-3 py-2 text-xs text-fg-muted">
                  {row.created_at.slice(0, 16).replace("T", " ")}
                  {row.is_retry && (
                    <span className="ml-1 rounded bg-surface-3 px-1 text-[10px] uppercase">
                      {t("retryTag")}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <DirectionIcon direction={row.direction} />
                    <span className="min-w-0">
                      <span className="tnum block">{formatPhone(row.counterparty_number)}</span>
                      <span className="block truncate text-xs text-fg-faint">
                        {row.counterparty_name ?? ""}{" "}
                        {row.start_time.slice(0, 16).replace("T", " ")}
                      </span>
                    </span>
                  </span>
                </td>
                <td className="max-w-xs px-3 py-2">
                  {row.status === "ok" ? (
                    <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">
                      {t("ok")}
                    </span>
                  ) : (
                    <span
                      className="block truncate rounded-full bg-danger/10 px-2 py-0.5 text-xs font-semibold text-danger"
                      title={row.error}
                    >
                      {t("error")}: {row.error}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  {canRetry && (
                    <button
                      type="button"
                      data-testid={`crm-retry-${row.call_id}`}
                      disabled={retry.isPending}
                      onClick={() => retry.mutate(row.call_id)}
                      title={t("retry")}
                      className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-surface-2 disabled:opacity-50"
                    >
                      <RefreshCw className="size-3.5" /> {t("retry")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!isPending && rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-xs text-fg-faint">
                  {t("empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {data && data.pages > 1 && (
        <div className="mt-2 flex items-center justify-end gap-2 text-xs">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-md border border-border px-2 py-1 disabled:opacity-40"
          >
            ‹
          </button>
          <span className="tnum">
            {page} / {data.pages}
          </span>
          <button
            type="button"
            disabled={page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-md border border-border px-2 py-1 disabled:opacity-40"
          >
            ›
          </button>
        </div>
      )}
    </section>
  );
}

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

  const disconnect = useMutation({
    mutationFn: () => disconnectIntegration(provider),
    onSuccess: () => {
      setForm({});
      setEnabled(false);
      queryClient.invalidateQueries({ queryKey: ["s-integrations"] });
      useToastStore.getState().push({ kind: "success", text: t("disconnected") });
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
        {(row?.configured || row?.is_enabled) && (
          <button
            type="button"
            data-testid="crm-disconnect"
            disabled={disconnect.isPending}
            onClick={async () =>
              (await confirmDialog(t("disconnectConfirm", { title }), {
                danger: true,
                confirmLabel: t("disconnect"),
              })) && disconnect.mutate()
            }
            className="inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-4 py-2 text-sm font-medium text-danger hover:bg-danger/5 disabled:opacity-50"
          >
            <Unplug className="size-4" /> {t("disconnect")}
          </button>
        )}
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

      {(row?.configured || row?.last_delivery_at) && (
        <DeliveryLog provider={provider} canRetry={Boolean(row?.is_enabled && row?.configured)} />
      )}
    </div>
  );
}
