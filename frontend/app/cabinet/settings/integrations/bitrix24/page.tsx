"use client";

import { useTranslations } from "next-intl";

import { CrmProviderPage } from "@/components/CrmProviderPage";

export default function Bitrix24IntegrationPage() {
  const t = useTranslations("crm.bitrix24");
  return (
    <CrmProviderPage
      provider="bitrix24"
      title="Bitrix24"
      info={t("info")}
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
    />
  );
}
