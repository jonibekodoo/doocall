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
  missed: number;
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
