"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { CrmProviderPage } from "@/components/CrmProviderPage";
import { confirmDialog } from "@/components/ui/Confirm";
import { useToastStore } from "@/components/ui/Toast";
import {
  rotateKotibAnalysisUrl,
  saveKotibAnalysisSecret,
} from "@/lib/api/endpoints";

/** Where Kotib posts finished analyses back to us (connected state only):
 * webhook URL to hand to the Kotib manager, signing secret, rotate, stats. */
function KotibAnalysisSection({ config }: { config: Record<string, string> }) {
  const t = useTranslations("crm.kotib");
  const queryClient = useQueryClient();
  const [secret, setSecret] = useState("");
  const toast = (kind: "success" | "error", text: string) =>
    useToastStore.getState().push({ kind, text });
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["s-integrations"] });

  const saveSecret = useMutation({
    mutationFn: () => saveKotibAnalysisSecret(secret.trim()),
    onSuccess: () => {
      setSecret("");
      refresh();
      toast("success", t("secretSaved"));
    },
    onError: (error: Error) => toast("error", error.message),
  });
  const rotate = useMutation({
    mutationFn: rotateKotibAnalysisUrl,
    onSuccess: () => {
      refresh();
      toast("success", t("rotated"));
    },
    onError: (error: Error) => toast("error", error.message),
  });

  const url = config.analysis_webhook_url ?? "";
  const storedSecret = config.analysis_secret ?? "";
  const lastAt = config.analysis_last_received_at;
  const count = Number(config.analysis_count ?? 0);

  return (
    <section
      data-testid="kotib-analysis"
      className="mt-6 space-y-3 rounded-lg border border-border bg-surface p-4"
    >
      <h2 className="text-base font-semibold">{t("analysisTitle")}</h2>

      <div className="text-sm">
        <span className="mb-1 block text-xs text-fg-muted">
          {t("analysisUrl")}
        </span>
        <div className="flex max-w-xl gap-2">
          <input
            readOnly
            value={url}
            data-testid="kotib-analysis-url"
            onFocus={(event) => event.currentTarget.select()}
            className="min-w-0 flex-1 rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-xs"
          />
          <button
            type="button"
            data-testid="kotib-analysis-copy"
            disabled={!url}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(url);
                toast("success", t("copied"));
              } catch {
                toast("error", t("copyFailed"));
              }
            }}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-xs hover:bg-surface-2 disabled:opacity-50"
          >
            <Copy className="size-3.5" /> {t("copy")}
          </button>
        </div>
        <p className="mt-1 text-xs text-fg-faint">{t("analysisUrlHint")}</p>
      </div>

      <label className="block max-w-xl text-sm">
        <span className="mb-1 block text-xs text-fg-muted">
          {t("secretLabel")}
        </span>
        <div className="flex gap-2">
          <input
            value={secret}
            onChange={(event) => setSecret(event.target.value)}
            placeholder={
              storedSecret ? t("secretStored", { masked: storedSecret }) : ""
            }
            autoComplete="off"
            data-testid="kotib-analysis-secret"
            className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-2 font-mono text-sm"
          />
          <button
            type="button"
            data-testid="kotib-analysis-secret-save"
            disabled={!secret.trim() || saveSecret.isPending}
            onClick={() => saveSecret.mutate()}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-50"
          >
            {t("secretSave")}
          </button>
        </div>
      </label>
      {!storedSecret && (
        <p
          data-testid="kotib-analysis-unsigned"
          className="max-w-xl rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
        >
          {t("unsignedWarning")}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 text-xs text-fg-muted">
        <span data-testid="kotib-analysis-stats">
          {lastAt
            ? t("lastReceived", {
                at: lastAt.slice(0, 16).replace("T", " "),
                count,
              })
            : t("noneReceived")}
        </span>
        <button
          type="button"
          data-testid="kotib-analysis-rotate"
          disabled={rotate.isPending}
          onClick={async () =>
            (await confirmDialog(t("rotateConfirm"), {
              danger: true,
              confirmLabel: t("rotate"),
            })) && rotate.mutate()
          }
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-surface-2 disabled:opacity-50"
        >
          <RefreshCw className="size-3.5" /> {t("rotate")}
        </button>
      </div>
    </section>
  );
}

/** Kotib Analytics (kotib.ai): AI analysis of answered calls. Saving the key
 * connects synchronously on the backend, so a failed connect keeps Kotib's
 * own message on the card. */
export default function KotibIntegrationPage() {
  const t = useTranslations("crm.kotib");
  return (
    <CrmProviderPage
      provider="kotib"
      title="Kotib Analytics"
      info={t("info")}
      alwaysEnabled
      showSaveError
      fields={[
        {
          key: "api_key",
          label: t("apiKey"),
          placeholder: "a1b2c3…",
          secret: true,
        },
      ]}
      connectedInfo={(config) => {
        const inactive = Number(config.employees_created_inactive ?? 0);
        const hasCounts = ["created", "existing", "created_inactive"].some(
          (key) => config[`employees_${key}`] !== undefined,
        );
        return (
          <div className="space-y-2 text-sm">
            {config.company_name && (
              <p className="font-semibold text-accent">
                {t("connectedTo", { company: config.company_name })}
              </p>
            )}
            {hasCounts && (
              <p className="tnum text-fg-muted" data-testid="kotib-employees">
                {t("employees", {
                  created: Number(config.employees_created ?? 0),
                  existing: Number(config.employees_existing ?? 0),
                  inactive,
                })}
              </p>
            )}
            {inactive > 0 && (
              <p
                data-testid="kotib-inactive-warning"
                className="max-w-xl rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-fg"
              >
                {t("inactiveWarning", { count: inactive })}
              </p>
            )}
            <KotibAnalysisSection config={config} />
          </div>
        );
      }}
    />
  );
}
