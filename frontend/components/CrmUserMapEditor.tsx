"use client";

/** Shared "map our operators to CRM users" table (Bitrix24, amoCRM): select
 * of CRM users, manual-ID fallback when they can't be loaded, auto-match from
 * backend suggestions. Saved by CrmProviderPage via extraConfig.user_map. */

import { useQuery } from "@tanstack/react-query";
import { Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { fetchCrmUsers, type CrmOperator } from "@/lib/api/endpoints";

export type UserMapProvider = "bitrix24" | "amocrm";

const TEST_ID_PREFIX: Record<UserMapProvider, string> = {
  bitrix24: "b24",
  amocrm: "amo",
};

export type UserMap = Record<string, string>;

/** Only real choices are saved: "" (= use the default user) is dropped. */
export function cleanUserMap(map: UserMap): UserMap {
  return Object.fromEntries(
    Object.entries(map)
      .map(([operatorId, userId]) => [operatorId, userId.trim()])
      .filter(([, userId]) => userId !== ""),
  );
}

/** Fill only EMPTY rows from the backend suggestions (manual picks win). */
export function applySuggestions(
  map: UserMap,
  suggestions: UserMap,
  allowed?: Set<string>,
): { map: UserMap; matched: number } {
  const next = { ...map };
  let matched = 0;
  for (const [operatorId, userId] of Object.entries(suggestions)) {
    const value = String(userId);
    if ((next[operatorId] ?? "").trim() || !value) continue;
    if (allowed && !allowed.has(value)) continue;
    next[operatorId] = value;
    matched += 1;
  }
  return { map: next, matched };
}

function phonesText(phones: CrmOperator["phones"]): string {
  return Array.isArray(phones)
    ? phones.filter(Boolean).join(", ")
    : phones || "";
}

/** Operator → CRM user editor (Bitrix24 USER_ID / amoCRM manager); the page
 * saves the map with its Connect button. Texts come from `crm.<provider>`. */
export function CrmUserMapEditor({
  provider,
  map,
  onChange,
  defaultUserId,
}: {
  provider: UserMapProvider;
  map: UserMap;
  onChange: (map: UserMap) => void;
  defaultUserId: string;
}) {
  const t = useTranslations(`crm.${provider}`);
  const prefix = TEST_ID_PREFIX[provider];
  const [matched, setMatched] = useState<number | null>(null);
  const { data, isPending, isError, error } = useQuery({
    queryKey: [`s-${provider}-users`],
    queryFn: () => fetchCrmUsers(provider),
  });

  const users = useMemo(
    () => (data?.success ? (data.users ?? []) : null),
    [data],
  );
  const userIds = useMemo(
    () => (users ? new Set(users.map((user) => String(user.id))) : undefined),
    [users],
  );
  const operators = data?.operators ?? [];
  const loadError = isError
    ? (error as Error).message
    : data && !data.success
      ? data.error || ""
      : null;

  const set = (operatorId: number, value: string) => {
    setMatched(null);
    onChange({ ...map, [String(operatorId)]: value });
  };

  return (
    <section
      data-testid={`${prefix}-user-map`}
      className="mt-6 space-y-3 rounded-lg border border-border bg-surface p-4"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="flex-1 text-base font-semibold">{t("mapTitle")}</h2>
        <button
          type="button"
          data-testid={`${prefix}-auto-match`}
          disabled={!data?.suggestions || operators.length === 0}
          onClick={() => {
            const result = applySuggestions(
              map,
              data?.suggestions ?? {},
              userIds,
            );
            onChange(result.map);
            setMatched(result.matched);
          }}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-surface-2 disabled:opacity-50"
        >
          <Wand2 className="size-3.5" /> {t("autoMatch")}
        </button>
      </div>
      <p className="text-xs text-fg-muted">{t("mapHint")}</p>
      {matched !== null && (
        <p
          data-testid={`${prefix}-matched`}
          className="text-xs font-medium text-accent"
        >
          {matched > 0
            ? t("autoMatched", { count: matched })
            : t("autoMatchedNone")}
        </p>
      )}
      {loadError !== null && (
        <p
          data-testid={`${prefix}-users-error`}
          className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
        >
          {t("usersError", { error: loadError })}
        </p>
      )}

      {isPending ? (
        <div className="h-24 animate-pulse rounded-md bg-surface-3" />
      ) : operators.length === 0 ? (
        <p className="text-sm text-fg-faint">{t("noOperators")}</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-fg-muted">
            <tr>
              <th className="py-2 pr-3 text-left">{t("colOperator")}</th>
              <th className="py-2 text-left">{t("colUser")}</th>
            </tr>
          </thead>
          <tbody>
            {operators.map((operator) => {
              const value = map[String(operator.id)] ?? "";
              const usesDefault = value.trim() === "";
              return (
                <tr
                  key={operator.id}
                  data-testid={`${prefix}-row-${operator.id}`}
                  className="border-t border-border align-top"
                >
                  <td className="py-2 pr-3">
                    <span className="block font-medium">
                      {operator.full_name || operator.user_name}
                    </span>
                    <span className="block text-xs text-fg-faint">
                      {operator.user_name}
                      {phonesText(operator.phones) &&
                        ` · ${phonesText(operator.phones)}`}
                    </span>
                  </td>
                  <td className="py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {users ? (
                        <select
                          value={value}
                          data-testid={`${prefix}-select-${operator.id}`}
                          aria-label={operator.full_name || operator.user_name}
                          onChange={(event) =>
                            set(operator.id, event.target.value)
                          }
                          className="min-w-0 max-w-xs flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm"
                        >
                          <option value="">{t("defaultOption")}</option>
                          {value && !userIds?.has(value) && (
                            <option value={value}>
                              {t("unknownUser", { id: value })}
                            </option>
                          )}
                          {users.map((user) => (
                            <option key={user.id} value={String(user.id)}>
                              {[user.name, user.email]
                                .filter(Boolean)
                                .join(" · ") || `ID ${user.id}`}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          value={value}
                          inputMode="numeric"
                          placeholder={t("manualPlaceholder")}
                          data-testid={`${prefix}-input-${operator.id}`}
                          aria-label={operator.full_name || operator.user_name}
                          onChange={(event) =>
                            set(
                              operator.id,
                              event.target.value.replace(/\D/g, ""),
                            )
                          }
                          className="w-32 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm"
                        />
                      )}
                      {usesDefault && (
                        <span
                          data-testid={`${prefix}-default-${operator.id}`}
                          className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-fg-muted"
                        >
                          {t("usesDefault", { id: defaultUserId })}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

/** Editable copy of the saved config.user_map (values as strings), reset
 * whenever the stored map changes (load / after a save). */
export function useUserMapState(saved: unknown) {
  const savedMap = saved as Record<string, unknown> | undefined;
  const [userMap, setUserMap] = useState<UserMap>({});
  useEffect(() => {
    setUserMap(
      Object.fromEntries(
        Object.entries(savedMap ?? {}).map(([key, value]) => [
          key,
          String(value),
        ]),
      ),
    );
  }, [savedMap]);
  return [userMap, setUserMap] as const;
}
