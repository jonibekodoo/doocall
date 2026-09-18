"use client";

/** Staff monitoring — coming-soon teaser (check-in/out + live location). */

import { Clock, MapPin, Route, UserCheck } from "lucide-react";
import { useTranslations } from "next-intl";

const FEATURES = ["fCheckin", "fLocation", "fRoute"] as const;
const FEATURE_ICONS = {
  fCheckin: Clock,
  fLocation: MapPin,
  fRoute: Route,
} as const;

export default function MonitoringPage() {
  const t = useTranslations("monitoring");

  return (
    <div
      data-testid="monitoring-page"
      className="relative overflow-hidden rounded-2xl border border-border"
    >
      {/* Map-flavoured backdrop */}
      <div className="absolute inset-0 bg-[#0b1512]" />
      <div className="pointer-events-none absolute -left-32 -top-32 size-96 rounded-full bg-[#14b8a6]/35 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 left-1/3 size-96 rounded-full bg-[#22c55e]/25 blur-3xl" />
      <div className="pointer-events-none absolute -right-24 -top-24 size-80 rounded-full bg-[#0ea5e9]/25 blur-3xl" />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage:
            "linear-gradient(#ffffff 1px, transparent 0), linear-gradient(90deg, #ffffff 1px, transparent 0)",
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative grid min-h-[70vh] place-items-center px-6 py-20 text-center text-white">
        <div className="max-w-2xl">
          <span className="mx-auto grid size-16 place-items-center rounded-2xl bg-white/10 backdrop-blur">
            <UserCheck className="size-8 text-[#5eead4]" />
          </span>
          <p className="mt-6 inline-block rounded-full border border-white/20 bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-[#7dd3fc]">
            {t("badge")}
          </p>
          <h1 className="mt-4 bg-gradient-to-r from-[#5eead4] via-[#7dd3fc] to-[#86efac] bg-clip-text font-[family-name:var(--font-display)] text-4xl font-bold text-transparent sm:text-5xl">
            {t("title")}
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-white/70">
            {t("text")}
          </p>

          <div className="mt-10 grid gap-3 sm:grid-cols-3">
            {FEATURES.map((key) => {
              const Icon = FEATURE_ICONS[key];
              return (
                <div
                  key={key}
                  className="rounded-xl border border-white/10 bg-white/5 p-4 backdrop-blur"
                >
                  <Icon className="mx-auto size-5 text-[#5eead4]" />
                  <p className="mt-2 text-sm font-medium text-white/85">
                    {t(key)}
                  </p>
                </div>
              );
            })}
          </div>

          <p className="mt-10 text-xs uppercase tracking-widest text-white/40">
            {t("soon")}
          </p>
        </div>
      </div>
    </div>
  );
}
