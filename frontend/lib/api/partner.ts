/** Typed client for the partner portal API (/api/partner/v1). */

import { get, post, put } from "./client";
import type { ApiEnvelope } from "./types";

const P = "/api/partner/v1" as const;

export interface PartnerDashboard extends ApiEnvelope {
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

export interface PartnerCompany {
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
    phone: string;
    email: string;
    referral_code: string;
    payout_details: Record<string, string>;
  }>(`${P}/profile`);

export const savePartnerProfile = (body: {
  name?: string;
  phone?: string;
  payout_details?: Record<string, string>;
}) => put<ApiEnvelope>(`${P}/profile`, body);

/** Referral link builder — used by the UI and unit-tested.
 * Lands straight on the registration form with the promo code locked in. */
export function referralLink(
  code: string,
  base = "https://doocall.uz",
): string {
  return `${base.replace(/\/+$/, "")}/register?ref=${encodeURIComponent(code)}`;
}
