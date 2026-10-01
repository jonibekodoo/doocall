/** Typed client for the sales-manager portal API (/api/sales/v1). */

import { api, get, post, put } from "./client";
import type { ApiEnvelope, ExpiringCompany } from "./types";

const S = "/api/sales/v1" as const;

export interface CompanyStatusBreakdown {
  active: number;
  trial: number;
  expired: number;
  suspended: number;
}

export interface SalesDashboard extends ApiEnvelope {
  integrators: number;
  companies: number;
  operators: number;
  commission_percent: string;
  balance_uzs: number;
  accrued_uzs: number;
  lifetime_uzs: number;
  company_status: CompanyStatusBreakdown;
  expiring_soon: ExpiringCompany[];
}

export interface SalesIntegratorRow {
  id: number;
  name: string;
  company_name: string;
  logo_url: string | null;
  status: string;
  companies: number;
  company_status: CompanyStatusBreakdown;
}

export interface SalesPayout {
  id: number;
  amount_uzs: number;
  status: string;
  note: string;
  requested_at: string;
  processed_at: string | null;
}

export interface SalesProfile extends ApiEnvelope {
  name: string;
  company_name: string;
  logo_url: string | null;
  phone: string;
  email: string;
  commission_percent: string;
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
}

export const fetchSalesDashboard = () => get<SalesDashboard>(`${S}/dashboard`);

export const fetchSalesIntegrators = () =>
  get<{ success: boolean; integrators: SalesIntegratorRow[] }>(`${S}/integrators`);

export const createSalesIntegrator = (body: {
  email: string;
  name: string;
  password: string;
  phone?: string;
  company_name?: string;
}) => post<{ success: boolean; integrator: { id: number; referral_code: string } }>(`${S}/integrators`, body);

export interface SalesIntegratorDetail {
  id: number;
  name: string;
  company_name: string;
  logo_url: string | null;
  email: string;
  phone: string;
  status: string;
  referral_code: string;
  my_commission_uzs: number;
  companies: Array<{
    id: number;
    name: string;
    status: string;
    created_at: string;
    trial_ends_at: string | null;
    seats: number;
  }>;
}

export const fetchSalesIntegrator = (id: number) =>
  get<{ success: boolean; integrator: SalesIntegratorDetail }>(`${S}/integrators/${id}`);

export const fetchSalesPayouts = () =>
  get<{
    success: boolean;
    payouts: SalesPayout[];
    balance_uzs: number;
    min_payout_uzs: number;
  }>(`${S}/payouts`);

export const requestSalesPayout = (amount_uzs: number, note = "") =>
  post<{ success: boolean; payout_id: number; balance_uzs: number }>(
    `${S}/payouts`,
    { amount_uzs, note },
  );

export const fetchSalesProfile = () => get<SalesProfile>(`${S}/profile`);

export const saveSalesProfile = (body: {
  name?: string;
  company_name?: string;
  phone?: string;
  bank_card?: string;
  bank_mfo?: string;
  bank_inn?: string;
  bank_transit?: string;
  accept_offer?: boolean;
}) => put<SalesProfile>(`${S}/profile`, body);

export const uploadSalesLogo = (file: File) => {
  const form = new FormData();
  form.append("logo", file);
  return api<{ success: boolean; logo_url: string }>(`${S}/logo`, {
    method: "POST",
    body: form,
  });
};

export interface SalesNotification {
  id: number;
  kind: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

export const fetchSalesNotifications = () =>
  get<{ success: boolean; unread: number; notifications: SalesNotification[] }>(
    `${S}/notifications`,
  );

export const markSalesNotificationsRead = () =>
  post<ApiEnvelope>(`${S}/notifications`, {});

// ── CRM ─────────────────────────────────────────────────────────────────────
export interface Stage {
  id: number;
  name: string;
  order: number;
  color: string;
}
export interface Pipeline {
  id: number;
  name: string;
  order: number;
  stages: Stage[];
}
export interface TagRef {
  id: number;
  name: string;
  color: string;
}
export interface SourceRef {
  id: number;
  name: string;
}
export interface TaskTypeRef {
  id: number;
  name: string;
  icon: string;
}
export interface CrmMeta {
  tags: TagRef[];
  sources: SourceRef[];
  task_types: TaskTypeRef[];
}
export interface TaskState {
  kind: "none" | "nodue" | "today" | "left" | "overdue";
  days: number;
}
export interface LeadCard {
  id: number;
  full_name: string;
  company: string;
  phone: string;
  stage_id: number | null;
  priority: number;
  source: SourceRef | null;
  tags: TagRef[];
  sales_manager: string | null;
  sales_manager_id: number | null;
  task_state: TaskState;
}
export interface BoardStats {
  today_tasks: number;
  no_task_leads: number;
  overdue_tasks: number;
  leads_today: number;
  leads_yesterday: number;
}
export interface LeadEvent {
  id: number;
  kind: string;
  text: string;
  actor: string;
  created_at: string;
  task: {
    id: number;
    title: string;
    due_at: string | null;
    is_done: boolean;
    responsible: string | null;
    type: { id: number; name: string; icon: string } | null;
  } | null;
}
export interface LeadDetailData extends LeadCard {
  contact_name: string;
  email: string;
  source_id: number | null;
  tag_ids: number[];
  note: string;
  pipeline_id: number;
  created_at: string;
  events: LeadEvent[];
  open_tasks: LeadEvent["task"][];
}
export interface CrmTask {
  id: number;
  title: string;
  due_at: string | null;
  is_done: boolean;
  is_cancelled: boolean;
  auto: boolean;
  lead_id: number | null;
  lead_name: string | null;
  type: { name: string; icon: string } | null;
  bucket: string;
  created_at: string;
}

export const fetchCrmMeta = () =>
  get<{ success: boolean } & CrmMeta>(`${S}/crm/meta`);

export const fetchPipelines = () =>
  get<{ success: boolean; pipelines: Pipeline[] }>(`${S}/pipelines`);

export const fetchLeads = (query: string) =>
  get<{ success: boolean; leads: LeadCard[] }>(`${S}/leads${query}`);

export const fetchBoardStats = () =>
  get<{ success: boolean } & BoardStats>(`${S}/crm/board-stats`);

export const createLead = (body: {
  full_name: string;
  phone?: string;
  company?: string;
}) => post<{ success: boolean; lead: LeadCard }>(`${S}/leads`, body);

export const fetchLead = (id: number) =>
  get<{ success: boolean; lead: LeadDetailData }>(`${S}/leads/${id}`);

export const updateLead = (
  id: number,
  body: Partial<{
    stage_id: number;
    full_name: string;
    contact_name: string;
    phone: string;
    email: string;
    company: string;
    source_id: number | null;
    tag_ids: number[];
    note: string;
    priority: number;
  }>,
) => api<{ success: boolean; lead: LeadDetailData }>(`${S}/leads/${id}`, { method: "PATCH", body: JSON.stringify(body) });

export const addLeadNote = (id: number, text: string) =>
  post<ApiEnvelope>(`${S}/leads/${id}/note`, { text });

export const addLeadTask = (id: number, title: string, due_at?: string, type_id?: number) =>
  post<ApiEnvelope>(`${S}/leads/${id}/task`, { title, due_at, type_id });

export const fetchTasks = () =>
  get<{ success: boolean; tasks: CrmTask[]; open_count: number }>(`${S}/tasks`);

export const createTask = (body: { title: string; due_at?: string; type_id?: number }) =>
  post<ApiEnvelope>(`${S}/tasks`, body);

export const updateTask = (
  id: number,
  body: Partial<{ action: string; reason: string; is_done: boolean; title: string; due_at: string; type_id: number }>,
) => api<ApiEnvelope>(`${S}/tasks/${id}`, { method: "PATCH", body: JSON.stringify(body) });
