"use client";

/** Admin profile — identity hero, language, theme and session controls. */

import { Globe, LogOut, Moon, ShieldCheck, Sun, UserCog } from "lucide-react";
import { useTranslations } from "next-intl";

import { PortalLocaleSwitcher } from "@/components/PortalLocaleSwitcher";
import { useAuth } from "@/lib/auth";

export default function AdminProfilePage() {
  const t = useTranslations("admin.profile");
  const { user, logout } = useAuth();

  const toggleTheme = () => {
    const root = document.documentElement;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("doocall_theme", next);
  };

  const initial = (user?.email ?? "?").slice(0, 1).toUpperCase();
  const isSuper = user?.role === "superadmin";

  return (
    <div data-testid="admin-profile" className="max-w-2xl">
      {/* Hero */}
      <div className="relative mb-5 overflow-hidden rounded-2xl border border-border bg-surface">
        <div className="h-20 bg-gradient-to-r from-[#141817] via-[#1f2a27] to-accent/50" />
        <div className="px-5 pb-5">
          <div className="-mt-9 mb-3 flex items-end gap-4">
            <span className="grid size-18 shrink-0 place-items-center rounded-2xl border-4 border-surface bg-[#141817] text-2xl font-bold text-white shadow-md">
              {initial}
            </span>
            <div className="min-w-0 pb-0.5">
              <h1 className="truncate text-xl font-semibold">{user?.email}</h1>
              <p className="flex items-center gap-1.5 text-sm text-fg-muted">
                <ShieldCheck className="size-3.5 text-warning" />
                {isSuper ? t("roleSuperadmin") : t("rolePlatformAdmin")}
              </p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/15 px-3 py-1 text-xs font-bold uppercase tracking-wide text-warning">
            <UserCog className="size-3.5" /> {user?.role}
          </span>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Language */}
        <section className="rounded-2xl border border-border bg-surface p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
            <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">
              <Globe className="size-4" />
            </span>
            {t("language")}
          </h2>
          <PortalLocaleSwitcher />
        </section>

        {/* Appearance */}
        <section className="rounded-2xl border border-border bg-surface p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
            <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">
              <Sun className="size-4" />
            </span>
            {t("appearance")}
          </h2>
          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-surface-2"
          >
            <Sun className="size-4 [data-theme=dark]_&:hidden" />
            <Moon className="hidden size-4 [data-theme=dark]_&:block" />
            {t("toggleTheme")}
          </button>
        </section>
      </div>

      {/* Session */}
      <div className="mt-4 flex items-center justify-between rounded-2xl border border-border bg-surface p-4">
        <p className="text-sm text-fg-muted">{t("sessionHint")}</p>
        <button
          type="button"
          data-testid="profile-logout"
          onClick={() => logout()}
          className="inline-flex items-center gap-2 rounded-lg border border-danger/30 px-4 py-2 text-sm font-semibold text-danger hover:bg-danger/5"
        >
          <LogOut className="size-4" /> {t("signOut")}
        </button>
      </div>
    </div>
  );
}
