"use client";

/** Auth session: login/register/logout + silent cookie refresh + route guard. */

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getSessionUser,
  post,
  setAccessToken,
  tryRefresh,
} from "@/lib/api/client";
import type { LoginResponse, RegisterResponse } from "@/lib/api/types";

interface SessionUser {
  email: string;
  company: string | null;
  role?: string;
  portal?: string;
}

/** Post-login destination by portal (A.1 routing). */
export function homeFor(portal: string | undefined): string {
  if (portal === "admin") return "/admin";
  if (portal === "partner") return "/partner";
  return "/cabinet";
}

function setPortalCookie(portal: string | undefined) {
  document.cookie = `doocall_portal=${portal ?? "cabinet"};path=/;max-age=2592000;samesite=lax`;
}

interface AuthState {
  status: "loading" | "authenticated" | "anonymous";
  user: SessionUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: {
    company_name: string;
    admin_email: string;
    phone: string;
    password: string;
    ref?: string | null;
  }) => Promise<RegisterResponse>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);

  // Session recovery: redeem a one-time ?sso= hand-off code (landing →
  // company subdomain, where cookies may not follow), else one silent
  // refresh on mount (httpOnly cookie → access).
  useEffect(() => {
    let cancelled = false;
    const bootstrap = async () => {
      const params = new URLSearchParams(window.location.search);
      const sso = params.get("sso");
      if (sso) {
        params.delete("sso");
        const query = params.toString();
        window.history.replaceState(
          null,
          "",
          window.location.pathname + (query ? `?${query}` : ""),
        );
        try {
          const body = await post<LoginResponse>("/auth/handoff/redeem", {
            code: sso,
          });
          setAccessToken(body.access);
          if (!cancelled) {
            setUser(body.user);
            setPortalCookie(body.user?.portal);
            setStatus("authenticated");
          }
          return;
        } catch {
          /* expired/used code — fall back to the cookie refresh */
        }
      }
      const ok = await tryRefresh();
      if (cancelled) return;
      const recovered = getSessionUser();
      if (ok && recovered) {
        setUser(recovered);
        setPortalCookie(recovered.portal);
      }
      setStatus(ok ? "authenticated" : "anonymous");
    };
    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const body = await post<LoginResponse>("/auth/login", { email, password });
    setAccessToken(body.access);
    setUser(body.user);
    setPortalCookie((body.user as SessionUser).portal);
    setStatus("authenticated");
  }, []);

  const register = useCallback(
    async (payload: {
      company_name: string;
      admin_email: string;
      phone: string;
      password: string;
      ref?: string | null;
    }) => {
      const body = await post<RegisterResponse>("/auth/register", payload);
      // Auto-login right after registration.
      await login(payload.admin_email, payload.password);
      return body;
    },
    [login],
  );

  const logout = useCallback(async () => {
    try {
      await post("/auth/logout");
    } finally {
      setAccessToken(null);
      setUser(null);
      document.cookie = "doocall_portal=;path=/;max-age=0";
      setStatus("anonymous");
    }
  }, []);

  const value = useMemo(
    () => ({ status, user, login, register, logout }),
    [status, user, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

/** Client-side route guard: anonymous users land on /login. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center text-fg-muted">
        <span className="animate-pulse">dooCall…</span>
      </div>
    );
  }
  return <>{children}</>;
}
