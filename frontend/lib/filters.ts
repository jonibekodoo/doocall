/** Calls-list filter model → backend query string (§6.2 param names). */

export interface CallFilters {
  employees?: number[];
  dateFrom?: string; // YYYY-MM-DD
  dateTo?: string;
  direction?: "inbound" | "outbound";
  status?: "answered" | "no_answer";
  search?: string;
  minDuration?: number;
  simSlot?: number;
  page?: number;
  ordering?: "duration" | "-duration" | "date" | "-date";
}

/** Deterministic, param-name-exact builder. Empty/undefined values omitted. */
export function buildCallsQuery(filters: CallFilters): string {
  const params = new URLSearchParams();
  if (filters.employees?.length)
    params.set("employees", filters.employees.join(","));
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.direction) params.set("direction", filters.direction);
  if (filters.status) params.set("status", filters.status);
  if (filters.search?.trim()) params.set("search", filters.search.trim());
  if (filters.minDuration !== undefined && filters.minDuration > 0)
    params.set("min_duration", String(filters.minDuration));
  if (filters.simSlot !== undefined && filters.simSlot >= 0)
    params.set("sim_slot", String(filters.simSlot));
  if (filters.page !== undefined && filters.page > 1)
    params.set("page", String(filters.page));
  if (filters.ordering) params.set("ordering", filters.ordering);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}
