# PHASE 8 — Public landing + funnel (completed)

## Phase 7 verification (session start)

`make test` green; Playwright cabinet suite green after one regression fix
(the seat-toggle assertion needed row-scoping because earlier runs leave
deactivated operators — strict-mode violation, not a product bug).

## Delivered

1. **`GET /api/public/pricing/`** (also slash-less) — unauthenticated,
   Redis-cached (`PUBLIC_PRICING_CACHE_SECONDS`, default 60s), returns the
   current global PricingSetting with settings-default fallback. 3 backend
   tests: unauth 200 with exact body, **cached-within-TTL** (price change
   invisible until invalidation), fallback without a pricing row.
2. **Landing (doocall.local, `app/page.tsx`)** — server component, bolder
   art direction than the cabinet on the same tokens: dark `#0f1a19` hero
   with a radial teal glow, Space Grotesk display headings, oversized step
   numerals, pure-CSS product frame (fixed 360px height — no CLS). Sections:
   hero with value prop + CTA; how-it-works 3 steps (APK → calls → you see
   everything); 6-tile feature grid mirroring cabinet modules; **pricing
   with the LIVE per-operator price + seat slider** (1–50, monthly total =
   seats × price, trial note with live trial_days); FAQ accordion
   (details/summary, no JS); footer with contacts.
3. **i18n** — landing defaults to **UZ** (cookie-less visitors), switcher
   UZ/RU/EN shares the `doocall_locale` cookie with the cabinet; ru/en
   catalogs are complete mirrors (tested).
4. **SEO / Lighthouse-minded** — metadata + OpenGraph on the page,
   `opengraph-image.tsx` (generated 1200×630), `sitemap.ts`, `robots.ts`
   (cabinet + API disallowed); next/font (preloaded, latin+cyrillic); fixed
   min-heights on hero/pricing so nothing shifts while the live price loads.
5. **Registration funnel** — hero CTA → register (Phase-4 API) → auto-login
   → **`/cabinet/onboarding` checklist**: add operator (auto-completes from
   real operator count) → download APK (placeholder link, real artifact in
   Phase 9) → see first call (auto-completes from calls count); dismissible
   with persisted state (revisits bounce to the dashboard).
   `cabinet-shell` testid moved to the layout so guards/tests hold on every
   cabinet route.

## Tests

- **Backend: 169 passed** (3 new pricing tests).
- **Vitest: 53 passed** (8 new): pricing calculator (seats × live price,
  clamping, no negative totals) and landing locale catalogs (uz default
  copy, ru/en key-parity, `{days}` placeholder, onboarding strings).
- **Playwright: 21 passed / 8 by-design skips** —
  - **full funnel**: landing opens in UZ → live price 50 000 renders →
    slider to 10 seats recomputes 500 000 → switch to RU (hero re-renders) →
    register fresh company → onboarding checklist → add operator
    (credentials dialog) → license tab shows 1 seat + **trial countdown
    («Осталось дней: ~14»)** → onboarding step 1 «Готово» → dismiss persists;
  - **pricing change**: PricingSetting → 75 000 via backend + cache
    invalidation (TTL expiry simulated) → landing shows 75 000 after reload;
    restored to 50 000 after.
  - Mutation tests (seat math, global pricing) are desktop-project-scoped —
    running them per-viewport raced each other on the shared seeded company.
- `make lint` exit 0 · `make test` exit 0.

## Visual evidence

`docs/screenshots/phase8-landing-uz.png` — UZ hero with teal glow, display
type, CSS product frame, «Qanday ishlaydi» steps with oversized numerals.

## Fixes discovered by tests

- Next dev proxy lacked `/api/public/*` → landing silently fell back to the
  default price; added rewrite + made the Django route slash-optional (Next
  strips trailing slashes, Django appends — redirect loop otherwise).

## Notes / carry-over

- APK download is a placeholder link — the artifact + distribution page is
  Phase 9 scope.
- OG image uses the runtime generator; a designed static asset can replace
  it later without code changes.
- Master spec §7/§9 still absent — funnel and art direction executed from
  the task message.
