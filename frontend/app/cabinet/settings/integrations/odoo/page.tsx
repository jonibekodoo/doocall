"use client";

import { useTranslations } from "next-intl";

import { CrmProviderPage } from "@/components/CrmProviderPage";

export default function OdooIntegrationPage() {
  const t = useTranslations("crm.odoo");
  return (
    <CrmProviderPage
      provider="odoo"
      title="Odoo"
      info={t("info")}
      downloadHref="/api/public/odoo-app"
      fields={[
        { key: "url", label: t("url"), placeholder: "https://erp.mycompany.uz" },
        { key: "db", label: t("db"), placeholder: "mycompany" },
        { key: "login", label: t("login"), placeholder: "bot@mycompany.uz" },
        {
          key: "api_key",
          label: t("apiKey"),
          placeholder: "a1b2c3…",
          secret: true,
        },
      ]}
    />
  );
}
