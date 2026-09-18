"use client";

/** Sales-manager portal shell. */

import { useQuery } from "@tanstack/react-query";
import {
  Bell,
  Briefcase,
  Handshake,
  KanbanSquare,
  LayoutDashboard,
  ListTodo,
  LogOut,
  UserRound,
  Wallet,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { PortalLocaleSwitcher } from "@/components/PortalLocaleSwitcher";
import { fetchBoardStats, fetchSalesNotifications } from "@/lib/api/sales";
import { RequireAuth, useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/sales", key: "overview", icon: LayoutDashboard },
  { href: "/sales/crm", key: "crm", icon: KanbanSquare },
  { href: "/sales/tasks", key: "tasks", icon: ListTodo },
  { href: "/sales/integrators", key: "integrators", icon: Handshake },
  { href: "/sales/payouts", key: "payouts", icon: Wallet },
  { href: "/sales/notifications", key: "notifications", icon: Bell },
  { href: "/sales/profile", key: "profile", icon: UserRound },
] as const;

function SalesShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("sales");
  const tTop = useTranslations("topbar");
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { data: notifs } = useQuery({
    queryKey: ["sales-notifications"],
    queryFn: fetchSalesNotifications,
    refetchInterval: 60_000,
  });
  const { data: boardStats } = useQuery({
    queryKey: ["sales-board-stats"],
    queryFn: fetchBoardStats,
    refetchInterval: 60_000,
  });
  const unread = notifs?.unread ?? 0;
  const openTasks = (boardStats?.overdue_tasks ?? 0) + (boardStats?.today_tasks ?? 0);
  const badge = (key: string) =>
    key === "notifications" ? unread : key === "tasks" ? openTasks : 0;

  return (
    <div className="min-h-screen bg-bg" data-testid="sales-shell">
      <aside className="fixed inset-y-0 left-0 z-30 flex w-[236px] flex-col border-r border-border bg-surface max-sm:hidden">
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <span className="grid size-8 place-items-center rounded-md bg-accent text-accent-fg">
            <Briefcase className="size-4" />
          </span>
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold">
            dooCall
          </span>
          <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent">
            Sales
          </span>
        </div>
        <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
          {NAV.map(({ href, key, icon: Icon }) => {
            const active =
              href === "/sales" ? pathname === "/sales" : pathname.startsWith(href);
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
                <span className="flex-1">{t(key)}</span>
                {badge(key) > 0 && (
                  <span className="tnum rounded-full bg-danger px-1.5 text-[10px] font-bold text-white">
                    {badge(key)}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border p-2">
          <div className="px-3 py-2">
            <PortalLocaleSwitcher />
          </div>
          <p className="truncate px-3 py-1 text-xs text-fg-faint">{user?.email}</p>
          <button
            type="button"
            onClick={() => logout()}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-fg-muted hover:bg-surface-2"
          >
            <LogOut className="size-4" /> {tTop("logout")}
          </button>
        </div>
      </aside>
      <main className="p-4 sm:ml-[236px] md:p-6">{children}</main>
    </div>
  );
}

export default function SalesLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <SalesShell>{children}</SalesShell>
    </RequireAuth>
  );
}
