/** Typed client for the admin portal API (/api/admin/v1). */

import { api, del, get, post, put } from "./client";
import type { ApiEnvelope } from "./types";

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
  integrators: number;
  pending_payouts: number;
  payments_series: number[];
  calls_series: number[];
}

export interface AdminCompanyRow {
  id: number;
  name: string;
  slug: string;
  status: string;
  trial_ends_at: string | null;
  trial_expired: boolean;
  created_at: string;
  acquired_via: string;
  integrator_id: number | null;
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
  status: string;
  referral_code: string;
  companies: number;
  override_percent: string | null;
  balance_uzs: number;
}

export interface IntegratorDetail extends ApiEnvelope {
  integrator: {
    id: number;
    name: string;
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

export const fetchAdminCompanies = (params = "") =>
  g<{ success: boolean; companies: AdminCompanyRow[] }>(`/companies${params}`);

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
    };
  }>(`/companies/${id}`);

export const updateAdminCompany = (
  id: number,
  body: Partial<{ name: string; audio_retention_days: number | null }>,
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

export const approvePayment = (id: number) =>
  post<{
    success: boolean;
    payment_status: string;
    cashback_accrued_uzs: number;
  }>(abs(`/payments/${id}/approve`));

export const refundPayment = (id: number) =>
  post<ApiEnvelope>(abs(`/payments/${id}/refund`));

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

export const fetchIntegratorDetail = (id: number) =>
  g<IntegratorDetail>(`/integrators/${id}`);

export const patchIntegrator = (
  id: number,
  body: Partial<{
    name: string;
    status: string;
    phone: string;
    email: string;
    payout_details: Record<string, string>;
    cashback_percent_override: string | null;
  }>,
) => patchJson<ApiEnvelope>(abs(`/integrators/${id}`), body);

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
