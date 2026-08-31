"use client";

/** MoiZvonki-style «Личный кабинет» header dropdown on the landing.
 * Login happens inline (the visitor stays on the landing); on success the
 * account's companies are listed and each opens its own subdomain cabinet
 * (e.g. deepvision.doocall.uz). Portal accounts get their portal link. */

import {
  Building2,
  ChevronDown,
  ExternalLink,
  Loader2,
  LogOut,
  UserRound,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface CabinetMenuLabels {
  button: string;
  email: string;
  password: string;
  signIn: string;
  myCompanies: string;
  openPortal: string;
  logout: string;
  error: string;
  noAccount: string;
  register: string;
}

interface CompanyEntry {
  name: string;
  slug: string;
  url: string;
}

interface SessionState {
  portal: string;
  portal_url: string;
  companies: CompanyEntry[];
  email: string;
}

async function api(path: string, init?: RequestInit) {
  const response = await fetch(`/api/web/v1${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}

export function CabinetMenu({ labels }: { labels: CabinetMenuLabels }) {
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [session, setSession] = useState<SessionState | null>(null);
  const [access, setAccess] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const probed = useRef(false);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const loadCompanies = async (token: string, userEmail: string) => {
    setAccess(token);
    const menu = await api("/auth/companies", {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
    setSession({
      portal: menu.portal,
      portal_url: menu.portal_url,
      companies: menu.companies,
      email: userEmail,
    });
  };

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    // First open: silently recover an existing session via the
    // domain-wide refresh cookie — the visitor stays on the landing.
    if (next && !probed.current) {
      probed.current = true;
      setChecking(true);
      try {
        const body = await api("/auth/refresh", { method: "POST" });
        await loadCompanies(body.access, body.user?.email ?? "");
      } catch {
        /* no session — show the login form */
      } finally {
        setChecking(false);
      }
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError(false);
    try {
      const body = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      await loadCompanies(body.access, body.user?.email ?? email);
      setPassword("");
    } catch {
      setError(true);
    } finally {
      setPending(false);
    }
  };

  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      /* cookie already gone */
    }
    setSession(null);
    setAccess(null);
  };

  // Cookies don't cross *.localhost in dev — hand the session over with a
  // one-time code the subdomain redeems (works with any cookie policy).
  const openCompany = async (event: React.MouseEvent, url: string) => {
    event.preventDefault();
    let target = url;
    try {
      const body = await api("/auth/handoff", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access}`,
        },
      });
      target = `${url}?sso=${encodeURIComponent(body.code)}`;
    } catch {
      /* fall back to a plain visit → login page */
    }
    window.location.href = target;
  };

  return (
    <div className="relative" ref={rootRef} data-testid="cabinet-menu">
      <button
        type="button"
        data-testid="cabinet-menu-button"
        onClick={toggle}
        className="flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-surface-2"
      >
        <UserRound className="size-4" />
        {labels.button}
        <ChevronDown
          className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="absolute right-0 z-40 mt-2 w-72 rounded-xl border border-border bg-surface p-3 shadow-xl">
          {checking ? (
            <div className="grid h-24 place-items-center">
              <Loader2 className="size-5 animate-spin text-fg-faint" />
            </div>
          ) : session ? (
            <div data-testid="cabinet-menu-companies">
              <p className="mb-2 truncate px-1 text-xs text-fg-faint">
                {session.email}
              </p>
              {session.portal === "cabinet" ? (
                <>
                  <p className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-fg-muted">
                    {labels.myCompanies}
                  </p>
                  <ul className="space-y-1">
                    {session.companies.map((companyEntry) => (
                      <li key={companyEntry.slug}>
                        <a
                          href={companyEntry.url}
                          onClick={(event) =>
                            openCompany(event, companyEntry.url)
                          }
                          data-testid={`company-link-${companyEntry.slug}`}
                          className="flex items-center gap-2 rounded-lg px-2 py-2 text-sm font-medium hover:bg-accent-soft hover:text-accent"
                        >
                          <span className="grid size-8 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">
                            <Building2 className="size-4" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate">
                              {companyEntry.name}
                            </span>
                            <span className="block truncate text-xs font-normal text-fg-faint">
                              {new URL(companyEntry.url).host}
                            </span>
                          </span>
                          <ExternalLink className="size-3.5 shrink-0 text-fg-faint" />
                        </a>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <a
                  href={session.portal_url}
                  className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-accent-fg hover:opacity-90"
                >
                  <ExternalLink className="size-4" /> {labels.openPortal}
                </a>
              )}
              <button
                type="button"
                onClick={logout}
                className="mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-fg-muted hover:bg-surface-2"
              >
                <LogOut className="size-3.5" /> {labels.logout}
              </button>
            </div>
          ) : (
            <form onSubmit={submit} data-testid="cabinet-menu-login">
              <input
                type="email"
                name="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={labels.email}
                className="mb-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <input
                type="password"
                name="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={labels.password}
                className="mb-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
              />
              {error && (
                <p className="mb-2 text-xs text-danger">{labels.error}</p>
              )}
              <button
                type="submit"
                disabled={pending}
                className="w-full rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
              >
                {pending ? "…" : labels.signIn}
              </button>
              <p className="mt-2 text-center text-xs text-fg-muted">
                {labels.noAccount}{" "}
                <a
                  href="/register"
                  data-testid="menu-register"
                  className="font-semibold text-accent hover:underline"
                >
                  {labels.register}
                </a>
              </p>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
