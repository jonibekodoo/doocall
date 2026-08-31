"use client";

/** RU/UZ/EN pill switcher for the admin & partner sidebars. Writes the
 * `doocall_locale` cookie (same mechanism as the cabinet Topbar). */

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/utils";

const LOCALES = ["ru", "uz", "en"] as const;

export function PortalLocaleSwitcher({ dark = false }: { dark?: boolean }) {
  const t = useTranslations("topbar");
  const locale = useLocale();
  const router = useRouter();

  const setLocale = (next: string) => {
    document.cookie = `doocall_locale=${next};path=/;max-age=31536000;samesite=lax`;
    router.refresh();
  };

  return (
    <div
      data-testid="portal-locale"
      role="group"
      aria-label={t("language")}
      className={cn(
        "flex rounded-full border p-0.5",
        dark ? "border-white/15" : "border-border",
      )}
    >
      {LOCALES.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLocale(code)}
          className={cn(
            "flex-1 rounded-full px-2 py-0.5 text-xs font-medium uppercase",
            code === locale
              ? "bg-accent text-accent-fg"
              : dark
                ? "text-white/40 hover:text-white"
                : "text-fg-faint hover:text-fg",
          )}
        >
          {code}
        </button>
      ))}
    </div>
  );
}
