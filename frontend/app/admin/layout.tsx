"use client";

/** Admin portal shell (A.1/A.3) — darker sidebar variant + Admin badge on
 * the shared tokens. Superadmin-only nav items are ABSENT (not disabled)
 * for platform_admin. */

import {
  Building2,
  CreditCard,
  Handshake,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Percent,
  Plug,
  ScrollText,
  ShieldCheck,
  Smartphone,
  Tag,
  UserRound,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { PortalLocaleSwitcher } from "@/components/PortalLocaleSwitcher";
import { RequireAuth, useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  {
    href: "/admin",
    label: "dashboard",
    icon: LayoutDashboard,
    superOnly: false,
  },
  {
    href: "/admin/companies",
    label: "companies",
    icon: Building2,
    superOnly: false,
  },
  {
    href: "/admin/payments",
    label: "payments",
    icon: CreditCard,
    superOnly: false,
  },
  {
    href: "/admin/integrators",
    label: "integrators",
    icon: Handshake,
    superOnly: false,
  },
  {
    href: "/admin/app",
    label: "app",
    icon: Smartphone,
    superOnly: false,
  },
  {
    href: "/admin/crm-catalog",
    label: "crmCatalog",
    icon: Plug,
    superOnly: false,
  },
  { href: "/admin/audit", label: "audit", icon: ScrollText, superOnly: false },
  { href: "/admin/pricing", label: "pricing", icon: Tag, superOnly: true },
  {
    href: "/admin/cashback",
    label: "cashback",
    icon: Percent,
    superOnly: true,
  },
  {
    href: "/admin/payouts",
    label: "payouts",
    icon: ListChecks,
    superOnly: true,
  },
  {
    href: "/admin/admins",
    label: "admins",
    icon: Users,
    superOnly: true,
  },
  {
    href: "/admin/profile",
    label: "profile",
    icon: UserRound,
    superOnly: false,
  },
] as const;

function AdminShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("admin");
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const isSuper = user?.role === "superadmin";
  const items = NAV.filter((item) => !item.superOnly || isSuper);

  return (
    <div className="min-h-screen bg-bg" data-testid="admin-shell">
      {/* Dark admin sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 flex w-[236px] flex-col bg-[#141817] text-white/80 max-sm:hidden">
        <div className="flex h-14 items-center gap-2 border-b border-white/10 px-4">
          <span className="grid size-8 place-items-center rounded-md bg-accent text-accent-fg">
            <ShieldCheck className="size-4" />
          </span>
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold text-white">
            dooCall
          </span>
          <span
            data-testid="admin-badge"
            className="rounded-full bg-warning/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-warning"
          >
            Admin
          </span>
        </div>
        <nav className="flex-1 space-y-1 p-2">
          {items.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/admin"
                ? pathname === "/admin"
                : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                  active
                    ? "bg-white/10 text-white"
                    : "hover:bg-white/5 hover:text-white",
                )}
              >
                {active && (
                  <span className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-accent" />
                )}
                <Icon className="size-4 shrink-0" />
                {t(`nav.${label}`)}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-white/10 p-2">
          <div className="px-3 py-2">
            <PortalLocaleSwitcher dark />
          </div>
          <p className="truncate px-3 py-1 text-xs text-white/40">
            {user?.email}
          </p>
          <p className="px-3 pb-1 text-[10px] uppercase text-white/30">
            {user?.role}
          </p>
          <button
            type="button"
            data-testid="admin-logout"
            onClick={() => logout()}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-white/5 hover:text-white"
          >
            <LogOut className="size-4" /> {t("logout")}
          </button>
        </div>
      </aside>

      <main className="mx-auto max-w-[1400px] p-4 sm:ml-[236px] md:p-6">
        {children}
      </main>
    </div>
  );
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RequireAuth>
      <AdminShell>{children}</AdminShell>
    </RequireAuth>
  );
}
