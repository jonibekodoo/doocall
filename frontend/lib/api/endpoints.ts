/** Typed endpoint functions for every Phase-5 cabinet API. */

import { api, del, get, post, put } from "./client";

const patchJson = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });
import type {
  ApiEnvelope,
  DialCommandState,
  DialDevice,
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
/** Shared report filter (same params as the Calls list): dates are
 * YYYY-MM-DD in the company time zone; omitted = no bound. */
export interface ReportFilters {
  dateFrom?: string;
  dateTo?: string;
  employees?: number[];
}

/** "?date_from=…&date_to=…&employees=1,2" (or "" when unfiltered). */
export const reportQuery = (
  filters: ReportFilters = {},
  extra: Record<string, string> = {},
): string => {
  const query = new URLSearchParams(extra);
  if (filters.dateFrom) query.set("date_from", filters.dateFrom);
  if (filters.dateTo) query.set("date_to", filters.dateTo);
  if (filters.employees?.length) query.set("employees", filters.employees.join(","));
  const text = query.toString();
  return text ? `?${text}` : "";
};

export interface GeneralReport {
  all: { total: number; answered: number; missed: number };
  inbound: { total: number; answered: number; missed: number };
  outbound: { total: number; answered: number; missed: number };
  total_duration_sec: number;
}
export const fetchGeneralReport = (filters: ReportFilters = {}) =>
  get<{ success: boolean; report: GeneralReport }>(
    `/reports/general${reportQuery(filters)}`,
  );

export interface WeekdayRow {
  weekday: number;
  total: number;
  inbound: number;
  outbound: number;
  answered: number;
  missed: number;
}
export const fetchWeekdayMatrix = (filters: ReportFilters = {}) =>
  get<{ success: boolean; report: WeekdayRow[] }>(
    `/reports/weekday-matrix${reportQuery(filters)}`,
  );

export interface PeriodRow {
  bucket: string;
  total: number;
  answered: number;
  missed: number;
}
export const fetchPeriodCounts = (
  group: string,
  unique: boolean,
  filters: ReportFilters = {},
) =>
  get<{ success: boolean; report: PeriodRow[] }>(
    `/reports/period-counts${reportQuery(filters, { group, unique: String(unique) })}`,
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
export const fetchPerEmployee = (filters: ReportFilters = {}) =>
  get<{ success: boolean; report: EmployeeRow[] }>(
    `/reports/per-employee${reportQuery(filters)}`,
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
export const fetchPerClient = (filters: ReportFilters = {}) =>
  get<{ success: boolean; report: ClientRow[] }>(
    `/reports/per-client${reportQuery(filters)}`,
  );

export interface UnansweredRow {
  counterparty_number: string;
  name: string | null;
  last_attempt: string;
  last_success: string | null;
  attempts_since_success: number;
  operator_id: number | null;
}
export const fetchUnanswered = (filters: ReportFilters = {}) =>
  get<{ success: boolean; report: UnansweredRow[] }>(
    `/reports/unanswered${reportQuery(filters)}`,
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
export const fetchLastContact = (filters: ReportFilters = {}) =>
  get<{ success: boolean; report: LastContactRow[] }>(
    `/reports/last-contact${reportQuery(filters)}`,
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
  /** Default calling code (digits, no "+") for numbers typed without one. */
  phone_code: string;
}
export const fetchAccountSettings = () =>
  get<{ success: boolean; settings: AccountSettings }>("/settings/account");
export const saveAccountSettings = (payload: Partial<AccountSettings>) =>
  put<{ success: boolean; settings: AccountSettings }>(
    "/settings/account",
    payload,
  );

export interface PaymentProviderOption {
  name: string;
  label: string;
  logo_url: string | null;
}

export interface BillingOverview extends ApiEnvelope {
  balance_uzs: number;
  month_accrued_uzs: number;
  /** Usage accrued since the last deduction (next statement amount so far). */
  cycle_accrued_uzs: number;
  /** Billing cycle: payment date → same day next month (balance charged on cycle_end). */
  cycle_start: string | null;
  cycle_end: string | null;
  /** Days the balance covers at the current burn rate (null: trial / no operators). */
  days_left: number | null;
  runs_out_on: string | null;
  price_per_operator_uzs: number;
  daily_rate_uzs: number;
  seats: number;
  blocked: boolean;
  providers: PaymentProviderOption[];
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
      period_start: string | null;
      period_end: string | null;
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

export const paylovPay = (
  amount_uzs: number,
  card_number: string,
  expire_date: string,
) =>
  post<{
    success: boolean;
    payment_id: number;
    otp_phone: string;
    needs_otp: boolean;
  }>("/billing/paylov/pay", { amount_uzs, card_number, expire_date });

export const paylovConfirm = (payment_id: number, otp: string) =>
  post<{ success: boolean; status: string; balance_uzs: number }>(
    "/billing/paylov/confirm",
    { payment_id, otp },
  );

// ── Paylov saved cards + auto-payment ────────────────────────────────────────
export interface SavedCard {
  id: number;
  /** Masked PAN as returned by Paylov, e.g. "860000******9999". */
  masked_number: string;
  owner: string;
  /** "Uzcard" | "Humo" */
  vendor: string;
  /** YYMM */
  expire: string;
  is_active: boolean;
}

export type AutoPayAmountMode = "month" | "fixed";

export interface AutoPayState {
  is_enabled: boolean;
  card_id: number | null;
  amount_mode: AutoPayAmountMode;
  fixed_amount_uzs: number | null;
  monthly_limit_uzs: number | null;
  /** One month of service at the current operator count. */
  default_amount_uzs: number;
  effective_amount_uzs: number;
  effective_limit_uzs: number;
  spent_30d_uzs: number;
  last_attempt_at: string | null;
  last_status: "" | "ok" | "failed" | "pending";
  last_error: string;
  fail_streak: number;
  disabled_reason: string;
  consent_at: string | null;
}

export interface AutoPayOverview extends ApiEnvelope {
  /** Company admins only may link cards / change auto-payment. */
  can_manage: boolean;
  /** Paylov enabled + configured + platform switch on. */
  available: boolean;
  cards: SavedCard[];
  autopay: AutoPayState;
}

export interface AutoPaySettingsInput {
  is_enabled: boolean;
  card_id: number | null;
  amount_mode: AutoPayAmountMode;
  fixed_amount_uzs: number | null;
  monthly_limit_uzs: number | null;
  /** Must be true when enabling (explicit cardholder authorization). */
  consent: boolean;
}

export const fetchAutoPay = () => get<AutoPayOverview>("/billing/autopay");

export const saveAutoPay = (body: AutoPaySettingsInput) =>
  put<AutoPayOverview>("/billing/autopay", body);

/** Step 1 of linking a card: Paylov sends an SMS code to the cardholder. */
export const linkCardStart = (card_number: string, expire_date: string) =>
  post<{ success: boolean; card_ref: number; otp_phone: string }>(
    "/billing/cards",
    { card_number, expire_date },
  );

export const linkCardConfirm = (card_ref: number, otp: string) =>
  post<{ success: boolean; card: SavedCard }>("/billing/cards/confirm", {
    card_ref,
    otp,
  });

export const removeSavedCard = (id: number) =>
  del<{ success: boolean }>(`/billing/cards/${id}`);

export const payWithSavedCard = (id: number, amount_uzs: number) =>
  post<{ success: boolean; status: string; balance_uzs: number }>(
    `/billing/cards/${id}/pay`,
    { amount_uzs },
  );

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
  provider: "amocrm" | "bitrix24" | "odoo" | "kotib";
  is_enabled: boolean;
  configured: boolean;
  config: Record<string, string>;
  last_status: "" | "ok" | "error";
  last_error: string;
  last_delivery_at: string | null;
}

/** CRM users + our operators for the operator → CRM user mapping (Bitrix24
 * USER_ID, amoCRM manager). success:false (with ``error``) when the CRM
 * users can't be read (e.g. missing scope) — operators still come back so
 * IDs can be typed in by hand. */
export interface CrmUser {
  id: string | number;
  name: string;
  email: string;
  phone: string;
  position: string;
}
export interface CrmOperator {
  id: number;
  full_name: string;
  user_name: string;
  phones: string[] | string;
}
export interface CrmUsersResponse {
  success: boolean;
  error?: string;
  users?: CrmUser[];
  operators: CrmOperator[];
  suggestions?: Record<string, string>;
}
export const fetchCrmUsers = (provider: "bitrix24" | "amocrm") =>
  get<CrmUsersResponse>(`/settings/integrations/${provider}/users`);

export type Bitrix24User = CrmUser;
export type Bitrix24Operator = CrmOperator;
export type Bitrix24UsersResponse = CrmUsersResponse;
export const fetchBitrix24Users = () => fetchCrmUsers("bitrix24");

/** Kotib AI results webhook (connected Kotib only). */
export const saveKotibAnalysisSecret = (secret: string) =>
  put<{ success: boolean }>("/settings/integrations/kotib/analysis", { secret });
export const rotateKotibAnalysisUrl = () =>
  post<{ success: boolean }>("/settings/integrations/kotib/analysis/rotate");

export const fetchIntegrations = () =>
  get<{ success: boolean; integrations: CrmIntegrationRow[] }>(
    "/settings/integrations",
  );

export const saveIntegration = (
  provider: string,
  body: { is_enabled: boolean; config: Record<string, unknown> },
) =>
  put<{ success: boolean; integration: CrmIntegrationRow }>(
    `/settings/integrations/${provider}`,
    body,
  );

export const disconnectIntegration = (provider: string) =>
  del<{ success: boolean; integration: CrmIntegrationRow }>(
    `/settings/integrations/${provider}`,
  );

export interface CrmDeliveryRow {
  id: number;
  call_id: number;
  counterparty_number: string;
  counterparty_name: string | null;
  direction: string;
  call_status: string;
  start_time: string;
  status: "ok" | "error";
  error: string;
  is_retry: boolean;
  created_at: string;
}

export const fetchIntegrationDeliveries = (
  provider: string,
  params: { status?: "" | "ok" | "error"; page?: number } = {},
) =>
  get<{
    success: boolean;
    count: number;
    page: number;
    pages: number;
    summary: { ok_30d: number; error_30d: number };
    deliveries: CrmDeliveryRow[];
  }>(
    `/settings/integrations/${provider}/deliveries?status=${params.status ?? ""}&page=${params.page ?? 1}`,
  );

export const retryIntegrationDelivery = (provider: string, callId: number) =>
  post<{ success: boolean; error: string; delivery: CrmDeliveryRow }>(
    `/settings/integrations/${provider}/deliveries/${callId}/retry`,
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

// ── AI analysis (Kotib) ────────────────────────────────────────────────────
export interface AiStatus extends ApiEnvelope {
  kotib_connected: boolean;
  has_analyses: boolean;
  is_admin: boolean;
}
export const fetchAiStatus = () => get<AiStatus>("/ai/status");

export interface AiAnalysisRow {
  id: number;
  call_id: number | null;
  start_time: string;
  operator: { id: number; full_name: string } | null;
  phone: string;
  /** Kotib's final score — usually 0–100, can be negative. */
  final_score: number;
  summary: string;
  has_violation: boolean;
}

export interface AiAnalysisFilters {
  dateFrom?: string;
  dateTo?: string;
  employees?: number[];
  minScore?: number;
  maxScore?: number;
  violations?: boolean;
  search?: string;
  page?: number;
}

export interface AiAnalysesResponse extends ApiEnvelope {
  count: number;
  pages: number;
  page: number;
  summary: { count: number; avg_score: number | null; violations: number };
  analyses: AiAnalysisRow[];
}

export const buildAiQuery = (filters: AiAnalysisFilters): string => {
  const query = new URLSearchParams();
  if (filters.dateFrom) query.set("date_from", filters.dateFrom);
  if (filters.dateTo) query.set("date_to", filters.dateTo);
  if (filters.employees?.length) query.set("employees", filters.employees.join(","));
  if (filters.minScore !== undefined) query.set("min_score", String(filters.minScore));
  if (filters.maxScore !== undefined) query.set("max_score", String(filters.maxScore));
  if (filters.violations) query.set("violations", "1");
  if (filters.search) query.set("search", filters.search);
  if (filters.page && filters.page > 1) query.set("page", String(filters.page));
  const text = query.toString();
  return text ? `?${text}` : "";
};

export const fetchAiAnalyses = (filters: AiAnalysisFilters) =>
  get<AiAnalysesResponse>(`/ai/analyses${buildAiQuery(filters)}`);

export interface AiPromptScore {
  key: string;
  name: string;
  score: number | null;
  /** Sanitised server-side (allowlist) — the only HTML we render. */
  comment_html: string;
  is_violation: boolean;
}

export interface AiAnalysisDetail extends AiAnalysisRow {
  end_time: string | null;
  conversation_text: string;
  prompt_scores: AiPromptScore[];
  client_data: {
    phone_number: string;
    summary: string;
    answers: { key: string; name: string; value: unknown }[];
  } | null;
  call: {
    id: number;
    duration: number;
    direction: "inbound" | "outbound" | "internal";
    has_audio: boolean;
  } | null;
  signature_verified: boolean;
  received_at: string;
}

export const fetchAiAnalysis = (id: number) =>
  get<{ success: boolean; analysis: AiAnalysisDetail }>(`/ai/analyses/${id}`);

// ── Remote Dial (cabinet → operator's phone) ───────────────────────────────
/** Admins get every company device, operators only their own. Accepts a bare
 * list or a {devices: [...]} envelope. */
export const fetchDialDevices = async (): Promise<DialDevice[]> => {
  const body = await get<DialDevice[] | { devices?: DialDevice[] }>(
    "/dial/devices",
  );
  return Array.isArray(body) ? body : (body?.devices ?? []);
};

/** 200 {command_id, status:"sent"}; 409 device_offline (body carries the
 * command_id + status "offline"); 429 rate limited; 400 invalid number. */
export const startDial = (body: {
  device_id: string;
  number: string;
  idempotency_key: string;
}) =>
  post<{ success: boolean; command_id: string; status: "sent" }>("/dial", body);

/** The backend wraps it as {success, command: {…}, now}; a bare state is
 * accepted too. */
export const fetchDialCommand = async (
  commandId: string,
): Promise<DialCommandState> => {
  const body = await get<
    (DialCommandState & { success?: boolean }) | { command?: DialCommandState }
  >(`/dial/${encodeURIComponent(commandId)}`);
  return ((body as { command?: DialCommandState })?.command ??
    body) as DialCommandState;
};
