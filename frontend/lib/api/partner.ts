/** Typed client for the partner portal API (/api/partner/v1). */

import type { CompanyStatsData } from "@/components/company/CompanyStats";

import { api, get, post, put } from "./client";
import type { ApiEnvelope } from "./types";

const P = "/api/partner/v1" as const;

export interface PartnerDashboard extends ApiEnvelope {
  companies_by_status: CompaniesByStatus;
  month_cashback_uzs: number;
  min_payout_uzs: number;
  referral_code: string;
  effective_percent: string;
  companies_total: number;
  companies_active: number;
  balance_uzs: number;
  paid_out_uzs: number;
  accrued_total_uzs: number;
  monthly_series: Array<{ month: string; amount_uzs: number }>;
}

export interface CompaniesByStatus {
  active: number;
  trial: number;
  trial_expired: number;
  suspended: number;
}

export interface PartnerCompany {
  trial_expired: boolean;
  trial_ends_at: string | null;
  id: number;
  name: string;
  status: string;
  acquired_via: string;
  created_at: string;
  seats: number;
  subscription_status: string | null;
  my_cashback_uzs: number;
}

export interface PartnerAccrual {
  id: number;
  company: string;
  company_id: number;
  amount_uzs: number;
  percent: string;
  status: string;
  created_at: string;
}

export interface PartnerPayout {
  id: number;
  amount_uzs: number;
  status: string;
  note: string;
  requested_at: string;
  processed_at: string | null;
}

export const fetchPartnerDashboard = () =>
  get<PartnerDashboard>(`${P}/dashboard`);

export const fetchPartnerCompanies = () =>
  get<{ success: boolean; companies: PartnerCompany[] }>(`${P}/companies`);

export const fetchPartnerCompany = (id: number) =>
  get<{
    success: boolean;
    company: PartnerCompany & {
      accruals: Omit<PartnerAccrual, "company" | "company_id">[];
      stats: CompanyStatsData;
    };
  }>(`${P}/companies/${id}`);

export const registerClientCompany = (body: {
  company_name: string;
  admin_email: string;
  phone: string;
  password: string;
}) =>
  post<{ success: boolean; company: PartnerCompany }>(`${P}/companies`, body);

export const fetchPartnerAccruals = (params = "") =>
  get<{ success: boolean; accruals: PartnerAccrual[] }>(
    `${P}/accruals${params}`,
  );

export const fetchPartnerPayouts = () =>
  get<{
    success: boolean;
    payouts: PartnerPayout[];
    balance_uzs: number;
    min_payout_uzs: number;
  }>(`${P}/payouts`);

export const requestPayout = (amount_uzs: number, note = "") =>
  post<{ success: boolean; payout_id: number; balance_uzs: number }>(
    `${P}/payouts`,
    {
      amount_uzs,
      note,
    },
  );

export const fetchPartnerProfile = () =>
  get<{
    success: boolean;
    name: string;
    company_name: string;
    logo_url: string | null;
    is_public: boolean;
    phone: string;
    email: string;
    referral_code: string;
    payout_details: Record<string, string>;
    bank_card: string;
    bank_mfo: string;
    bank_inn: string;
    bank_transit: string;
    offer: {
      content: string;
      version: number;
      accepted: boolean;
      accepted_at: string | null;
    };
  }>(`${P}/profile`);

export const savePartnerProfile = (body: {
  name?: string;
  company_name?: string;
  phone?: string;
  is_public?: boolean;
  payout_details?: Record<string, string>;
  bank_card?: string;
  bank_mfo?: string;
  bank_inn?: string;
  bank_transit?: string;
  accept_offer?: boolean;
}) => put<ApiEnvelope>(`${P}/profile`, body);

export const uploadPartnerLogo = (file: File) => {
  const form = new FormData();
  form.append("logo", file);
  return api<{ success: boolean; logo_url: string }>(`${P}/logo`, {
    method: "POST",
    body: form,
  });
};

/** Referral link builder — used by the UI and unit-tested.
 * Lands straight on the registration form with the promo code locked in. */
export function referralLink(
  code: string,
  base = "https://doocall.uz",
): string {
  return `${base.replace(/\/+$/, "")}/register?ref=${encodeURIComponent(code)}`;
}
