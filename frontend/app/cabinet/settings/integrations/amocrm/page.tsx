"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { CrmProviderPage } from "@/components/CrmProviderPage";
import {
  cleanUserMap,
  CrmUserMapEditor,
  useUserMapState,
} from "@/components/CrmUserMapEditor";
import { fetchIntegrations } from "@/lib/api/endpoints";

export default function AmoCrmIntegrationPage() {
  const t = useTranslations("crm.amocrm");
  const { data } = useQuery({
    queryKey: ["s-integrations"],
    queryFn: fetchIntegrations,
  });
  const row = data?.integrations.find(
    (integration) => integration.provider === "amocrm",
  );
  // user_map is a non-string config value (the row type is string-only).
  const config = (row?.config ?? {}) as Record<string, unknown>;
  const [userMap, setUserMap] = useUserMapState(config.user_map);
  const configured = Boolean(row?.configured);

  return (
    <CrmProviderPage
      provider="amocrm"
      title="amoCRM / kommoCRM"
      info={t("info")}
      guideHref="/docs/amocrm"
      showSaveError
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
      formExtra={
        configured ? (
          <CrmUserMapEditor
            provider="amocrm"
            map={userMap}
            onChange={setUserMap}
            defaultUserId={String(config.responsible_user_id || "—")}
          />
        ) : undefined
      }
      extraConfig={configured ? { user_map: cleanUserMap(userMap) } : undefined}
    />
  );
}
