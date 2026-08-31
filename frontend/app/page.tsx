/** doocall.local — public landing. Server component; locale defaults to UZ
 * (landing-specific), overridable via the shared doocall_locale cookie.
 * Bolder art direction than the cabinet: dark hero, display face, big
 * numerals — same token system. */

import {
  ArrowDownLeft,
  BarChart3,
  Contact2,
  LayoutDashboard,
  Phone,
  PhoneCall,
  Settings,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";

import { CabinetMenu } from "@/components/landing/CabinetMenu";
import { DownloadApp } from "@/components/landing/DownloadApp";
import { LandingLocaleSwitcher } from "@/components/landing/LandingLocaleSwitcher";
import { RefCapture } from "@/components/landing/RefCapture";
import { PricingSection } from "@/components/landing/PricingSection";
import en from "@/messages/en.json";
import ru from "@/messages/ru.json";
import uz from "@/messages/uz.json";

const MESSAGES = { uz, ru, en } as const;
type LandingLocale = keyof typeof MESSAGES;

export const metadata: Metadata = {
  title: "dooCall — qo'ng'iroqlarni yozib olish va nazorat qilish",
  description:
    "Operatorlaringizning barcha qo'ng'iroqlari: yozuvlar, statistika, hisobotlar. 14 kun bepul.",
  openGraph: {
    title: "dooCall",
    description: "Har bir qo'ng'iroq — nazorat ostida. Call-recording SaaS.",
    url: "https://doocall.local",
    siteName: "dooCall",
    type: "website",
  },
};

async function landingLocale(): Promise<LandingLocale> {
  const store = await cookies();
  const cookie = store.get("doocall_locale")?.value;
  return cookie && cookie in MESSAGES ? (cookie as LandingLocale) : "uz"; // uz default
}

export default async function Landing() {
  const locale = await landingLocale();
  const t = MESSAGES[locale].landing;
  const year = new Date().getFullYear();

  const features = [
    { icon: LayoutDashboard, title: t.fDashboard, text: t.fDashboardText },
    { icon: Phone, title: t.fCalls, text: t.fCallsText },
    { icon: Contact2, title: t.fContacts, text: t.fContactsText },
    { icon: BarChart3, title: t.fReports, text: t.fReportsText },
    { icon: Settings, title: t.fSettings, text: t.fSettingsText },
    { icon: ShieldCheck, title: t.fSecurity, text: t.fSecurityText },
  ];
  const steps = [
    { icon: Smartphone, title: t.step1Title, text: t.step1Text },
    { icon: PhoneCall, title: t.step2Title, text: t.step2Text },
    { icon: BarChart3, title: t.step3Title, text: t.step3Text },
  ];
  const faqs = [
    { q: t.faq1q, a: t.faq1a },
    { q: t.faq2q, a: t.faq2a },
    { q: t.faq3q, a: t.faq3a },
    { q: t.faq4q, a: t.faq4a },
  ];

  return (
    <div className="bg-bg">
      <RefCapture />
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <span className="flex items-center gap-2">
          <span className="grid size-9 place-items-center rounded-md bg-accent text-accent-fg">
            <PhoneCall className="size-4" />
          </span>
          <span className="font-[family-name:var(--font-display)] text-xl font-bold">
            dooCall
          </span>
        </span>
        <div className="flex items-center gap-3">
          <Link
            href="/help/recording"
            className="hidden text-sm font-medium text-fg-muted hover:text-accent sm:block"
          >
            {t.helpNav}
          </Link>
          <LandingLocaleSwitcher current={locale} />
          <CabinetMenu
            labels={{
              button: t.cabinetMenu,
              email: t.menuEmail,
              password: t.menuPassword,
              signIn: t.menuSignIn,
              myCompanies: t.menuMyCompanies,
              openPortal: t.menuOpenPortal,
              logout: t.menuLogout,
              error: t.menuError,
              noAccount: t.menuNoAccount,
              register: t.menuRegister,
            }}
          />
        </div>
      </header>

      {/* ── Hero: dark, teal glow, fixed min-height (no CLS) ───────────── */}
      <section className="relative overflow-hidden bg-[#0f1a19] text-white">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-40 left-1/2 h-[480px] w-[720px] -translate-x-1/2 rounded-full opacity-30 blur-3xl"
          style={{
            background: "radial-gradient(closest-side, #2a9691, transparent)",
          }}
        />
        <div className="relative mx-auto grid min-h-[560px] max-w-6xl items-center gap-12 px-6 py-20 lg:grid-cols-2">
          <div>
            <h1
              data-testid="hero-title"
              className="font-[family-name:var(--font-display)] text-4xl font-bold leading-tight tracking-tight sm:text-5xl"
            >
              {t.heroTitle}
            </h1>
            <p className="mt-5 max-w-lg text-lg text-white/70">
              {t.heroSubtitle}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/register"
                data-testid="hero-cta"
                className="rounded-md bg-accent px-6 py-3 text-sm font-bold text-accent-fg hover:opacity-90"
              >
                {t.heroCta}
              </Link>
              <a
                href="#pricing"
                className="rounded-md border border-white/20 px-6 py-3 text-sm font-medium text-white/80 hover:bg-white/5"
              >
                → {t.pricingTitle}
              </a>
              <DownloadApp label={t.downloadApk} />
            </div>
          </div>

          {/* Product frame — pure CSS mock of the cabinet (stable size). */}
          <div className="hidden select-none lg:block" aria-hidden>
            <div className="h-[360px] rounded-xl border border-white/10 bg-[#1b1e1d] p-4 shadow-2xl">
              <div className="flex gap-1.5 pb-3">
                <span className="size-2.5 rounded-full bg-white/15" />
                <span className="size-2.5 rounded-full bg-white/15" />
                <span className="size-2.5 rounded-full bg-white/15" />
              </div>
              <div className="grid h-[300px] grid-cols-[130px_1fr] gap-3">
                <div className="space-y-2 rounded-lg bg-white/5 p-3">
                  {[38, 60, 52, 46, 58].map((width, index) => (
                    <div
                      key={index}
                      className={
                        index === 0
                          ? "h-2.5 rounded bg-accent/80"
                          : "h-2.5 rounded bg-white/15"
                      }
                      style={{ width: `${width}%` }}
                    />
                  ))}
                </div>
                <div className="space-y-3">
                  <div className="flex h-24 items-end gap-2 rounded-lg bg-white/5 p-3">
                    {[60, 90, 45, 75, 35, 82].map((height, index) => (
                      <div
                        key={index}
                        className="flex-1 overflow-hidden rounded-t"
                      >
                        <div
                          className="bg-danger-500/80"
                          style={{ height: `${(100 - height) * 0.3}px` }}
                        />
                        <div
                          className="bg-accent/90"
                          style={{ height: `${height * 0.6}px` }}
                        />
                      </div>
                    ))}
                  </div>
                  <div className="space-y-2 rounded-lg bg-white/5 p-3">
                    {[0, 1, 2, 3].map((index) => (
                      <div key={index} className="flex items-center gap-2">
                        <ArrowDownLeft className="size-3 text-accent" />
                        <div className="h-2 flex-1 rounded bg-white/15" />
                        <div className="h-2 w-8 rounded bg-white/25" />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ───────────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-center font-[family-name:var(--font-display)] text-3xl font-bold sm:text-4xl">
          {t.howTitle}
        </h2>
        <div className="mt-12 grid gap-8 sm:grid-cols-3">
          {steps.map((step, index) => (
            <div
              key={step.title}
              className="relative rounded-2xl border border-border bg-surface p-6"
            >
              <span className="tnum absolute -top-5 left-6 font-[family-name:var(--font-display)] text-6xl font-bold text-accent/15">
                {index + 1}
              </span>
              <step.icon className="size-6 text-accent" />
              <h3 className="mt-3 font-semibold">{step.title}</h3>
              <p className="mt-1.5 text-sm text-fg-muted">{step.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Feature grid ───────────────────────────────────────────────── */}
      <section className="bg-surface-2 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center font-[family-name:var(--font-display)] text-3xl font-bold sm:text-4xl">
            {t.featuresTitle}
          </h2>
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="rounded-xl border border-border bg-surface p-5 transition-shadow hover:shadow-md"
              >
                <feature.icon className="size-5 text-accent" />
                <h3 className="mt-3 text-sm font-semibold">{feature.title}</h3>
                <p className="mt-1 text-sm text-fg-muted">{feature.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing (live) ─────────────────────────────────────────────── */}
      <PricingSection
        strings={{
          title: t.pricingTitle,
          perOperator: t.pricingPerOperator,
          seats: t.pricingSeats,
          total: t.pricingTotal,
          trial: t.pricingTrial,
        }}
      />

      {/* ── FAQ ────────────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-3xl px-6 pb-20">
        <h2 className="text-center font-[family-name:var(--font-display)] text-3xl font-bold">
          {t.faqTitle}
        </h2>
        <div className="mt-8 space-y-3">
          {faqs.map((faq) => (
            <details
              key={faq.q}
              className="group rounded-xl border border-border bg-surface px-5 py-4"
            >
              <summary className="cursor-pointer list-none text-sm font-semibold marker:hidden">
                {faq.q}
                <span className="float-right text-fg-faint transition-transform group-open:rotate-45">
                  +
                </span>
              </summary>
              <p className="mt-2 text-sm text-fg-muted">{faq.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="border-t border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-fg-muted">
          <span className="flex items-center gap-2 font-[family-name:var(--font-display)] font-bold text-fg">
            <PhoneCall className="size-4 text-accent" /> dooCall
          </span>
          <span>
            {t.footerContact}:{" "}
            <a
              href="mailto:hello@doocall.uz"
              className="text-accent hover:underline"
            >
              hello@doocall.uz
            </a>{" "}
            ·{" "}
            <a
              href="tel:+998997980727"
              className="tnum text-accent hover:underline"
            >
              +998 99 798-07-27
            </a>
          </span>
          <span>
            © {year} dooCall. {t.footerRights}.
          </span>
        </div>
      </footer>
    </div>
  );
}
