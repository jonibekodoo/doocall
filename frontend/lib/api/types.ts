/** Hand-typed from /api/schema/ (drf-spectacular) — web cabinet surface. */

export interface ApiEnvelope {
  success: boolean;
  message?: string;
  error_code?: string;
}

export interface LoginResponse extends ApiEnvelope {
  access: string;
  user: { email: string; company: string | null; role: string; portal: string };
}

export interface RegisterResponse extends ApiEnvelope {
  company: { name: string; slug: string };
  trial_ends_at: string | null;
  email_verification_required: boolean;
}

export interface DirectionStats {
  total: number;
  answered: number;
  /** All unanswered (legacy, kept by the backend). */
  missed: number;
  /** Inbound unanswered — "O'tkazib yuborilgan" (new backend). */
  missed_inbound?: number;
  /** Outbound unanswered — "Javob bermadi" (new backend). */
  not_reached?: number;
}

export interface DashboardResponse extends ApiEnvelope {
  period: string;
  general: {
    all: DirectionStats;
    inbound: DirectionStats;
    outbound: DirectionStats;
    total_duration_sec: number;
  };
  per_operator: Array<{
    id: number;
    user_name: string;
    full_name: string;
    total: number;
    answered: number;
    missed: number;
    missed_inbound?: number;
    not_reached?: number;
    duration: number;
  }>;
  latest_calls: CallRow[];
  unanswered_now: Array<CallRow & { total_missed: number }>;
}

export interface CallRow {
  id: number;
  call_id: string;
  direction: "inbound" | "outbound" | "internal";
  status: "answered" | "no_answer" | "busy" | "failed";
  operator_id: number | null;
  operator_name: string | null;
  operator_number: string;
  counterparty_number: string;
  counterparty_name: string | null;
  duration: number;
  start_time: string;
  has_location: boolean;
  /** Latest delivery outcome per connected CRM (empty when none configured). */
  crm: CrmMark[];
  /** Kotib AI analysis of this call, when one has arrived. */
  ai?: CallAiMark | null;
}

export interface CallAiMark {
  analysis_id: number;
  final_score: number;
}

/** A company about to go offline (partner / sales / admin dashboards). */
export interface ExpiringCompany {
  id: number;
  name: string;
  integrator: string | null;
  /** "trial" — trial ends; "balance" — prepaid balance runs out. */
  reason: "trial" | "balance";
  days_left: number;
  ends_on: string;
}

export interface CrmMark {
  provider: "amocrm" | "bitrix24" | "odoo" | "kotib";
  status: "ok" | "error";
  error: string;
  at: string;
}

export interface CallsListResponse extends ApiEnvelope {
  count: number;
  page: number;
  pages: number;
  page_size: number;
  results: CallRow[];
}

export interface CallAudioInfo {
  kind: "primary" | "realtime";
  filename: string;
  size_bytes: number;
  url: string;
}

export interface CallDetailResponse extends ApiEnvelope {
  call: CallRow & {
    from_number: string;
    from_name: string | null;
    to_number: string;
    to_name: string | null;
    operator_number: string | null;
    sim_slot: number;
    end_time: string | null;
    start_time_local: string;
    latitude: number | null;
    longitude: number | null;
    address: string;
    audios: CallAudioInfo[];
  };
}

export interface PaywallPayload {
  reason: "trial_expired" | "suspended";
  seats: number;
  price_per_operator_uzs: number;
  amount_due_uzs: number;
  providers: string[];
}

export interface BillingStatusResponse extends ApiEnvelope {
  company: string;
  status: string;
  seats: number;
  price_per_operator_uzs: number;
  amount_due_uzs: number;
  trial_ends_at: string | null;
  current_period_end: string | null;
  paywall?: PaywallPayload;
}

export interface ContactRow {
  id: number;
  name: string;
  note: string;
  responsible_id: number | null;
  phones: string[];
  created_at: string;
}

/** Bitrix24 card options (saved with the integration config). */
export type Bitrix24CreateCard = "auto" | "lead" | "contact" | "deal" | "none";

export interface Bitrix24CardOptions {
  save_external_calls: boolean;
  create_card: Bitrix24CreateCard;
  /** Bitrix24 SOURCE id for leads — A-Z, 0-9, _ (≤ 50); "" = CALL. */
  lead_source: string;
  only_answered: boolean;
}

/** Read-only portal CRM mode detected by the backend. */
export interface Bitrix24PortalMode {
  /** "classic" = with leads, "simple" = no leads, "" = not checked yet. */
  crm_mode: "classic" | "simple" | "";
  crm_mode_checked_at: string | null;
  /** Detection failed → treated as "simple" (no leads) for safety. */
  crm_mode_assumed: boolean;
}

/** Last custom-webhook delivery outcome (GET /settings/webhook, final result
 * after retries). */
export interface WebhookDeliveryStatus {
  /** null = never sent; "http_<code>" = the server answered with that code. */
  last_status:
    | null
    | "ok"
    | `http_${number}`
    | "timeout"
    | "connection_error"
    | "blocked"
    | "error";
  /** ISO with offset. */
  last_ok_at: string | null;
  last_error_at: string | null;
}

/** Remote Dial: a company phone that can be asked to dial a number. */
export interface DialDevice {
  device_id: string;
  operator: { id: number; full_name: string } | null;
  model: string;
  online: boolean;
  last_seen: string | null;
}

export type DialStatus =
  | "sent"
  | "received"
  | "rejected"
  | "dialing"
  | "active"
  | "disconnected"
  | "failed"
  | "expired"
  | "offline";

export interface DialCommandState {
  status: DialStatus;
  reject_reason?: string | null;
  /** e.g. "ask" when the phone asks which SIM to use. */
  sim_mode?: string | null;
  /** 0-based SIM slot actually used. */
  used_sim_slot?: number | null;
  duration_sec?: number | null;
  cause?: string | null;
}

/** Bitrix24 click-to-call (ONEXTERNALCALLSTART → Remote Dial) config. */
export interface Bitrix24ClickToCall {
  click_to_call_enabled: boolean;
  /** Handler URL for the Bitrix24 outgoing webhook (shown to admins). */
  click_to_call_url: string;
  /** Bitrix24 application_token saved (the secret itself is never sent). */
  b24_app_token_set: boolean;
  /** DooCall's external line exists in Bitrix24 telephony. */
  external_line_registered: boolean;
}
