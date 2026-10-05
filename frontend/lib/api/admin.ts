/** Typed client for the admin portal API (/api/admin/v1). */

import type { CompanyStatsData } from "@/components/company/CompanyStats";

import { api, del, get, post, put } from "./client";
import type { LeadCard, LeadDetailData, Pipeline } from "./sales";
import type { ApiEnvelope, ExpiringCompany } from "./types";

const patchJson = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });

const A = "/api/admin/v1" as const;
// The shared client prefixes /api/web/v1 — admin calls use absolute paths.
const abs = (path: string) => `${A}${path}`;

// Base override: the shared client hardcodes the web base, so wrap fetchers.
const g = <T>(path: string) => get<T>(`${abs(path)}` as string);

export interface AdminKpis extends ApiEnvelope {
  companies: {
    total: number;
    active: number;
    trial: number;
    suspended: number;
  };
  mrr_uzs: number;
  payments_30d_uzs: number;
  calls_today: number;
  total_calls: number;
  total_call_seconds: number;
  integrators: number;
  pending_payments: number;
  pending_payouts: number;
  payments_series: number[];
  calls_series: number[];
  expiring: ExpiringCompany[];
}

export interface AdminCompanyRow {
  id: number;
  name: string;
  slug: string;
  phone: string;
  status: string;
  trial_ends_at: string | null;
  trial_expired: boolean;
  created_at: string;
  acquired_via: string;
  integrator_id: number | null;
  integrator_name: string | null;
  integrator_company: string | null;
  integrations_count: number;
  audio_retention_days: number | null;
  seats: number;
  subscription_status: string | null;
  period_end: string | null;
}

export interface AdminPaymentRow {
  id: number;
  company: string;
  company_id: number;
  provider: string;
  amount_uzs: number;
  status: string;
  created_at: string;
  cashback_uzs: number | null;
}

export interface IntegratorRow {
  id: number;
  name: string;
  company_name: string;
  logo_url: string | null;
  status: string;
  referral_code: string;
  email: string;
  phone: string;
  companies: number;
  override_percent: string | null;
  balance_uzs: number;
}

export interface IntegratorDetail extends ApiEnvelope {
  integrator: {
    id: number;
    name: string;
    company_name: string;
    logo_url: string | null;
    is_public: boolean;
    email: string;
    phone: string;
    status: string;
    referral_code: string;
    override_percent: string | null;
    default_percent: string;
    effective_percent: string;
    lifetime_cashback_uzs: number;
    balance_uzs: number;
    payout_details: Record<string, string>;
    bank_card: string;
    bank_mfo: string;
    bank_inn: string;
    bank_transit: string;
    sales_manager_id: number | null;
    sales_manager_name: string | null;
    offer_accepted_at: string | null;
  };
  companies: Array<{
    id: number;
    name: string;
    status: string;
    acquired_via: string;
    cashback_uzs: number;
  }>;
  accruals: Array<{
    id: number;
    company: string;
    amount_uzs: number;
    percent: string;
    status: string;
    created_at: string;
  }>;
  payouts: Array<{
    id: number;
    amount_uzs: number;
    status: string;
    requested_at: string;
  }>;
}

export const fetchKpis = () => g<AdminKpis>("/dashboard");

export type DashboardMetric = "payments" | "calls";
export type DashboardPeriod = "daily" | "weekly" | "monthly" | "yearly";

export interface DashboardSeries {
  success: boolean;
  metric: DashboardMetric;
  period: DashboardPeriod;
  series: Array<{ label: string; value: number }>;
}

export const fetchDashboardSeries = (
  metric: DashboardMetric,
  period: DashboardPeriod,
) => g<DashboardSeries>(`/dashboard/series?metric=${metric}&period=${period}`);

export interface AdminCompanyStats {
  total: number;
  active: number;
  trial: number;
  expired: number;
  suspended: number;
}

export const fetchAdminCompanies = (params = "") =>
  g<{ success: boolean; stats: AdminCompanyStats; companies: AdminCompanyRow[] }>(
    `/companies${params}`,
  );

export const fetchAdminCompany = (id: number) =>
  g<{
    success: boolean;
    company: AdminCompanyRow & {
      operators: Array<{
        id: number;
        user_name: string;
        full_name: string;
        is_active: boolean;
      }>;
      payments: AdminPaymentRow[];
      users: Array<{
        id: number;
        email: string;
        is_company_admin: boolean;
        is_active: boolean;
        last_login: string | null;
      }>;
      integrations: AdminCompanyIntegration[];
      stats: CompanyStatsData;
    };
  }>(`/companies/${id}`);

export interface AdminCompanyIntegration {
  kind: "crm" | "webhook" | "api";
  provider: string;
  label: string;
  is_enabled: boolean;
  last_status: string;
  last_error: string;
  last_delivery_at: string | null;
  updated_at: string | null;
  target?: string;
  ok_30d?: number;
  error_30d?: number;
}

export const resetCompanyUserPassword = (
  companyId: number,
  userId: number,
  password: string,
) =>
  post<{ success: boolean }>(
    abs(`/companies/${companyId}/users/${userId}/password`),
    { password },
  );

export const updateAdminCompany = (
  id: number,
  body: Partial<{
    name: string;
    phone: string;
    audio_retention_days: number | null;
  }>,
) =>
  patchJson<{ success: boolean; company: AdminCompanyRow }>(
    abs(`/companies/${id}`),
    body,
  );

export const deleteAdminCompany = (id: number, confirm: string) =>
  del<{ success: boolean }>(
    abs(`/companies/${id}?confirm=${encodeURIComponent(confirm)}`),
  );

export const companyAction = (id: number, action: string, body?: unknown) =>
  post<{ success: boolean; company: AdminCompanyRow }>(
    abs(`/companies/${id}/${action}`),
    body,
  );

export const impersonate = (companyId: number) =>
  post<{
    success: boolean;
    access: string;
    impersonated_user: string;
    company: string;
    expires_in_minutes: number;
  }>(abs(`/impersonate/${companyId}`));

export const impersonateStop = (company: string) =>
  post<ApiEnvelope>(`${abs("/impersonate/stop")}`, { company });

export const fetchAdminPayments = (params = "") =>
  g<{ success: boolean; payments: AdminPaymentRow[] }>(`/payments${params}`);

export interface AdminPaymentStats {
  success: boolean;
  total_uzs: number;
  total_count: number;
  pending_count: number;
  pending_uzs: number;
  by_provider: Array<{ provider: string; count: number; amount_uzs: number }>;
  by_status: Array<{ status: string; count: number; amount_uzs: number }>;
  revenue_series: number[];
}

export const fetchPaymentStats = () =>
  g<AdminPaymentStats>("/payments/stats");

// ── Dashboard: top-10 companies by calls (all-time + today) ─────────────────
export interface CallsTodayCompany {
  id: number;
  name: string;
  total: number;
  today: number;
}
export const fetchAdminCallsToday = () =>
  g<{
    success: boolean;
    date: string;
    total: number;
    today: number;
    companies_count: number;
    companies: CallsTodayCompany[];
  }>("/dashboard/calls-today");

export const approvePayment = (id: number) =>
  post<{
    success: boolean;
    payment_status: string;
    cashback_accrued_uzs: number;
  }>(abs(`/payments/${id}/approve`));

export const refundPayment = (id: number) =>
  post<ApiEnvelope>(abs(`/payments/${id}/refund`));

export const rejectPayment = (id: number) =>
  post<{ success: boolean; status: string }>(abs(`/payments/${id}/reject`));

export const deletePayment = (id: number) =>
  del<ApiEnvelope>(abs(`/payments/${id}`));

// ── Payment providers (on/off + logo) ────────────────────────────────────────
export interface PaymentProviderRow {
  provider: string;
  label: string;
  is_enabled: boolean;
  sort_order: number;
  logo_url: string | null;
  updated_at: string;
}

export const fetchPaymentProviders = () =>
  g<{ success: boolean; providers: PaymentProviderRow[] }>("/payment-providers");

export const updatePaymentProvider = (
  body: { provider: string; is_enabled?: boolean; sort_order?: number },
) => patchJson<{ success: boolean; provider: PaymentProviderRow }>(abs("/payment-providers"), body);

export const uploadProviderLogo = (provider: string, file: File) => {
  const form = new FormData();
  form.append("logo", file);
  return api<{ success: boolean; logo_url: string }>(
    abs(`/payment-providers/${provider}/logo`),
    { method: "POST", body: form },
  );
};

// ── Paylov transactions + logs ───────────────────────────────────────────────
export interface PaylovTransaction {
  id: number;
  company: string;
  company_id: number;
  amount_uzs: number;
  status: string;
  external_id: string;
  created_at: string;
  approved_at: string | null;
  logs_count: number;
}

export const fetchPaylovTransactions = (params = "") =>
  g<{
    success: boolean;
    transactions: PaylovTransaction[];
    total_count: number;
    total_uzs: number;
    approved_count: number;
    approved_uzs: number;
  }>(`/paylov/transactions${params}`);

export const paylovTransactionAction = (id: number, action: "refund" | "cancel") =>
  post<{ success: boolean; status: string }>(abs(`/paylov/transactions/${id}/action`), { action });

export interface PaylovLogRow {
  id: number;
  direction: "in" | "out";
  event: string;
  ok: boolean;
  http_status: number | null;
  payment_id: number | null;
  request_body: unknown;
  response_body: unknown;
  note: string;
  created_at: string;
}

export const fetchPaylovLogs = (params = "") =>
  g<{ success: boolean; logs: PaylovLogRow[] }>(`/paylov/logs${params}`);

export const fetchPricing = () =>
  g<{
    success: boolean;
    price_per_operator_uzs: number;
    trial_days: number;
    history: Array<{
      price_per_operator_uzs: number;
      trial_days: number;
      changed_at: string;
      changed_by: string | null;
    }>;
  }>("/settings/pricing");

export const savePricing = (body: {
  price_per_operator_uzs?: number;
  trial_days?: number;
}) => put<ApiEnvelope>(`${abs("/settings/pricing")}`, body);

export const fetchIntegrators = () =>
  g<{ success: boolean; integrators: IntegratorRow[] }>("/integrators");

export const createIntegrator = (body: {
  email: string;
  name: string;
  password: string;
  phone?: string;
}) =>
  post<{ success: boolean; integrator: { id: number; referral_code: string } }>(
    `${abs("/integrators")}`,
    body,
  );

export interface IntegratorStatRow {
  id: number;
  name: string;
  company_name: string;
  logo_url: string | null;
  referral_code: string;
  status: string;
  companies: number;
  company_status: {
    active: number;
    trial: number;
    expired: number;
    suspended: number;
  };
  revenue_uzs: number;
  cashback_uzs: number;
  balance_uzs: number;
  call_seconds: number;
}

export interface IntegratorStats {
  success: boolean;
  integrators: IntegratorStatRow[];
  totals: {
    integrators: number;
    companies: number;
    revenue_uzs: number;
    cashback_uzs: number;
    call_seconds: number;
  };
}

export const fetchIntegratorStats = () =>
  g<IntegratorStats>("/integrators/stats");

export interface IntegratorApplicationRow {
  id: number;
  full_name: string;
  phone: string;
  email: string;
  company: string;
  message: string;
  status: string;
  sales_manager_id: number | null;
  sales_manager_name: string | null;
  created_at: string;
  reviewed_at: string | null;
}

// ── Sales managers ──────────────────────────────────────────────────────────
export interface SalesManagerRow {
  id: number;
  name: string;
  company_name: string;
  logo_url: string | null;
  email: string;
  phone: string;
  status: string;
  commission_percent: string;
  balance_uzs: number;
  integrators: number;
  bank_card: string;
  bank_mfo: string;
  bank_inn: string;
  bank_transit: string;
  offer_accepted_at: string | null;
}

export interface SalesManagerStatRow {
  id: number;
  name: string;
  company_name: string;
  logo_url: string | null;
  status: string;
  commission_percent: string;
  integrators: number;
  companies: number;
  revenue_uzs: number;
  commission_uzs: number;
  balance_uzs: number;
  call_seconds: number;
}

export const fetchSalesManagers = () =>
  g<{ success: boolean; managers: SalesManagerRow[] }>("/sales-managers");

export const fetchSalesManagerStats = () =>
  g<{
    success: boolean;
    managers: SalesManagerStatRow[];
    totals: {
      managers: number;
      integrators: number;
      companies: number;
      revenue_uzs: number;
      commission_uzs: number;
    };
  }>("/sales-managers/stats");

export const createSalesManager = (body: {
  email: string;
  name: string;
  password: string;
  phone?: string;
  commission_percent?: string;
}) => post<{ success: boolean; manager: SalesManagerRow }>(abs("/sales-managers"), body);

export const fetchSalesManager = (id: number) =>
  g<{
    success: boolean;
    manager: SalesManagerRow & {
      integrator_list: Array<{ id: number; name: string; status: string; companies: number }>;
      commissions: Array<{
        id: number;
        company: string;
        amount_uzs: number;
        percent: string;
        status: string;
        created_at: string;
      }>;
      payouts: Array<{ id: number; amount_uzs: number; status: string; requested_at: string }>;
      lifetime_commission_uzs: number;
    };
  }>(`/sales-managers/${id}`);

export const updateSalesManager = (
  id: number,
  body: Partial<{
    name: string;
    company_name: string;
    phone: string;
    email: string;
    status: string;
    commission_percent: string;
    bank_card: string;
    bank_mfo: string;
    bank_inn: string;
    bank_transit: string;
  }>,
) => patchJson<{ success: boolean; manager: SalesManagerRow }>(abs(`/sales-managers/${id}`), body);

export const resetSalesManagerPassword = (id: number, password: string) =>
  post<{ success: boolean }>(abs(`/sales-managers/${id}/password`), { password });

export const uploadSalesManagerLogo = (id: number, file: File) => {
  const form = new FormData();
  form.append("logo", file);
  return api<{ success: boolean; logo_url: string }>(abs(`/sales-managers/${id}/logo`), {
    method: "POST",
    body: form,
  });
};

export const fetchAdminSalesPayouts = (params = "") =>
  g<{
    success: boolean;
    payouts: Array<{
      id: number;
      sales_manager: string;
      sales_manager_id: number;
      amount_uzs: number;
      status: string;
      requested_at: string;
      bank: { card: string; mfo: string; inn: string; transit: string };
    }>;
  }>(`/sales-payouts${params}`);

export const salesPayoutAction = (
  id: number,
  action: "approve" | "reject" | "mark-paid",
) => post<{ success: boolean; status: string }>(abs(`/sales-payouts/${id}/${action}`));

/** Offer / legal documents are stored per language (uz is the base). */
export const DOC_LANGS = ["uz", "ru", "en"] as const;
export type DocLang = (typeof DOC_LANGS)[number];
export type DocContents = Record<DocLang, string>;

export const fetchOffer = () =>
  g<{ success: boolean; content: string; contents: DocContents; version: number }>("/offer");

export const saveOffer = (contents: DocContents) =>
  put<ApiEnvelope>(`${abs("/offer")}`, { contents });

// ── Public legal pages (privacy / terms / refund) ────────────────────────────
export type LegalKind = "privacy" | "terms" | "refund";

export const fetchLegal = (kind: LegalKind) =>
  g<{
    success: boolean;
    kind: LegalKind;
    content: string;
    contents: DocContents;
    version: number;
    updated_at: string;
  }>(`/legal/${kind}`);

export const saveLegal = (kind: LegalKind, contents: DocContents) =>
  put<ApiEnvelope>(`${abs(`/legal/${kind}`)}`, { contents });

export const fetchIntegratorApplications = (params = "") =>
  g<{
    success: boolean;
    applications: IntegratorApplicationRow[];
    new_count: number;
  }>(`/integrator-applications${params}`);

export const updateIntegratorApplication = (id: number, status: string) =>
  patchJson<{ success: boolean; application: IntegratorApplicationRow }>(
    abs(`/integrator-applications/${id}`),
    { status },
  );

export const assignApplication = (id: number, sales_manager_id: number | null) =>
  patchJson<{ success: boolean; application: IntegratorApplicationRow }>(
    abs(`/integrator-applications/${id}`),
    { sales_manager_id },
  );

export const fetchAdminPipelines = () =>
  g<{ success: boolean; pipelines: Pipeline[] }>("/crm/pipelines");

export const createAdminPipeline = (name: string) =>
  post<{ success: boolean; pipeline: Pipeline }>(abs("/crm/pipelines"), { name });

export const renameAdminPipeline = (id: number, name: string) =>
  patchJson<ApiEnvelope>(abs(`/crm/pipelines/${id}`), { name });

export const deleteAdminPipeline = (id: number) =>
  del<ApiEnvelope>(abs(`/crm/pipelines/${id}`));

export const addAdminStage = (pipelineId: number, name: string) =>
  post<ApiEnvelope>(abs(`/crm/pipelines/${pipelineId}`), { name });

export const deleteAdminStage = (stageId: number) =>
  del<ApiEnvelope>(abs(`/crm/stages/${stageId}`));

export const fetchAdminLeads = (params = "") =>
  g<{ success: boolean; leads: LeadCard[] }>(`/leads${params}`);

export const fetchAdminBoardStats = (params = "") =>
  g<{
    success: boolean;
    today_tasks: number;
    no_task_leads: number;
    overdue_tasks: number;
    leads_today: number;
    leads_yesterday: number;
  }>(`/crm/board-stats${params}`);

export const fetchAdminLead = (id: number) =>
  g<{ success: boolean; lead: LeadDetailData }>(`/leads/${id}`);

export const createAdminLead = (body: {
  sales_manager_id: number;
  full_name: string;
  phone?: string;
  company?: string;
  source?: string;
}) => post<{ success: boolean; lead: LeadCard }>(abs("/leads"), body);

export const patchAdminLead = (id: number, body: Record<string, unknown>) =>
  patchJson<{ success: boolean; lead: LeadDetailData }>(abs(`/leads/${id}`), body);

export const deleteAdminLead = (id: number) => del<ApiEnvelope>(abs(`/leads/${id}`));

export const addAdminLeadNote = (id: number, text: string) =>
  post<ApiEnvelope>(abs(`/leads/${id}/note`), { text });

export const addAdminLeadTask = (id: number, title: string, due_at?: string, type_id?: number) =>
  post<ApiEnvelope>(abs(`/leads/${id}/task`), { title, due_at, type_id });

export const fetchAdminCrmMeta = () =>
  g<{
    success: boolean;
    tags: Array<{ id: number; name: string; color: string }>;
    sources: Array<{ id: number; name: string }>;
    task_types: Array<{ id: number; name: string; icon: string }>;
  }>("/crm/meta");

export const createCrmMetaItem = (kind: "tag" | "source" | "task_type", name: string, extra?: { color?: string; icon?: string }) =>
  post<{ success: boolean; id: number }>(abs("/crm/meta"), { kind, name, ...(extra ?? {}) });

export const deleteCrmMetaItem = (kind: "tag" | "source" | "task_type", id: number) =>
  del<ApiEnvelope>(abs(`/crm/meta/${kind}/${id}`));

export const fetchAdminCrmTasks = (params = "") =>
  g<{
    success: boolean;
    tasks: Array<{
      id: number;
      title: string;
      is_done: boolean;
      is_cancelled: boolean;
      auto: boolean;
      due_at: string | null;
      sales_manager: string;
      lead_id: number | null;
      lead_name: string | null;
      type: { name: string; icon: string } | null;
      bucket: string;
    }>;
  }>(`/crm-tasks${params}`);

export const completeAdminTask = (id: number) =>
  patchJson<ApiEnvelope>(abs(`/crm-tasks/${id}`), { action: "complete" });

export const cancelAdminTask = (id: number, reason: string) =>
  patchJson<ApiEnvelope>(abs(`/crm-tasks/${id}`), { action: "cancel", reason });

export const editAdminTask = (
  id: number,
  body: Partial<{ title: string; due_at: string; type_id: number }>,
) => patchJson<ApiEnvelope>(abs(`/crm-tasks/${id}`), { action: "edit", ...body });

export const deleteAdminTask = (id: number) => del<ApiEnvelope>(abs(`/crm-tasks/${id}`));

export const fetchIntegratorDetail = (id: number) =>
  g<IntegratorDetail>(`/integrators/${id}`);

export const resetIntegratorPassword = (id: number, password: string) =>
  post<{ success: boolean }>(abs(`/integrators/${id}/password`), { password });

export const patchIntegrator = (
  id: number,
  body: Partial<{
    name: string;
    company_name: string;
    is_public: boolean;
    status: string;
    phone: string;
    email: string;
    payout_details: Record<string, string>;
    cashback_percent_override: string | null;
    sales_manager_id: number | null;
    bank_card: string;
    bank_mfo: string;
    bank_inn: string;
    bank_transit: string;
  }>,
) => patchJson<ApiEnvelope>(abs(`/integrators/${id}`), body);

export const uploadIntegratorLogo = (id: number, file: File) => {
  const form = new FormData();
  form.append("logo", file);
  return api<{ success: boolean; logo_url: string }>(
    abs(`/integrators/${id}/logo`),
    { method: "POST", body: form },
  );
};

export const fetchCashbackSettings = () =>
  g<{
    success: boolean;
    default_cashback_percent: string;
    cashback_months_limit: number;
  }>("/settings/cashback");

export const saveCashbackSettings = (body: {
  default_cashback_percent?: string;
  cashback_months_limit?: number;
}) => put<ApiEnvelope>(`${abs("/settings/cashback")}`, body);

export const fetchPlatformAdmins = () =>
  g<{
    success: boolean;
    admins: Array<{ id: number; email: string; is_active: boolean }>;
  }>("/admins");

export const createPlatformAdmin = (body: {
  email: string;
  password: string;
}) => post<{ success: boolean; id: number }>(`${abs("/admins")}`, body);

export const togglePlatformAdmin = (id: number, active: boolean) =>
  patchJson<ApiEnvelope>(abs(`/admins/${id}`), { is_active: active });

export const fetchAdminPayouts = (params = "") =>
  g<{
    success: boolean;
    payouts: Array<{
      id: number;
      integrator: string;
      integrator_id: number;
      amount_uzs: number;
      status: string;
      requested_at: string;
      payout_details: Record<string, string>;
    }>;
  }>(`/payouts${params}`);

export const payoutAction = (
  id: number,
  action: "approve" | "reject" | "mark-paid",
) =>
  post<{ success: boolean; status: string }>(abs(`/payouts/${id}/${action}`));

export const fetchAudit = (params = "") =>
  g<{
    success: boolean;
    entries: Array<{
      id: number;
      action: string;
      company: string | null;
      actor: string | null;
      changes: Record<string, unknown>;
      created_at: string;
    }>;
  }>(`/audit${params}`);

export { del };

export interface AppReleaseRow {
  id: number;
  version: string;
  size_bytes: number;
  notes: string;
  uploaded_by: string | null;
  created_at: string;
}

export const fetchAppReleases = () =>
  g<{ success: boolean; releases: AppReleaseRow[] }>("/app-releases");

export const uploadAppRelease = (
  version: string,
  notes: string,
  file: File,
) => {
  const form = new FormData();
  form.append("version", version);
  form.append("notes", notes);
  form.append("file", file);
  return api<{ success: boolean; release: { id: number; version: string } }>(
    abs("/app-releases"),
    { method: "POST", body: form },
  );
};

export const deleteAppRelease = (id: number) =>
  del<ApiEnvelope>(abs(`/app-releases/${id}`));

export interface CrmCatalogRow {
  id: number;
  name: string;
  site_url: string;
  logo_url: string | null;
  sort_order: number;
  is_active: boolean;
}

export const fetchCrmCatalogAdmin = () =>
  g<{ success: boolean; entries: CrmCatalogRow[] }>("/crm-catalog");

export const createCrmCatalogEntry = (body: {
  name: string;
  site_url: string;
  sort_order?: number;
  logo?: File | null;
}) => {
  const form = new FormData();
  form.append("name", body.name);
  form.append("site_url", body.site_url);
  if (body.sort_order != null) form.append("sort_order", String(body.sort_order));
  if (body.logo) form.append("logo", body.logo);
  return api<{ success: boolean; entry: CrmCatalogRow }>(abs("/crm-catalog"), {
    method: "POST",
    body: form,
  });
};

export const updateCrmCatalogEntry = (
  id: number,
  body: Partial<{
    name: string;
    site_url: string;
    sort_order: number;
    is_active: boolean;
    logo: File | null;
  }>,
) => {
  const form = new FormData();
  if (body.name != null) form.append("name", body.name);
  if (body.site_url != null) form.append("site_url", body.site_url);
  if (body.sort_order != null) form.append("sort_order", String(body.sort_order));
  if (body.is_active != null) form.append("is_active", String(body.is_active));
  if (body.logo) form.append("logo", body.logo);
  return api<{ success: boolean; entry: CrmCatalogRow }>(
    abs(`/crm-catalog/${id}`),
    { method: "POST", body: form },
  );
};

export const deleteCrmCatalogEntry = (id: number) =>
  del<ApiEnvelope>(abs(`/crm-catalog/${id}`));
