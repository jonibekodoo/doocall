"use client";

import { useRouter } from "next/navigation";

const LOCALES = ["uz", "ru", "en"] as const;

export function LandingLocaleSwitcher({ current }: { current: string }) {
  const router = useRouter();
  const change = (locale: string) => {
    document.cookie = `doocall_locale=${locale};path=/;max-age=31536000;samesite=lax`;
    router.refresh();
  };
  return (
    <div
      className="flex rounded-full border border-border p-0.5"
      role="group"
      aria-label="language"
      data-testid="landing-locale"
    >
      {LOCALES.map((locale) => (
        <button
          key={locale}
          type="button"
          onClick={() => change(locale)}
          className={
            locale === current
              ? "rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold uppercase text-accent-fg"
              : "rounded-full px-2.5 py-0.5 text-xs font-medium uppercase text-fg-faint hover:text-fg"
          }
        >
          {locale}
        </button>
      ))}
    </div>
  );
}
