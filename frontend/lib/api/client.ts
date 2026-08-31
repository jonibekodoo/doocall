/** Typed API client with in-memory access token + cookie-refresh on 401.
 *
 * The refresh token lives in an httpOnly cookie scoped to /api/web/v1/auth
 * (Phase 4). The access token is held ONLY in memory here — page reloads
 * recover the session with a single silent refresh.
 */

import type { ApiEnvelope } from "./types";

const BASE = process.env.NEXT_PUBLIC_WEB_API_BASE ?? "/api/web/v1";

let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;
/** User payload captured from the last successful login/refresh.
 * Exposed via a getter — `export let` live bindings are unreliable under
 * the SWC/webpack CJS interop and read as stale null in importers. */
interface SessionUserPayload {
  email: string;
  company: string | null;
  role: string;
  portal: string;
}
let sessionUser: SessionUserPayload | null = null;

export function getSessionUser(): SessionUserPayload | null {
  return sessionUser;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public errorCode: string | undefined,
    message: string,
    public body: unknown,
  ) {
    super(message);
  }
}

async function rawRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<{ status: number; body: T }> {
  const headers: Record<string, string> = {
    // FormData bodies set their own multipart boundary.
    ...(init.body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" }),
    ...(init.headers as Record<string, string>),
  };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  // Absolute API paths (/api/admin/v1, /api/partner/v1…) bypass the
  // default web base; relative paths keep the historic prefix.
  const url = path.startsWith("/api/") ? path : `${BASE}${path}`;
  const response = await fetch(url, {
    ...init,
    headers,
    credentials: "include", // refresh cookie rides along on /auth paths
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* non-JSON (e.g. 204) */
  }
  return { status: response.status, body: body as T };
}

/** One shared silent-refresh at a time; resolves true when a new token landed. */
export async function tryRefresh(): Promise<boolean> {
  refreshPromise ??= (async () => {
    const { status, body } = await rawRequest<{
      access?: string;
      user?: SessionUserPayload;
    }>("/auth/refresh", {
      method: "POST",
    });
    if (status === 200 && body?.access) {
      accessToken = body.access;
      if (body.user) sessionUser = body.user;
      return true;
    }
    accessToken = null;
    return false;
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

export async function api<T extends ApiEnvelope | unknown>(
  path: string,
  init: RequestInit = {},
  { retryOn401 = true }: { retryOn401?: boolean } = {},
): Promise<T> {
  const { status, body } = await rawRequest<T>(path, init);

  if (status === 401 && retryOn401 && !path.includes("/auth/")) {
    if (await tryRefresh()) {
      return api<T>(path, init, { retryOn401: false });
    }
  }
  if (status >= 400) {
    const envelope = body as ApiEnvelope | null;
    throw new ApiError(
      status,
      envelope?.error_code,
      envelope?.message ?? `Request failed (${status})`,
      body,
    );
  }
  return body;
}

export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: data === undefined ? undefined : JSON.stringify(data),
  });

export const get = <T>(path: string) => api<T>(path);

export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });

export const put = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(data) });
