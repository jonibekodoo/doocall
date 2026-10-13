"use client";

import { useTranslations } from "next-intl";

import { CrmProviderPage } from "@/components/CrmProviderPage";

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
          </div>
        );
      }}
    />
  );
}
