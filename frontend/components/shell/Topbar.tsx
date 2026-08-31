"use client";

import { LogOut, Moon, Sun, User } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const LOCALES = ["ru", "uz", "en"] as const;

export function Topbar({ periodSlot }: { periodSlot?: React.ReactNode }) {
  const t = useTranslations("topbar");
  const locale = useLocale();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const setLocale = (next: string) => {
    document.cookie = `doocall_locale=${next};path=/;max-age=31536000;samesite=lax`;
    router.refresh();
  };

  const toggleTheme = () => {
    const root = document.documentElement;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("doocall_theme", next);
  };

  return (
    <header
      data-testid="topbar"
      className="sticky top-0 z-20 flex h-[var(--topbar-h)] items-center justify-between gap-3 border-b border-border bg-surface/90 px-4 backdrop-blur"
    >
      {/* Period quick-filter slot (pages inject their own control) */}
      <div className="min-w-0 flex-1">{periodSlot}</div>

      <div className="flex items-center gap-1.5">
        {/* Locale switcher */}
        <div
          className="flex rounded-full border border-border p-0.5"
          role="group"
          aria-label={t("language")}
        >
          {LOCALES.map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => setLocale(code)}
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium uppercase",
                code === locale
                  ? "bg-accent text-accent-fg"
                  : "text-fg-faint hover:text-fg",
              )}
            >
              {code}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={toggleTheme}
          aria-label={t("theme")}
          className="grid size-8 place-items-center rounded-md text-fg-muted hover:bg-surface-2"
        >
          <Sun className="size-4 [data-theme=dark]_&:hidden" />
          <Moon className="hidden size-4 [data-theme=dark]_&:block" />
        </button>

        {/* User menu */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            data-testid="user-menu"
            onClick={() => setMenuOpen((open) => !open)}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-2"
          >
            <span className="grid size-7 place-items-center rounded-full bg-surface-3 text-fg-muted">
              <User className="size-4" />
            </span>
            <span className="hidden max-w-40 truncate text-fg-muted md:block">
              {user?.email}
            </span>
          </button>
          {menuOpen && (
            <div className="absolute right-0 mt-1 w-48 rounded-md border border-border bg-surface p-1 shadow-lg">
              <button
                type="button"
                data-testid="logout"
                onClick={() => logout()}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm text-fg-muted hover:bg-surface-2 hover:text-fg"
              >
                <LogOut className="size-4" /> {t("logout")}
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
