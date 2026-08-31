"use client";

/** Partner portal shell (A.4) — MoySklad-style partner cabinet. */

import {
  BarChart3,
  Building2,
  Handshake,
  LayoutDashboard,
  LogOut,
  UserPlus,
  UserRound,
  Wallet,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { PortalLocaleSwitcher } from "@/components/PortalLocaleSwitcher";
import { RequireAuth, useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/partner", key: "overview", icon: LayoutDashboard },
  { href: "/partner/companies", key: "companies", icon: Building2 },
  { href: "/partner/add", key: "add", icon: UserPlus },
  { href: "/partner/accruals", key: "accruals", icon: BarChart3 },
  { href: "/partner/payouts", key: "payouts", icon: Wallet },
  { href: "/partner/profile", key: "profile", icon: UserRound },
] as const;

function PartnerShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("partner");
  const tTop = useTranslations("topbar");
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-bg" data-testid="partner-shell">
      <aside className="fixed inset-y-0 left-0 z-30 flex w-[236px] flex-col border-r border-border bg-surface max-sm:hidden">
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <span className="grid size-8 place-items-center rounded-md bg-accent text-accent-fg">
            <Handshake className="size-4" />
          </span>
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold">
            dooCall
          </span>
          <span
            data-testid="partner-badge"
            className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent"
          >
            Partner
          </span>
        </div>
        <nav className="flex-1 space-y-1 p-2">
          {NAV.map(({ href, key, icon: Icon }) => {
            const active =
              href === "/partner"
                ? pathname === "/partner"
                : pathname.startsWith(href);
            return (
              <Link
                key={key}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                  active
                    ? "bg-accent-soft text-accent"
                    : "text-fg-muted hover:bg-surface-2 hover:text-fg",
                )}
              >
                {active && (
                  <span className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-accent" />
                )}
                <Icon className="size-4 shrink-0" />
                {t(key)}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border p-2">
          <div className="px-3 py-2">
            <PortalLocaleSwitcher />
          </div>
          <p className="truncate px-3 py-1 text-xs text-fg-faint">
            {user?.email}
          </p>
          <button
            type="button"
            onClick={() => logout()}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-fg-muted hover:bg-surface-2"
          >
            <LogOut className="size-4" /> {tTop("logout")}
          </button>
        </div>
      </aside>
      <main className="mx-auto max-w-[1200px] p-4 sm:ml-[236px] md:p-6">
        {children}
      </main>
    </div>
  );
}

export default function PartnerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RequireAuth>
      <PartnerShell>{children}</PartnerShell>
    </RequireAuth>
  );
}
