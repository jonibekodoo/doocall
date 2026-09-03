"use client";

/** §6.5 Настройки — six tabs: users&groups, devices, calls&SMS,
 * integration, account, license&payment. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Power, Smartphone, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { CredentialsDialog } from "@/components/CredentialsDialog";
import { useToastStore } from "@/components/ui/Toast";
import {
  createGroup,
  createOperator,
  deleteDevice,
  deleteGroup,
  fetchAccountSettings,
  fetchApiKey,
  fetchCrmCatalog,
  fetchDevices,
  fetchGroups,
  fetchIntegrations,
  fetchLicense,
  fetchUsers,
  fetchWebhook,
  patchOperator,
  patchSim,
  rotateApiKey,
  saveAccountSettings,
  saveWebhook,
  testWebhook,
  type NewOperatorResponse,
} from "@/lib/api/endpoints";
import { formatPhone, formatUzs } from "@/lib/format";
import { cn } from "@/lib/utils";

const TABS = [
  "usersGroups",
  "devices",
  "callsSms",
  "integration",
  "account",
  "license",
] as const;
type SettingsTab = (typeof TABS)[number];

// ── Tab 1: users & groups ──────────────────────────────────────────────────
function UsersTab() {
  const t = useTranslations("settings");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["s-users"], queryFn: fetchUsers });
  const { data: groups } = useQuery({
    queryKey: ["s-groups"],
    queryFn: fetchGroups,
  });
  const [newOperator, setNewOperator] = useState("");
  const [opFullName, setOpFullName] = useState("");
  const [opPhone, setOpPhone] = useState("");
  const [opPhone2, setOpPhone2] = useState("");
  const [opGroup, setOpGroup] = useState<string>("");
  const [newGroup, setNewGroup] = useState("");
  const [credentials, setCredentials] = useState<
    NewOperatorResponse["credentials"] | null
  >(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["s-users"] });
    queryClient.invalidateQueries({ queryKey: ["s-license"] });
  };

  const add = useMutation({
    mutationFn: () =>
      createOperator({
        user_name: newOperator.trim(),
        full_name: opFullName.trim() || undefined,
        phone: opPhone.trim() || undefined,
        phone2: opPhone2.trim() || undefined,
        group_id: opGroup ? Number(opGroup) : undefined,
      }),
    onSuccess: (body) => {
      setCredentials(body.credentials);
      setNewOperator("");
      setOpFullName("");
      setOpPhone("");
      setOpPhone2("");
      setOpGroup("");
      invalidate();
    },
  });
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      patchOperator(id, { is_active: active }),
    onSuccess: invalidate,
  });
  const addGroup = useMutation({
    mutationFn: () => createGroup(newGroup.trim()),
    onSuccess: () => {
      setNewGroup("");
      queryClient.invalidateQueries({ queryKey: ["s-groups"] });
    },
  });

  return (
    <div className="space-y-6">
      <p className="text-xs text-fg-faint">{t("seatNote")}</p>

      <div className="rounded-lg border border-border bg-surface">
        <div className="border-b border-border p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
            {t("newOperatorTitle")}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("opUserName")} *
              </span>
              <input
                value={newOperator}
                onChange={(event) => setNewOperator(event.target.value)}
                placeholder="operator1"
                data-testid="new-operator-name"
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("opFullName")}
              </span>
              <input
                value={opFullName}
                onChange={(event) => setOpFullName(event.target.value)}
                data-testid="new-operator-fullname"
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("opPhone")}
              </span>
              <input
                value={opPhone}
                onChange={(event) => setOpPhone(event.target.value)}
                placeholder="+998 90 123 45 67"
                data-testid="new-operator-phone"
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("opPhone2")}
              </span>
              <input
                value={opPhone2}
                onChange={(event) => setOpPhone2(event.target.value)}
                data-testid="new-operator-phone2"
                className="tnum w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-fg-muted">
                {t("opGroup")}
              </span>
              <select
                value={opGroup}
                onChange={(event) => setOpGroup(event.target.value)}
                data-testid="new-operator-group"
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              >
                <option value="">{t("opNoGroup")}</option>
                {(groups?.groups ?? []).map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <button
                type="button"
                data-testid="add-operator"
                disabled={!newOperator.trim() || add.isPending}
                onClick={() => add.mutate()}
                className="w-full rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-fg disabled:opacity-50"
              >
                {t("addOperator")}
              </button>
            </div>
          </div>
        </div>
        <ul className="divide-y divide-border">
          {(data?.operators ?? []).map((operator) => (
            <li
              key={operator.id}
              className="flex items-center gap-3 px-4 py-2.5 text-sm"
            >
              <span
                className={cn(
                  "min-w-0 flex-1 truncate",
                  !operator.is_active && "opacity-50",
                )}
              >
                <b>{operator.user_name}</b>
                {operator.full_name && (
                  <span className="text-fg-muted"> · {operator.full_name}</span>
                )}
                {(operator.phones ?? []).length > 0 && (
                  <span className="tnum text-xs text-fg-faint">
                    {" "}
                    · {(operator.phones ?? []).map((p) => p.number).join(", ")}
                  </span>
                )}
                {!operator.is_active && (
                  <span className="ml-2 rounded-full bg-surface-3 px-2 py-0.5 text-xs">
                    {t("deactivated")}
                  </span>
                )}
              </span>
              <button
                type="button"
                aria-label={`toggle ${operator.user_name}`}
                data-testid={`toggle-${operator.user_name}`}
                onClick={() =>
                  toggle.mutate({
                    id: operator.id,
                    active: !operator.is_active,
                  })
                }
                className={cn(
                  "grid size-7 place-items-center rounded-full",
                  operator.is_active
                    ? "bg-accent-soft text-accent"
                    : "bg-surface-3 text-fg-faint",
                )}
              >
                <Power className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg border border-border bg-surface p-3">
        <div className="flex gap-2">
          <input
            value={newGroup}
            onChange={(event) => setNewGroup(event.target.value)}
            placeholder="Группа"
            className="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm"
          />
          <button
            type="button"
            disabled={!newGroup.trim()}
            onClick={() => addGroup.mutate()}
            className="rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50"
          >
            +
          </button>
        </div>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {(groups?.groups ?? []).map((group) => (
            <li
              key={group.id}
              className="flex items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1 text-xs"
            >
              {group.name}
              <button
                type="button"
                aria-label={`delete ${group.name}`}
                onClick={() =>
                  deleteGroup(group.id).then(() =>
                    queryClient.invalidateQueries({ queryKey: ["s-groups"] }),
                  )
                }
                className="text-fg-faint hover:text-danger"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      </div>

      {credentials && (
        <CredentialsDialog
          credentials={credentials}
          note={t("credentialsOnce")}
          onClose={() => setCredentials(null)}
        />
      )}
    </div>
  );
}

// ── Tab 2: devices ─────────────────────────────────────────────────────────
function DevicesTab() {
  const t = useTranslations("settings");
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["s-devices"], queryFn: fetchDevices });
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["s-devices"] });

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {(data?.devices ?? []).map((device) => (
        <div
          key={device.id}
          className="rounded-lg border border-border bg-surface p-4"
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <Smartphone className="size-5 text-fg-muted" />
              <div>
                <p className="text-sm font-semibold">
                  {device.manufacturer} {device.model}
                </p>
                <p className="text-xs text-fg-faint">
                  {device.operator} · v{device.app_version} · Android{" "}
                  {device.os_version}
                </p>
              </div>
            </div>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium",
                device.online
                  ? "bg-accent-soft text-accent"
                  : "bg-surface-3 text-fg-faint",
              )}
            >
              {device.online ? t("online") : t("offline")}
            </span>
          </div>
          <ul className="mt-3 space-y-2">
            {device.sims.map((sim) => (
              <li key={sim.id} className="flex items-center gap-2 text-sm">
                <span className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">
                  SIM {sim.sim_slot + 1}
                </span>
                <span className="tnum flex-1">{formatPhone(sim.number)}</span>
                <button
                  type="button"
                  onClick={() => {
                    const number = window.prompt(t("setNumber"), sim.number);
                    if (number) patchSim(sim.id, { number }).then(invalidate);
                  }}
                  className="text-xs text-accent hover:underline"
                >
                  {t("setNumber")}
                </button>
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={sim.recording_enabled}
                    onChange={(event) =>
                      patchSim(sim.id, {
                        recording_enabled: event.target.checked,
                      }).then(invalidate)
                    }
                    className="accent-[var(--accent)]"
                  />
                  {t("record")}
                </label>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => {
              if (window.confirm(`${t("deleteDevice")}?`))
                deleteDevice(device.id).then(invalidate);
            }}
            className="mt-3 flex items-center gap-1.5 text-xs text-fg-faint hover:text-danger"
          >
            <Trash2 className="size-3.5" /> {t("deleteDevice")}
          </button>
        </div>
      ))}
      {data && data.devices.length === 0 && (
        <p className="col-span-2 rounded-lg border border-border bg-surface p-8 text-center text-sm text-fg-faint">
          —
        </p>
      )}
    </div>
  );
}

// ── Tab 3 + 5: toggles (calls&SMS + account share the settings API) ────────
const COUNTRIES: Array<{ code: string; name: string; tz: string }> = [
  { code: "UZ", name: "Uzbekistan", tz: "Asia/Tashkent" },
  { code: "KZ", name: "Kazakhstan", tz: "Asia/Almaty" },
  { code: "KG", name: "Kyrgyzstan", tz: "Asia/Bishkek" },
  { code: "TJ", name: "Tajikistan", tz: "Asia/Dushanbe" },
  { code: "TM", name: "Turkmenistan", tz: "Asia/Ashgabat" },
  { code: "RU", name: "Russia", tz: "Europe/Moscow" },
  { code: "AZ", name: "Azerbaijan", tz: "Asia/Baku" },
  { code: "TR", name: "Türkiye", tz: "Europe/Istanbul" },
  { code: "AE", name: "UAE", tz: "Asia/Dubai" },
  { code: "SA", name: "Saudi Arabia", tz: "Asia/Riyadh" },
  { code: "GB", name: "United Kingdom", tz: "Europe/London" },
  { code: "DE", name: "Germany", tz: "Europe/Berlin" },
  { code: "US", name: "USA", tz: "America/New_York" },
  { code: "IN", name: "India", tz: "Asia/Kolkata" },
  { code: "CN", name: "China", tz: "Asia/Shanghai" },
];

const TIMEZONES = [
  "Asia/Tashkent",
  "Asia/Almaty",
  "Asia/Aqtobe",
  "Asia/Bishkek",
  "Asia/Dushanbe",
  "Asia/Ashgabat",
  "Europe/Moscow",
  "Europe/Samara",
  "Asia/Yekaterinburg",
  "Asia/Novosibirsk",
  "Asia/Baku",
  "Europe/Istanbul",
  "Asia/Dubai",
  "Asia/Riyadh",
  "Europe/Kyiv",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "Asia/Kolkata",
  "Asia/Shanghai",
];

function TogglesTab({ mode }: { mode: "callsSms" | "account" }) {
  const t = useTranslations("settings");
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["s-account"],
    queryFn: fetchAccountSettings,
  });
  const save = useMutation({
    mutationFn: saveAccountSettings,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["s-account"] }),
  });
  const settings = data?.settings;
  const rows =
    mode === "callsSms"
      ? ([["recording_enabled", t("record")]] as const)
      : ([
          ["contact_import_enabled", "Импорт контактов"],
          ["pin_enabled", "PIN-код"],
        ] as const);
  return (
    <div className="max-w-md space-y-3">
      {settings &&
        rows.map(([key, label]) => (
          <label
            key={key}
            className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 text-sm"
          >
            {label}
            <input
              type="checkbox"
              checked={settings[key]}
              onChange={(event) => save.mutate({ [key]: event.target.checked })}
              className="size-4 accent-[var(--accent)]"
            />
          </label>
        ))}
      {mode === "account" && settings && (
        <div className="space-y-3 rounded-lg border border-border bg-surface p-4">
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("country")}
            </span>
            <select
              value={settings.country}
              data-testid="account-country"
              onChange={(event) => {
                const picked = COUNTRIES.find(
                  (item) => item.code === event.target.value,
                );
                save.mutate({
                  country: event.target.value,
                  // Picking a country pre-sets its default zone (still editable).
                  ...(picked ? { timezone: picked.tz } : {}),
                });
              }}
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
            >
              {!COUNTRIES.some((item) => item.code === settings.country) && (
                <option value={settings.country}>
                  {settings.country || "—"}
                </option>
              )}
              {COUNTRIES.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("timezone")}
            </span>
            <select
              value={settings.timezone}
              data-testid="account-timezone"
              onChange={(event) => save.mutate({ timezone: event.target.value })}
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
            >
              {!TIMEZONES.includes(settings.timezone) && (
                <option value={settings.timezone}>
                  {settings.timezone || "—"}
                </option>
              )}
              {TIMEZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </select>
          </label>
          <p className="text-xs leading-relaxed text-fg-faint">
            {t("timezoneNote")}
          </p>
        </div>
      )}
      {mode === "callsSms" && (
        <>
          <button
            type="button"
            onClick={() =>
              useToastStore
                .getState()
                .push({ kind: "info", text: t("filtersModal") })
            }
            className="w-full rounded-lg border border-border bg-surface px-4 py-3 text-left text-sm hover:bg-surface-2"
          >
            {t("filtersModal")}…
          </button>
          <p className="rounded-lg border border-dashed border-border px-4 py-3 text-sm text-fg-faint">
            {t("smsTemplates")}
          </p>
        </>
      )}
    </div>
  );
}

// ── Tab 4: integration (moizvonki-style CRM grid + API params panel) ───────
const SPECIAL_TILES = [
  {
    provider: "bitrix24",
    label: "Bitrix24",
    style: { color: "#0BA7EF" },
    logo: (
      <span className="text-lg font-extrabold" style={{ color: "#0BA7EF" }}>
        Bitrix<span className="text-[#005893]">24</span>
      </span>
    ),
  },
  {
    provider: "amocrm",
    label: "amoCRM",
    style: { color: "#339DC7" },
    logo: (
      <span className="text-lg font-bold italic" style={{ color: "#339DC7" }}>
        amoCRM.
      </span>
    ),
  },
  {
    provider: "odoo",
    label: "Odoo",
    style: { color: "#714B67" },
    logo: (
      <span className="text-lg font-extrabold" style={{ color: "#714B67" }}>
        odoo
      </span>
    ),
  },
] as const;

function IntegrationTab() {
  const t = useTranslations("settings");
  const queryClient = useQueryClient();
  const { data: apiKey } = useQuery({
    queryKey: ["s-apikey"],
    queryFn: fetchApiKey,
  });
  const { data: webhook } = useQuery({
    queryKey: ["s-webhook"],
    queryFn: fetchWebhook,
  });
  const { data: integrations } = useQuery({
    queryKey: ["s-integrations"],
    queryFn: fetchIntegrations,
  });
  const { data: catalog } = useQuery({
    queryKey: ["s-crm-catalog"],
    queryFn: fetchCrmCatalog,
  });
  const [freshKey, setFreshKey] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const apiHost =
    typeof window !== "undefined" ? window.location.hostname : "";

  const rotate = useMutation({
    mutationFn: rotateApiKey,
    onSuccess: (body) => {
      setFreshKey(body.api_key);
      queryClient.invalidateQueries({ queryKey: ["s-apikey"] });
    },
  });
  const saveHook = useMutation({
    mutationFn: (value: string) => saveWebhook(value),
    onSuccess: (body) => {
      if (body.secret) setSecret(body.secret);
      queryClient.invalidateQueries({ queryKey: ["s-webhook"] });
    },
  });
  const test = useMutation({
    mutationFn: testWebhook,
    onSuccess: (body) =>
      useToastStore.getState().push({
        kind: body.success ? "success" : "error",
        text: `${t("testDelivery")}: ${body.delivery_status ?? body.error}`,
      }),
  });

  const statusFor = (provider: string) => {
    const row = integrations?.integrations.find(
      (integration) => integration.provider === provider,
    );
    if (!row?.is_enabled) return null;
    return row.last_status === "error" ? "error" : "ok";
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      {/* ── CRM systems grid ── */}
      <section className="rounded-lg border border-border bg-surface">
        <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
          {t("crmSystems")}
        </p>
        <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 xl:grid-cols-4">
          {SPECIAL_TILES.map((tile) => {
            const status = statusFor(tile.provider);
            return (
              <Link
                key={tile.provider}
                href={`/cabinet/settings/integrations/${tile.provider}`}
                data-testid={`crm-tile-${tile.provider}`}
                className="relative grid h-24 place-items-center rounded-lg border border-border bg-white transition hover:-translate-y-0.5 hover:shadow-md dark:bg-surface-2"
              >
                {status && (
                  <span
                    className={cn(
                      "absolute right-2 top-2 size-2.5 rounded-full",
                      status === "ok" ? "bg-accent" : "bg-danger",
                    )}
                  />
                )}
                {tile.logo}
              </Link>
            );
          })}
          {(catalog?.entries ?? []).map((entry) => (
            <a
              key={entry.id}
              href={entry.site_url}
              target="_blank"
              rel="noreferrer noopener"
              className="grid h-24 place-items-center rounded-lg border border-border bg-white p-2 transition hover:-translate-y-0.5 hover:shadow-md dark:bg-surface-2"
            >
              {entry.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={entry.logo_url}
                  alt={entry.name}
                  className="max-h-16 max-w-full object-contain"
                />
              ) : (
                <span className="text-center text-sm font-semibold text-fg-muted">
                  {entry.name}
                </span>
              )}
            </a>
          ))}
        </div>
      </section>

      {/* ── API parameters panel ── */}
      <section className="h-fit rounded-lg border border-border bg-surface">
        <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
          {t("apiParams")}
        </p>
        <div className="space-y-3 p-4">
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-fg-muted">
              {t("apiAddress")}
            </span>
            <input
              readOnly
              value={apiHost}
              className="tnum w-full rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-xs"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 flex items-center justify-between text-xs text-fg-muted">
              {t("apiKeyLabel")}
              <button
                type="button"
                onClick={() => rotate.mutate()}
                className="inline-flex items-center gap-1 font-semibold text-accent hover:underline"
              >
                <KeyRound className="size-3" /> {t("rotateKey")}
              </button>
            </span>
            <input
              readOnly
              value={freshKey ?? apiKey?.api_key_masked ?? "—"}
              className="tnum w-full rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-xs"
            />
          </label>
          {freshKey && (
            <p className="text-xs text-warning">{t("credentialsOnce")}</p>
          )}
          <p className="text-xs leading-relaxed text-fg-muted">
            {t("apiParamsNote")}
          </p>
          <a
            href="/docs/api"
            target="_blank"
            className="inline-block text-xs font-semibold text-accent hover:underline"
          >
            {t("apiDocsLink")}
          </a>

          <div className="border-t border-border pt-3">
            <p className="text-sm font-semibold">{t("webhookUrl")}</p>
            <input
              value={url ?? webhook?.webhook_url ?? ""}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://crm.example.uz/hook"
              className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
            />
            {secret && (
              <p className="tnum mt-2 break-all rounded-md bg-warning/10 p-2 font-mono text-xs">
                secret: {secret}
              </p>
            )}
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={url === null}
                onClick={() => url !== null && saveHook.mutate(url)}
                className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg disabled:opacity-50"
              >
                OK
              </button>
              <button
                type="button"
                disabled={!webhook?.webhook_url}
                onClick={() => test.mutate()}
                className="rounded-md border border-border px-3 py-1.5 text-xs disabled:opacity-50"
              >
                {t("testDelivery")}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

// ── Tab 6: license & payment ───────────────────────────────────────────────
function LicenseTab() {
  const t = useTranslations("settings");
  const { data } = useQuery({ queryKey: ["s-license"], queryFn: fetchLicense });
  if (!data)
    return <div className="h-40 animate-pulse rounded-lg bg-surface-2" />;

  return (
    <div className="max-w-lg space-y-4" data-testid="license-tab">
      <div className="rounded-lg border border-border bg-surface p-4">
        {data.status === "trial" && data.trial_days_left !== null ? (
          <p className="text-sm">
            {t("trialLeft")}: <b className="tnum">{data.trial_days_left}</b>
          </p>
        ) : (
          <p className="tnum text-sm text-fg-muted">
            {t("period")}: {data.current_period_start?.slice(0, 10)} —{" "}
            {data.current_period_end?.slice(0, 10)}
          </p>
        )}
        <dl className="tnum mt-3 space-y-1.5 text-sm">
          <div className="flex justify-between">
            <dt className="text-fg-muted">{t("seats")}</dt>
            <dd data-testid="license-seats">{data.seats}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-fg-muted">{t("perSeat")}</dt>
            <dd>{formatUzs(data.price_per_operator_uzs)} UZS</dd>
          </div>
          <div className="flex justify-between border-t border-border pt-1.5 font-semibold">
            <dt>{t("total")}</dt>
            <dd data-testid="license-total">{formatUzs(data.total_uzs)} UZS</dd>
          </div>
        </dl>
        <div className="mt-3 flex gap-2">
          {["payme", "click", "manual"].map((provider) => (
            <button
              key={provider}
              type="button"
              onClick={() =>
                useToastStore
                  .getState()
                  .push({ kind: "info", text: `${t("pay")}: ${provider}` })
              }
              className="flex-1 rounded-md bg-accent px-3 py-2 text-xs font-semibold capitalize text-accent-fg hover:opacity-90"
            >
              {provider}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-border bg-surface">
        <p className="border-b border-border px-4 py-2.5 text-sm font-semibold">
          {t("payments")}
        </p>
        <ul className="divide-y divide-border">
          {data.payments.length === 0 && (
            <li className="px-4 py-4 text-center text-xs text-fg-faint">—</li>
          )}
          {data.payments.map((payment) => (
            <li
              key={payment.id}
              className="flex items-center gap-2 px-4 py-2 text-sm"
            >
              <span className="flex-1 capitalize">{payment.provider}</span>
              <span className="tnum">{formatUzs(payment.amount_uzs)} UZS</span>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs",
                  payment.status === "approved"
                    ? "bg-accent-soft text-accent"
                    : "bg-surface-3 text-fg-muted",
                )}
              >
                {payment.status}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const t = useTranslations("settings");
  const tNav = useTranslations("nav");
  const [tab, setTab] = useState<SettingsTab>("usersGroups");

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">{tNav("settings")}</h1>
      <div className="mb-5 flex flex-wrap gap-1.5" data-testid="settings-tabs">
        {TABS.map((option) => (
          <button
            key={option}
            type="button"
            data-testid={`settings-tab-${option}`}
            onClick={() => setTab(option)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium",
              tab === option
                ? "bg-accent text-accent-fg"
                : "border border-border text-fg-muted hover:bg-surface-2",
            )}
          >
            {t(option)}
          </button>
        ))}
      </div>

      {tab === "usersGroups" && <UsersTab />}
      {tab === "devices" && <DevicesTab />}
      {tab === "callsSms" && <TogglesTab mode="callsSms" />}
      {tab === "integration" && <IntegrationTab />}
      {tab === "account" && <TogglesTab mode="account" />}
      {tab === "license" && <LicenseTab />}
    </div>
  );
}
