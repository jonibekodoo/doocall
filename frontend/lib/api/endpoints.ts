/** Typed endpoint functions for every Phase-5 cabinet API. */

import { api, del, get, post, put } from "./client";

const patchJson = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });
import type {
  ApiEnvelope,
  BillingStatusResponse,
  CallDetailResponse,
  CallRow,
  CallsListResponse,
  ContactRow,
  DashboardResponse,
} from "./types";
import { buildCallsQuery, type CallFilters } from "@/lib/filters";

// ── Dashboard ──────────────────────────────────────────────────────────────
export const fetchDashboard = (period: string, operator?: number) =>
  get<DashboardResponse>(
    `/dashboard?period=${period}${operator ? `&operator=${operator}` : ""}`,
  );

// ── Calls ──────────────────────────────────────────────────────────────────
export const fetchCalls = (filters: CallFilters) =>
  get<CallsListResponse>(`/calls${buildCallsQuery(filters)}`);

export const fetchCallDetail = (id: number) =>
  get<CallDetailResponse>(`/calls/${id}`);

export const fetchColumns = () =>
  get<{ success: boolean; columns: string[] }>("/calls/columns");

export const saveColumns = (columns: string[]) =>
  put<{ success: boolean; columns: string[] }>("/calls/columns", { columns });

export const startExport = (
  format: "csv" | "xlsx",
  filters: Record<string, string>,
) =>
  post<{ success: boolean; export_id: number }>("/calls/export", {
    format,
    filters,
  });

export interface ExportStatus extends ApiEnvelope {
  id: number;
  status: "pending" | "done" | "failed";
  url: string | null;
  row_count: number;
}
export const fetchExport = (id: number) =>
  get<ExportStatus>(`/calls/export/${id}`);

// ── Contacts ───────────────────────────────────────────────────────────────
export interface ContactsList extends ApiEnvelope {
  count: number;
  page: number;
  results: ContactRow[];
}
export const fetchContacts = (q = "", page = 1) =>
  get<ContactsList>(`/contacts?q=${encodeURIComponent(q)}&page=${page}`);

export const createContact = (payload: {
  name: string;
  phones: string[];
  note?: string;
  responsible_id?: number | null;
}) => post<{ success: boolean; contact: ContactRow }>("/contacts", payload);

export const updateContact = (
  id: number,
  payload: Partial<{
    name: string;
    phones: string[];
    note: string;
    responsible_id: number | null;
  }>,
) => put<{ success: boolean; contact: ContactRow }>(`/contacts/${id}`, payload);

export const deleteContact = (id: number) =>
  del<ApiEnvelope>(`/contacts/${id}`);

export const fetchContactDetail = (id: number) =>
  get<{ success: boolean; contact: ContactRow; calls: CallRow[] }>(
    `/contacts/${id}`,
  );

export const contactFromCall = (callId: number, name?: string) =>
  post<{ success: boolean; contact: ContactRow; linked_calls: number }>(
    `/contacts/from-call/${callId}`,
    name ? { name } : {},
  );

// ── Reports ────────────────────────────────────────────────────────────────
export interface GeneralReport {
  all: { total: number; answered: number; missed: number };
  inbound: { total: number; answered: number; missed: number };
  outbound: { total: number; answered: number; missed: number };
  total_duration_sec: number;
}
export const fetchGeneralReport = (qs = "") =>
  get<{ success: boolean; report: GeneralReport }>(`/reports/general${qs}`);

export interface WeekdayRow {
  weekday: number;
  total: number;
  inbound: number;
  outbound: number;
  answered: number;
  missed: number;
}
export const fetchWeekdayMatrix = (qs = "") =>
  get<{ success: boolean; report: WeekdayRow[] }>(
    `/reports/weekday-matrix${qs}`,
  );

export interface PeriodRow {
  bucket: string;
  total: number;
  answered: number;
  missed: number;
}
export const fetchPeriodCounts = (group: string, unique: boolean, qs = "") =>
  get<{ success: boolean; report: PeriodRow[] }>(
    `/reports/period-counts?group=${group}&unique=${unique}${qs ? `&${qs.slice(1)}` : ""}`,
  );

export interface EmployeeRow {
  operator_id: number;
  user_name: string;
  full_name: string;
  total: number;
  inbound: number;
  outbound: number;
  answered: number;
  missed: number;
  duration_minutes: number;
}
export const fetchPerEmployee = (qs = "") =>
  get<{ success: boolean; report: EmployeeRow[] }>(
    `/reports/per-employee${qs}`,
  );

export interface ClientRow {
  counterparty_number: string;
  name: string | null;
  total: number;
  answered: number;
  missed: number;
  duration: number;
  last_call: string;
}
export const fetchPerClient = (qs = "") =>
  get<{ success: boolean; report: ClientRow[] }>(`/reports/per-client${qs}`);

export interface UnansweredRow {
  counterparty_number: string;
  name: string | null;
  last_attempt: string;
  last_success: string | null;
  attempts_since_success: number;
  operator_id: number | null;
}
export const fetchUnanswered = (qs = "") =>
  get<{ success: boolean; report: UnansweredRow[] }>(
    `/reports/unanswered${qs}`,
  );

export interface LastContactRow {
  call_record_id: number;
  counterparty_number: string;
  name: string | null;
  last_call: string;
  direction: string;
  status: string;
  operator_id: number | null;
  duration: number;
}
export const fetchLastContact = (qs = "") =>
  get<{ success: boolean; report: LastContactRow[] }>(
    `/reports/last-contact${qs}`,
  );

// ── Settings ───────────────────────────────────────────────────────────────
export interface OperatorItem {
  id: number;
  user_id: number;
  user_name: string;
  full_name: string;
  group_id: number | null;
  is_active: boolean;
  email: string;
  is_company_admin: boolean;
  phones?: Array<{ sim_slot: number; number: string }>;
}
export const fetchUsers = () =>
  get<{
    success: boolean;
    operators: OperatorItem[];
    web_users: Array<{
      id: number;
      email: string;
      is_company_admin: boolean;
      is_active: boolean;
    }>;
  }>("/settings/users");

export interface NewOperatorResponse extends ApiEnvelope {
  operator: OperatorItem;
  credentials: { user_name: string; password: string; api_key: string };
}
export const createOperator = (payload: {
  user_name: string;
  full_name?: string;
  phone?: string;
  phone2?: string;
  group_id?: number | null;
}) => post<NewOperatorResponse>("/settings/users", payload);

export const patchOperator = (
  id: number,
  payload: Partial<{
    full_name: string;
    group_id: number | null;
    is_active: boolean;
  }>,
) =>
  patchJson<{ success: boolean; operator: OperatorItem }>(
    `/settings/users/${id}`,
    payload,
  );

export const fetchGroups = () =>
  get<{ success: boolean; groups: Array<{ id: number; name: string }> }>(
    "/settings/groups",
  );
export const createGroup = (name: string) =>
  post<{ success: boolean; group: { id: number; name: string } }>(
    "/settings/groups",
    { name },
  );
export const deleteGroup = (id: number) =>
  del<ApiEnvelope>(`/settings/groups/${id}`);

export interface DeviceItem {
  id: number;
  operator: string;
  operator_id: number;
  device_id: string;
  manufacturer: string;
  model: string;
  app_version: string;
  os_version: string;
  last_seen_at: string | null;
  online: boolean;
  sims: Array<{
    id: number;
    sim_slot: number;
    number: string;
    recording_enabled: boolean;
  }>;
}
export const fetchDevices = () =>
  get<{ success: boolean; devices: DeviceItem[] }>("/settings/devices");
export const patchSim = (
  id: number,
  payload: Partial<{ recording_enabled: boolean; number: string }>,
) => patchJson<ApiEnvelope>(`/settings/sims/${id}`, payload);
export const deleteDevice = (id: number) =>
  del<ApiEnvelope>(`/settings/devices/${id}`);

export interface AccountSettings {
  contact_import_enabled: boolean;
  recording_enabled: boolean;
  pin_enabled: boolean;
  country: string;
  timezone: string;
}
export const fetchAccountSettings = () =>
  get<{ success: boolean; settings: AccountSettings }>("/settings/account");
export const saveAccountSettings = (payload: Partial<AccountSettings>) =>
  put<{ success: boolean; settings: AccountSettings }>(
    "/settings/account",
    payload,
  );

export interface BillingOverview extends ApiEnvelope {
  balance_uzs: number;
  month_accrued_uzs: number;
  price_per_operator_uzs: number;
  daily_rate_uzs: number;
  seats: number;
  blocked: boolean;
  unpaid_statement: {
    month: string;
    total_uzs: number;
    status: string;
  } | null;
}

export const fetchBillingOverview = () =>
  get<BillingOverview>("/billing/overview");

export const fetchBillingCharges = (month: string) =>
  get<{
    success: boolean;
    month: string;
    total_uzs: number;
    days: Array<{ date: string; total_uzs: number; operators: number }>;
    charges: Array<{
      date: string;
      operator_name: string;
      amount_uzs: number;
      price_per_operator_uzs: number;
    }>;
  }>(`/billing/charges?month=${month}`);

export const fetchBillingStatements = () =>
  get<{
    success: boolean;
    statements: Array<{
      month: string;
      total_uzs: number;
      status: string;
      settled_at: string | null;
    }>;
  }>("/billing/statements");

export interface BillingNotificationRow {
  id: number;
  kind: string;
  message: string;
  amount_uzs: number | null;
  is_read: boolean;
  created_at: string;
}

export const fetchNotifications = () =>
  get<{
    success: boolean;
    unread: number;
    notifications: BillingNotificationRow[];
  }>("/notifications");

export const markNotificationsRead = () =>
  post<{ success: boolean; marked: number }>("/notifications/read");

export const markNotificationRead = (id: number) =>
  post<{ success: boolean }>(`/notifications/${id}/read`);

export const submitManualPayment = (amount_uzs: number) =>
  post<{
    success: boolean;
    payment: { id: number; amount_uzs: number; status: string };
  }>("/billing/pay", { provider: "manual", amount_uzs });

export const fetchApiKey = () =>
  get<{ success: boolean; api_key_masked: string | null }>("/settings/api-key");
export const rotateApiKey = () =>
  post<{ success: boolean; api_key: string }>("/settings/api-key");

export const fetchWebhook = () =>
  get<{ success: boolean; webhook_url: string | null; secret_set: boolean }>(
    "/settings/webhook",
  );
export const saveWebhook = (url: string) =>
  put<{ success: boolean; webhook_url: string | null; secret: string | null }>(
    "/settings/webhook",
    { url },
  );
export const testWebhook = () =>
  post<{ success: boolean; delivery_status?: number; error?: string }>(
    "/settings/webhook/test",
  );

export interface CrmIntegrationRow {
  provider: "amocrm" | "bitrix24" | "odoo";
  is_enabled: boolean;
  configured: boolean;
  config: Record<string, string>;
  last_status: "" | "ok" | "error";
  last_error: string;
  last_delivery_at: string | null;
}

export const fetchIntegrations = () =>
  get<{ success: boolean; integrations: CrmIntegrationRow[] }>(
    "/settings/integrations",
  );

export const saveIntegration = (
  provider: string,
  body: { is_enabled: boolean; config: Record<string, string> },
) =>
  put<{ success: boolean; integration: CrmIntegrationRow }>(
    `/settings/integrations/${provider}`,
    body,
  );

export const testIntegration = (provider: string) =>
  post<{ success: boolean; detail?: string; error?: string }>(
    `/settings/integrations/${provider}/test`,
  );

export interface CrmCatalogTile {
  id: number;
  name: string;
  site_url: string;
  logo_url: string | null;
}

export const fetchCrmCatalog = () =>
  get<{ success: boolean; entries: CrmCatalogTile[] }>(
    "/settings/integrations/catalog",
  );

export interface LicenseInfo extends ApiEnvelope {
  status: string;
  trial_ends_at: string | null;
  trial_days_left: number | null;
  current_period_start: string | null;
  current_period_end: string | null;
  seats: number;
  price_per_operator_uzs: number;
  total_uzs: number;
  payments: Array<{
    id: number;
    provider: string;
    amount_uzs: number;
    status: string;
    created_at: string;
  }>;
}
export const fetchLicense = () => get<LicenseInfo>("/settings/license");

export const fetchBillingStatus = () =>
  get<BillingStatusResponse>("/billing/status");
