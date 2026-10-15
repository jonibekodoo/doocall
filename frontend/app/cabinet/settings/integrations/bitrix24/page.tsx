"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { CrmProviderPage } from "@/components/CrmProviderPage";
import {
  cleanUserMap,
  CrmUserMapEditor,
  useUserMapState,
} from "@/components/CrmUserMapEditor";
import { fetchIntegrations } from "@/lib/api/endpoints";
import type {
  Bitrix24CardOptions,
  Bitrix24CreateCard,
  Bitrix24PortalMode,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

const CARD_MODES: Bitrix24CreateCard[] = [
  "auto",
  "lead",
  "contact",
  "deal",
  "none",
];

/** Backend defaults — also used for rows saved before these options existed. */
const DEFAULT_OPTIONS: Bitrix24CardOptions = {
  save_external_calls: true,
  create_card: "auto",
  lead_source: "CALL",
  only_answered: false,
};

const LEAD_SOURCE_RE = /^[A-Z0-9_]{0,50}$/; // "" → backend default (CALL)

function optionsFrom(config: Record<string, unknown>): Bitrix24CardOptions {
  const mode = String(config.create_card ?? "");
  return {
    save_external_calls:
      typeof config.save_external_calls === "boolean"
        ? config.save_external_calls
        : DEFAULT_OPTIONS.save_external_calls,
    create_card: (CARD_MODES as string[]).includes(mode)
      ? (mode as Bitrix24CreateCard)
      : DEFAULT_OPTIONS.create_card,
    lead_source:
      typeof config.lead_source === "string"
        ? config.lead_source
        : DEFAULT_OPTIONS.lead_source,
    only_answered:
      typeof config.only_answered === "boolean"
        ? config.only_answered
        : DEFAULT_OPTIONS.only_answered,
  };
}

/** Leads are only ever created on a classic portal (explicit "lead" on a
 * simple portal falls back to a contact; an undetected mode = no leads). */
function leadSourceRelevant(
  options: Bitrix24CardOptions,
  portal: Bitrix24PortalMode,
): boolean {
  if (!options.save_external_calls) return false;
  if (options.create_card !== "lead" && options.create_card !== "auto") {
    return false;
  }
  // Simple portal, or mode detection failed (assumed simple) → never leads.
  return portal.crm_mode !== "simple" && !portal.crm_mode_assumed;
}

/** moizvonki-style "Qo'ng'iroqlarni saqlash": what to create in Bitrix24 for
 * an unknown number; saved with the page's Connect button. */
function CardOptionsEditor({
  options,
  onChange,
  portal,
  leadSourceInvalid,
}: {
  options: Bitrix24CardOptions;
  onChange: (options: Bitrix24CardOptions) => void;
  portal: Bitrix24PortalMode;
  leadSourceInvalid: boolean;
}) {
  const t = useTranslations("crm.bitrix24");
  const set = <K extends keyof Bitrix24CardOptions>(
    key: K,
    value: Bitrix24CardOptions[K],
  ) => onChange({ ...options, [key]: value });
  const simple = portal.crm_mode === "simple";
  const noLeads = simple || portal.crm_mode_assumed;

  return (
    <section
      data-testid="b24-card-options"
      className="mt-6 space-y-3 rounded-lg border border-border bg-surface p-4"
    >
      <h2 className="text-base font-semibold">{t("saveTitle")}</h2>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={options.save_external_calls}
          onChange={(event) => set("save_external_calls", event.target.checked)}
          data-testid="b24-save-external"
          className="mt-0.5 size-4 accent-[var(--accent)]"
        />
        {t("saveExternal")}
      </label>

      <fieldset
        disabled={!options.save_external_calls}
        className="space-y-2 disabled:opacity-50"
        data-testid="b24-create-card"
      >
        <legend className="mb-1 text-sm font-medium">
          {t("unknownNumber")}
        </legend>
        {(simple || portal.crm_mode_assumed) && (
          <p
            data-testid="b24-portal-mode"
            className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs"
          >
            <Info className="mt-0.5 size-3.5 shrink-0 text-warning" />
            {portal.crm_mode_assumed ? t("modeAssumed") : t("modeSimple")}
          </p>
        )}
        {portal.crm_mode === "classic" && !portal.crm_mode_assumed && (
          <p data-testid="b24-portal-mode" className="text-xs text-fg-muted">
            {t("modeClassic")}
          </p>
        )}
        {CARD_MODES.map((mode) => {
          const leadUnavailable = mode === "lead" && noLeads;
          return (
            <label
              key={mode}
              data-testid={`b24-card-${mode}`}
              className={cn(
                "flex items-start gap-2 text-sm",
                leadUnavailable && "text-fg-muted",
              )}
            >
              <input
                type="radio"
                name="b24-create-card"
                value={mode}
                checked={options.create_card === mode}
                onChange={() => set("create_card", mode)}
                className="mt-0.5 accent-[var(--accent)]"
              />
              <span>
                <span
                  className={cn("block", leadUnavailable && "line-through")}
                >
                  {t(`card_${mode}`)}
                </span>
                <span className="block text-xs text-fg-faint">
                  {leadUnavailable
                    ? t("card_leadNoLeads")
                    : t(`card_${mode}Hint`)}
                </span>
              </span>
            </label>
          );
        })}
        <p className="text-xs text-fg-faint">{t("knownNumberNote")}</p>
      </fieldset>

      {leadSourceRelevant(options, portal) && (
        <label className="block max-w-xs text-sm">
          <span className="mb-1 block text-xs text-fg-muted">
            {t("leadSource")}
          </span>
          <input
            value={options.lead_source}
            onChange={(event) =>
              set("lead_source", event.target.value.toUpperCase())
            }
            placeholder="CALL"
            maxLength={50}
            autoComplete="off"
            aria-invalid={leadSourceInvalid}
            data-testid="b24-lead-source"
            className={cn(
              "w-full rounded-md border bg-surface px-3 py-2 font-mono text-sm",
              leadSourceInvalid ? "border-danger" : "border-border",
            )}
          />
          <span
            className={cn(
              "mt-1 block text-xs",
              leadSourceInvalid ? "text-danger" : "text-fg-faint",
            )}
            data-testid={
              leadSourceInvalid ? "b24-lead-source-error" : undefined
            }
          >
            {t("leadSourceHint")}
          </span>
        </label>
      )}

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={options.only_answered}
          onChange={(event) => set("only_answered", event.target.checked)}
          data-testid="b24-only-answered"
          className="mt-0.5 size-4 accent-[var(--accent)]"
        />
        {t("onlyAnswered")}
      </label>
    </section>
  );
}

export default function Bitrix24IntegrationPage() {
  const t = useTranslations("crm.bitrix24");
  const { data } = useQuery({
    queryKey: ["s-integrations"],
    queryFn: fetchIntegrations,
  });
  const row = data?.integrations.find(
    (integration) => integration.provider === "bitrix24",
  );
  // user_map / card options are non-string config values (row type is string-only).
  const config = (row?.config ?? {}) as Record<string, unknown>;
  const [userMap, setUserMap] = useUserMapState(config.user_map);

  const [options, setOptions] = useState<Bitrix24CardOptions>(DEFAULT_OPTIONS);
  useEffect(() => {
    if (row) setOptions(optionsFrom(row.config as Record<string, unknown>));
  }, [row]);
  const portal: Bitrix24PortalMode = {
    crm_mode:
      config.crm_mode === "classic" || config.crm_mode === "simple"
        ? config.crm_mode
        : "",
    crm_mode_checked_at: (config.crm_mode_checked_at as string | null) ?? null,
    crm_mode_assumed: Boolean(config.crm_mode_assumed),
  };
  const leadSourceValid = LEAD_SOURCE_RE.test(options.lead_source.trim());
  const relevant = leadSourceRelevant(options, portal);

  const configured = Boolean(row?.configured);
  return (
    <CrmProviderPage
      provider="bitrix24"
      title="Bitrix24"
      info={t("info")}
      guideHref="/docs/bitrix24"
      showSaveError
      regions={{
        label: t("regionLabel"),
        options: [
          { value: "ru", label: t("regionRu") },
          { value: "by_kz", label: t("regionByKz") },
          { value: "other", label: t("regionOther") },
        ],
      }}
      fields={[
        {
          key: "account",
          label: t("account"),
          placeholder: "my.bitrix24.ru",
        },
        {
          key: "webhook_url",
          label: t("webhookUrl"),
          placeholder: "https://my.bitrix24.ru/rest/1/abc123xyz/",
          secret: true,
        },
        { key: "user_id", label: t("userId"), placeholder: "1" },
      ]}
      formExtra={
        <>
          <CardOptionsEditor
            options={options}
            onChange={setOptions}
            portal={portal}
            leadSourceInvalid={relevant && !leadSourceValid}
          />
          {configured && (
            <CrmUserMapEditor
              provider="bitrix24"
              map={userMap}
              onChange={setUserMap}
              defaultUserId={String(config.user_id || "1")}
            />
          )}
        </>
      }
      extraConfig={{
        save_external_calls: options.save_external_calls,
        create_card: options.create_card,
        only_answered: options.only_answered,
        // An invalid source that doesn't apply is simply not sent (the stored
        // value is kept); when it applies, saving is blocked instead.
        ...(leadSourceValid ? { lead_source: options.lead_source.trim() } : {}),
        ...(configured ? { user_map: cleanUserMap(userMap) } : {}),
      }}
      saveBlocked={relevant && !leadSourceValid}
    />
  );
}
