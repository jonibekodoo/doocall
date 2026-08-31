# PHASE 7 — Cabinet screens (completed)

## Phase 6 verification (session start)

`make test` green (166 backend + 37 frontend). `seed_demo` extended with a
web admin (`admin@ahlan.uz` / demo1234, company admin) so the authenticated
shell and E2E run against the seeded backend — verified by live login.

## Delivered (all screens wired to the Phase-5 API, with skeletons, empty
states and error toasts)

1. **Рабочий стол (§6.1)** — Сегодня/3 дня/7 дней tabs; horizontal stacked
   bars Все/Входящие/Исходящие (answered teal vs missed red, total labels);
   per-operator stacked columns sorted desc with name+total labels; two
   mini-tables — последние успешные / текущие неотвеченные (light-red rows)
   — with operator filter, direction icons, inline audio play and «полный
   отчет» links.
2. **Звонки (§6.2)** — full FilterBar (employees, date range default 30d,
   direction, status, name/phone search, min duration, SIM, **Применить**
   staged-apply); paginated DataTable «1—30 из N»; sortable date/duration;
   direction icons; status chips; contact link or create-from-call action;
   `CallAudioButton` lazily fetches the call detail and streams the **real
   presigned URL** (mock removed from the flow); download in player;
   admin delete with confirm; column-settings gear persisted; **CSV/XLSX
   export with task-progress toast** polling `/calls/export/<id>` and
   opening the download link.
3. **Контакты (§6.3)** — search + «+ Новый контакт»; table
   Имя/Должность/Телефон/Ответственный; styled empty state; create/edit
   dialogs with **zod** validation (multi-phone, dedup via backend);
   contact card page (`/cabinet/contacts/[id]`) with call history +
   playback; **create-from-call** flow (`?fromCall=<id>`) auto-creates,
   links history, and back-fills names.
4. **Отчеты (§6.4)** — tab bar with dropdown submenus: Общая статистика
   (three summary columns, green/red rows, HH:MM:SS total); По периодам →
   weekday matrix table + period bar chart with value labels and
   **Уникальные** checkbox (day/week/month); По сотрудникам → donut
   distribution, answered/missed stacked columns, duration-minutes columns
   with rounding note; По клиентам → distribution table with "No data"
   empty state, **Неотвеченные вызовы** («Как давно» humanized, «С
   контактом» checkbox, pagination, red tint), Последний контакт with play
   buttons (backend now returns `call_record_id`) and red tint on missed.
5. **Настройки (§6.5)** — six tabs: users&groups (**credential reveal-once
   dialog** with copy buttons, deactivate toggle, seat-billing note, groups
   chips); devices (cards with online badge, per-SIM number set +
   Записывать toggle, delete with confirm); calls&SMS (recording toggle,
   filters modal stub, SMS templates stub); integration (API-key masked
   view + rotate-shown-once, webhook URL + secret-shown-once + test
   delivery); account (contact import / PIN toggles); license&payment
   (trial countdown OR period dates, **live seats × price = total**,
   payment history, Оплатить buttons per provider).
6. **Мои звонки (§6.6)** — operator-scoped table without admin actions.

Refactors: shared `DirectionIcon`/`directionBars` → `components/
calls-shared.tsx`, `CredentialsDialog` → own component, `humanizeAgo` →
`lib/format.ts` (Next.js page files must not export extras — caught by the
container typecheck).

## Tests

- **Vitest: 45 passed** (8 new Phase-7): dashboard stat mapping (stacked
  invariant answered+missed=total), weekday matrix rendered from fixture
  JSON with exact cell values (fetch stubbed), license total recompute,
  credential reveal-once dialog (contents + closes-once + gone after
  unmount), humanizeAgo table.
- **Playwright E2E: 6 passed** against the seeded stack:
  1. login → dashboard renders seeded numbers, period tabs switch, **zero
     console errors** (only the by-design anonymous refresh 401 excluded);
  2. calls: 30d default «1—30 из N», answered filter applied, audio
     interaction, no error alerts;
  3. create contact from call → contact appears in the table;
  4. **every report submenu** opens and renders seeded data (incl. operator
     name in the donut and humanized «Как давно»);
  5. settings: **add operator → license seats +1; deactivate → back down**
     — the full seat-billing loop through the real API;
  6. dark theme toggle + screenshot.
- `make lint` exit 0 (ruff+mypy backend · ESLint+Prettier+tsc frontend).
- `make test` exit 0 (166 backend + 45 frontend).

## Visual evidence

- `docs/screenshots/phase7-dark.png` — dark-theme dashboard with live
  seeded data (stacked bars, operator columns, both tables) — spot-checked.
- E2E failure screenshots reviewed during development confirmed the light
  theme calls screen (filters, chips, play buttons) renders correctly.

## Notes / carry-over

- Seeded calls carry no audio files, so E2E exercises the presigned-URL
  fetch path up to "no audio → control hides"; a real end-to-end stream
  plays whenever a call has audio (mobile upload with audio_file).
- Оплатить buttons toast provider choice; the actual Payme/Click checkout
  redirect lands with real merchant credentials (Phase 9 scope).
- Column prefs persist locally; server sync via `/calls/columns` remains a
  small follow-up.
- Master spec §6.1–§6.6 still absent — screens built from the task
  message's widget/filter/column list.
