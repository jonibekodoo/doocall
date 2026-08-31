/** Landing help page: enabling BUILT-IN call recording on Samsung /
 * Xiaomi / Huawei. Server component; locale from the shared
 * doocall_locale cookie (landing default: uz). */

import { ArrowLeft, PhoneCall } from "lucide-react";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";

import { GuideSectionView } from "@/components/landing/GuideRenderer";
import { LandingLocaleSwitcher } from "@/components/landing/LandingLocaleSwitcher";
import { GUIDES } from "@/content/recording-guide";

type GuideLocale = keyof typeof GUIDES;

async function pickLocale(): Promise<GuideLocale> {
  const store = await cookies();
  const cookieLocale = store.get("doocall_locale")?.value;
  return cookieLocale === "ru" || cookieLocale === "en" ? cookieLocale : "uz";
}

export async function generateMetadata(): Promise<Metadata> {
  const guide = GUIDES[await pickLocale()];
  return { title: guide.metaTitle, description: guide.metaDescription };
}

const BRANDS = [
  { label: "Samsung", href: "#samsung", dot: "bg-[#1428A0]" },
  { label: "Xiaomi / Redmi / POCO", href: "#xiaomi", dot: "bg-[#FF6900]" },
  { label: "Huawei / Honor", href: "#huawei", dot: "bg-[#CF0A2C]" },
];

export default async function RecordingGuidePage() {
  const locale = await pickLocale();
  const guide = GUIDES[locale];

  return (
    <div className="bg-bg">
      {/* ── Header (landing style) ────────────────────────────────────── */}
      <header className="mx-auto flex max-w-4xl items-center justify-between px-6 py-5">
        <Link href="/" className="flex items-center gap-2">
          <span className="grid size-9 place-items-center rounded-md bg-accent text-accent-fg">
            <PhoneCall className="size-4" />
          </span>
          <span className="font-[family-name:var(--font-display)] text-xl font-bold">
            dooCall
          </span>
        </Link>
        <div className="flex items-center gap-3">
          <LandingLocaleSwitcher current={locale} />
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-3.5 py-2 text-sm font-medium hover:bg-surface-2"
          >
            <ArrowLeft className="size-4" /> {guide.backToLanding}
          </Link>
        </div>
      </header>

      {/* ── Hero (dark, like the landing) ─────────────────────────────── */}
      <section className="relative overflow-hidden bg-[#0f1a19] text-white">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-40 left-1/2 h-[380px] w-[640px] -translate-x-1/2 rounded-full opacity-30 blur-3xl"
          style={{
            background: "radial-gradient(closest-side, #2a9691, transparent)",
          }}
        />
        <div className="relative mx-auto max-w-4xl px-6 py-14">
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-bold leading-tight sm:text-4xl">
            {guide.heroTitle}
          </h1>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-white/70">
            {guide.heroText}
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            {BRANDS.map((brand) => (
              <a
                key={brand.href}
                href={brand.href}
                className="inline-flex items-center gap-2 rounded-full border border-white/15 px-4 py-1.5 text-sm font-medium text-white/90 hover:bg-white/5"
              >
                <span className={`size-2 rounded-full ${brand.dot}`} />
                {brand.label}
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* ── Body ──────────────────────────────────────────────────────── */}
      <main className="mx-auto max-w-4xl px-6 py-10">
        {/* TOC */}
        <nav className="mb-10 rounded-xl border border-border bg-surface p-5">
          <p className="mb-3 text-xs font-bold uppercase tracking-wide text-fg-muted">
            {guide.tocTitle}
          </p>
          <ol className="grid gap-1.5 sm:grid-cols-2">
            {guide.sections.map((section, index) => (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  className="inline-flex items-baseline gap-2 text-sm text-fg-muted hover:text-accent"
                >
                  <span className="tnum text-xs text-fg-faint">
                    {index + 1}.
                  </span>
                  {section.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="space-y-14">
          {guide.sections.map((section) => (
            <GuideSectionView key={section.id} section={section} />
          ))}
        </div>

        {/* ── Footer notes ──────────────────────────────────────────────── */}
        <div className="mt-14 space-y-4">
          <div className="rounded-xl border border-danger/30 bg-danger/5 px-5 py-4 text-sm leading-relaxed text-fg-muted">
            {guide.legalNote}
          </div>
          <div className="rounded-xl border border-border bg-surface px-5 py-4 text-sm leading-relaxed text-fg-muted">
            {guide.supportNote
              .split("**")
              .map((part, index) =>
                index % 2 === 1 ? <b key={index}>{part}</b> : part,
              )}
          </div>
        </div>
      </main>
    </div>
  );
}
