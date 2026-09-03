"use client";

import { useTranslations } from "next-intl";

import { CrmProviderPage } from "@/components/CrmProviderPage";

export default function AmoCrmIntegrationPage() {
  const t = useTranslations("crm.amocrm");
  return (
    <CrmProviderPage
      provider="amocrm"
      title="amoCRM / kommoCRM"
      info={t("info")}
      regions={{
        label: t("regionLabel"),
        options: [
          { value: "amocrm.ru", label: t("regionRu") },
          { value: "kommo.com", label: t("regionKommo") },
        ],
      }}
      fields={[
        {
          key: "base_url",
          label: t("baseUrl"),
          placeholder: "https://mycompany.amocrm.ru",
        },
        {
          key: "access_token",
          label: t("accessToken"),
          placeholder: "eyJ0eXAiOiJKV1Qi…",
          secret: true,
        },
        {
          key: "responsible_user_id",
          label: t("responsibleUserId"),
          placeholder: "504141",
        },
      ]}
    />
  );
}
