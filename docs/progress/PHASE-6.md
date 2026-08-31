# PHASE 6 — Frontend foundation (completed)

## Phase 5 verification (session start)

`make test` green (166); live cabinet curls with a JWT for the seeded
company: dashboard (2694 calls/7d, 6 operators), per-employee report,
license (6 seats × 50 000 = 300 000 UZS). Note: no frontend-design skill is
available in this environment; §9 direction applied from the task message.

## Delivered (frontend/)

1. **Design system** — CSS-variable tokens in `app/globals.css`: deep-teal
   accent scale (#2a9691 family — deliberately not blue-500), warm-red
   danger for missed calls, warm-gray neutral scale with real hierarchy,
   radius/shadow/spacing scales; **dark theme** via `[data-theme=dark]`
   with pre-paint restore script; tokens mapped into Tailwind v4 `@theme`
   (usable as `bg-surface`, `text-accent`…); `next/font`: Inter
   (latin+cyrillic) for UI, Space Grotesk reserved for the landing; `.tnum`
   tabular-numerals utility used on all durations/phones/money.
2. **App shell** — collapsible icon+label sidebar (Рабочий стол / Звонки /
   Контакты / Отчеты / Настройки + bottom «Мои звонки»), accent active-bar
   indicator, collapse state persisted; topbar with locale switcher
   (RU/UZ/EN pills), theme toggle, user menu, period quick-filter slot;
   **≤640px the sidebar becomes a horizontal chip nav** — verified at 380px.
3. **Auth flows** — login / registration (wired to Phase-4 API, auto-login
   after register) / password reset (request + token-confirm modes);
   in-memory access token + **silent refresh via httpOnly cookie** (single
   shared refresh promise, session recovery on reload, 401→refresh→retry in
   the API client); `RequireAuth` route guard; **402 paywall screen**
   consuming the suspension payload (reason, seats × price, provider
   buttons).
4. **Data layer** — hand-typed API surface from `/api/schema/`
   (`lib/api/types.ts`), fetch client with envelope-aware `ApiError`;
   TanStack Query provider (no retry on 401/402/403, error toasts via a
   dependency-free toast store); `buildCallsQuery` filter→query-string
   builder matching backend param names exactly.
5. **i18n** — next-intl (cookie-based locale, no URL prefix): **ru primary**
   with reference terminology, uz, en; switcher in the topbar;
   date/number formatting available per locale via next-intl formatters.
6. **Primitives** — `DataTable` (sticky header, skeleton rows, density
   toggle, empty-state slot, column visibility persisted per user),
   `FilterBar`+`FilterSelect`, `DateRangePicker` (presets Сегодня/3 дня/7
   дней + custom range), `StatCard`, Recharts theme wrapper
   (**answered=accent teal, missed=warm red**, tokenized axes/tooltip),
   `AudioPlayer` (play → mini player with seek, 1×/1.5×/2×, download) built
   on a **pure reducer state machine** and running against a mock stream.
7. Dev API proxy in `next.config.ts` (`/api/* → backend`) so `:3000` works
   without nginx (used by Playwright; inert in prod).

## Tests

- **Vitest: 37 passed** — formatters (14 cases), filter builder (param-name
  exactness, omission rules), AudioPlayer machine (8 specs:
  idle/loading/playing/paused/seek-clamp/rate/ended/error/reset/no-op
  transitions), DataTable (empty/skeleton/custom-empty/data), Sidebar
  locale rendering (ru/uz/en + aria-current).
- **Playwright smoke: 4 passed, 2 skipped-by-design** (paywall fixture runs
  once): register → cabinet shell → logout → login on **1440 / 768 / 380**
  viewports; suspended-company fixture (mutated via manage.py) → paywall
  with UZS amounts.
- `tsc --noEmit` clean · ESLint clean · Prettier clean · `make lint` exit 0
  · `make test-frontend` exit 0 (containerized run, same 37).

## Screenshots (docs/screenshots/)

- `phase6-shell-desktop.png` — sidebar with active teal indicator, RU nav,
  stat cards (teal answered / red missed, tabular numerals).
- `phase6-shell-tablet.png` — same shell at 768px.
- `phase6-shell-mobile-380.png` — chip nav replaces sidebar, 2×2 cards.
- `phase6-paywall.png` — «Подписка неактивна», seats×price table, Payme/
  Click buttons.

## Notes / carry-over

- Dashboard stat labels are placeholders (`ДАТА` → should read «Всего») and
  the sidebar collapse control shows a bare glyph — Phase 7 polish items.
- AudioPlayer streams are mocked; wire presigned URLs in Phase 7 (calls
  screen) — the real `<audio>` path is already implemented behind the flag.
- Column-visibility persists to localStorage; syncing with the Phase-5
  `/calls/columns` endpoint is a Phase-7 task.
- Playwright runs against the live compose stack from the host
  (`npx playwright test` in frontend/); CI wiring for e2e is Phase 9.
