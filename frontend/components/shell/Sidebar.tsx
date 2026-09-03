"use client";

import {
  BarChart3,
  ChevronLeft,
  Contact2,
  LayoutDashboard,
  Phone,
  PhoneCall,
  Settings,
  Sparkles,
} from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const NAV = [
  { key: "dashboard", href: "/cabinet", icon: LayoutDashboard },
  { key: "calls", href: "/cabinet/calls", icon: Phone },
  { key: "contacts", href: "/cabinet/contacts", icon: Contact2 },
  { key: "reports", href: "/cabinet/reports", icon: BarChart3 },
  { key: "aiAnalysis", href: "/cabinet/ai", icon: Sparkles },
  { key: "settings", href: "/cabinet/settings", icon: Settings },
] as const;

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const t = useTranslations("nav");
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/cabinet" ? pathname === "/cabinet" : pathname.startsWith(href);

  return (
    <aside
      data-testid="sidebar"
      data-collapsed={collapsed}
      className={cn(
        "fixed inset-y-0 left-0 z-30 flex flex-col border-r border-border bg-surface",
        "transition-[width] duration-200",
        collapsed ? "w-[var(--sidebar-w-collapsed)]" : "w-[var(--sidebar-w)]",
        "max-sm:hidden", // <640px: replaced by the top drawer
      )}
    >
      {/* Brand */}
      <div className="flex h-[var(--topbar-h)] items-center gap-2 border-b border-border px-4">
        <span className="grid size-8 shrink-0 place-items-center rounded-md bg-accent text-accent-fg">
          <PhoneCall className="size-4" />
        </span>
        {!collapsed && (
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold tracking-tight">
            dooCall
          </span>
        )}
      </div>

      {/* Primary nav */}
      <nav className="flex flex-1 flex-col gap-1 p-2" aria-label="Main">
        {NAV.map(({ key, href, icon: Icon }) => {
          const active = isActive(href);
          return (
            <Link
              key={key}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                "transition-colors",
                active
                  ? "bg-accent-soft text-accent [data-theme=dark]_&:bg-surface-3"
                  : "text-fg-muted hover:bg-surface-2 hover:text-fg",
              )}
            >
              {/* Active indicator bar */}
              {active && (
                <span className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-accent" />
              )}
              <Icon className="size-4 shrink-0" />
              {!collapsed && <span className="truncate">{t(key)}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Bottom: Мои звонки + collapse */}
      <div className="border-t border-border p-2">
        <Link
          href="/cabinet/my-calls"
          className={cn(
            "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
            isActive("/cabinet/my-calls")
              ? "bg-accent-soft text-accent"
              : "text-fg-muted hover:bg-surface-2 hover:text-fg",
          )}
        >
          <PhoneCall className="size-4 shrink-0" />
          {!collapsed && <span className="truncate">{t("myCalls")}</span>}
        </Link>
        <button
          type="button"
          onClick={onToggle}
          aria-label="Toggle sidebar"
          className="mt-1 flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-fg-faint hover:bg-surface-2 hover:text-fg"
        >
          <ChevronLeft
            className={cn(
              "size-4 shrink-0 transition-transform",
              collapsed && "rotate-180",
            )}
          />
          {!collapsed && <span>—</span>}
        </button>
      </div>
    </aside>
  );
}

/** Mobile nav (≤640px): horizontal icon strip under the topbar. */
export function MobileNav() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  return (
    <nav
      data-testid="mobile-nav"
      className="flex items-center gap-1 overflow-x-auto border-b border-border bg-surface px-2 py-1 sm:hidden"
      aria-label="Main"
    >
      {[
        ...NAV,
        { key: "myCalls", href: "/cabinet/my-calls", icon: PhoneCall } as const,
      ].map(({ key, href, icon: Icon }) => {
        const active =
          href === "/cabinet"
            ? pathname === "/cabinet"
            : pathname.startsWith(href);
        return (
          <Link
            key={key}
            href={href}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium",
              active
                ? "bg-accent text-accent-fg"
                : "text-fg-muted hover:bg-surface-2",
            )}
          >
            <Icon className="size-3.5" />
            {t(key)}
          </Link>
        );
      })}
    </nav>
  );
}
