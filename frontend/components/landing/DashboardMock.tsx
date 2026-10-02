/** Landing hero art: a faithful, static, CSS-only replica of the cabinet
 * "Ish stoli" (dashboard) page — sidebar, period tabs, KPI cards, the two
 * charts and the latest-calls list — using the real design tokens so it
 * looks exactly like what the customer gets after signing up. Server
 * component (no hooks); labels come from the landing locale's messages. */

import {
  ArrowDownLeft,
  ArrowUpRight,
  BarChart3,
  Contact2,
  LayoutDashboard,
  Phone,
  PhoneCall,
  Play,
  Settings,
} from "lucide-react";

import { cn } from "@/lib/utils";

export interface DashboardMockLabels {
  nav: { dashboard: string; calls: string; contacts: string; reports: string; settings: string };
  period: { today: string; "3d": string; "7d": string };
  kTotal: string;
  answered: string;
  missed: string;
  duration: string;
  answerRate: string;
  directionChart: string;
  operatorChart: string;
  latestSuccessful: string;
  all: string;
  inbound: string;
  outbound: string;
}

// Demo numbers — deliberately "busy day" figures; percentages are consistent.
const KPI = { total: 1284, answered: 1097, missed: 187, duration: "42:17:05" };
const DIRECTIONS: Array<{ key: "all" | "inbound" | "outbound"; answered: number; missed: number }> = [
  { key: "all", answered: 1097, missed: 187 },
  { key: "inbound", answered: 612, missed: 141 },
  { key: "outbound", answered: 485, missed: 46 },
];
const OPERATORS = [
  { name: "Dilnoza", answered: 312, missed: 38 },
  { name: "Sardor", answered: 276, missed: 44 },
  { name: "Malika", answered: 231, missed: 29 },
  { name: "Jasur", answered: 178, missed: 51 },
  { name: "Nilufar", answered: 100, missed: 25 },
];
const CALLS = [
  { dir: "in", name: "Akmal Rustamov", time: "17:42", dur: "4:12" },
  { dir: "out", name: "+998 90 123 45 67", time: "17:31", dur: "1:48" },
  { dir: "in", name: "Dilshod Karimov", time: "17:19", dur: "7:05" },
  { dir: "out", name: "Sevara Yusupova", time: "17:04", dur: "2:33" },
] as const;

const NAV = [
  { key: "dashboard", icon: LayoutDashboard },
  { key: "calls", icon: PhoneCall },
  { key: "contacts", icon: Contact2 },
  { key: "reports", icon: BarChart3 },
  { key: "settings", icon: Settings },
] as const;

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "accent" | "danger" }) {
  return (
    <div className="rounded-md border border-border bg-surface px-2.5 py-2 shadow-sm">
      <p className="truncate text-[8px] font-medium uppercase tracking-wide text-fg-faint">{label}</p>
      <p className={cn("tnum mt-0.5 text-sm font-semibold leading-tight", tone === "accent" && "text-accent", tone === "danger" && "text-danger")}>
        {value}
      </p>
      {hint && <p className="truncate text-[8px] text-fg-muted">{hint}</p>}
    </div>
  );
}

export function DashboardMock({ labels }: { labels: DashboardMockLabels }) {
  const maxDir = DIRECTIONS[0].answered + DIRECTIONS[0].missed;
  const maxOp = Math.max(...OPERATORS.map((o) => o.answered + o.missed));
  const rate = Math.round((KPI.answered / KPI.total) * 100);
  return (
    <div className="select-none overflow-hidden rounded-xl border border-white/10 bg-[#1b1e1d] shadow-2xl" aria-hidden>
      {/* Browser chrome */}
      <div className="flex items-center gap-1.5 px-3 py-2">
        <span className="size-2.5 rounded-full bg-white/15" />
        <span className="size-2.5 rounded-full bg-white/15" />
        <span className="size-2.5 rounded-full bg-white/15" />
        <span className="ml-3 h-4 flex-1 rounded bg-white/5 px-2 text-[9px] leading-4 text-white/40">app.doocall.uz/cabinet</span>
      </div>

      {/* The cabinet itself — light theme, real tokens */}
      <div className="grid h-[400px] grid-cols-[112px_1fr] bg-surface-2 text-fg">
        <aside className="flex flex-col border-r border-border bg-surface px-2 py-3">
          <div className="mb-3 flex items-center gap-1.5 px-1">
            <span className="grid size-5 place-items-center rounded-md bg-accent text-accent-fg">
              <Phone className="size-3" />
            </span>
            <span className="text-[11px] font-bold">dooCall</span>
          </div>
          <nav className="space-y-0.5">
            {NAV.map(({ key, icon: Icon }, index) => (
              <div
                key={key}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[9px] font-medium",
                  index === 0 ? "bg-accent-soft text-accent" : "text-fg-muted",
                )}
              >
                <Icon className="size-3 shrink-0" />
                <span className="truncate">{labels.nav[key]}</span>
              </div>
            ))}
          </nav>
          <div className="mt-auto flex items-center gap-1.5 rounded-md border border-border px-2 py-1.5">
            <span className="grid size-4 place-items-center rounded-full bg-accent/20 text-[8px] font-bold text-accent">A</span>
            <span className="truncate text-[8px] text-fg-muted">admin@firma.uz</span>
          </div>
        </aside>

        <main className="min-w-0 space-y-2 overflow-hidden p-2.5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold">{labels.nav.dashboard}</p>
            <div className="flex gap-1">
              {(["today", "3d", "7d"] as const).map((p, i) => (
                <span
                  key={p}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[8px] font-medium",
                    i === 0 ? "bg-accent text-accent-fg" : "border border-border text-fg-muted",
                  )}
                >
                  {labels.period[p]}
                </span>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-4 gap-1.5">
            <Kpi label={labels.kTotal} value={KPI.total.toLocaleString("ru-RU")} />
            <Kpi label={labels.answered} value={KPI.answered.toLocaleString("ru-RU")} hint={`${rate}% ${labels.answerRate}`} tone="accent" />
            <Kpi label={labels.missed} value={String(KPI.missed)} tone="danger" />
            <Kpi label={labels.duration} value={KPI.duration} />
          </div>

          <div className="grid grid-cols-2 gap-1.5">
            {/* Direction: stacked horizontal bars */}
            <div className="rounded-md border border-border bg-surface p-2">
              <p className="mb-1.5 text-[9px] font-semibold">{labels.directionChart}</p>
              <div className="space-y-1.5">
                {DIRECTIONS.map((d) => {
                  const total = d.answered + d.missed;
                  return (
                    <div key={d.key} className="flex items-center gap-1.5">
                      <span className="w-12 shrink-0 truncate text-[8px] text-fg-muted">{labels[d.key]}</span>
                      <div className="flex h-2.5 flex-1 overflow-hidden rounded-r">
                        <div className="bg-accent" style={{ width: `${(d.answered / maxDir) * 100}%` }} />
                        <div className="bg-danger-500/80" style={{ width: `${(d.missed / maxDir) * 100}%` }} />
                      </div>
                      <span className="tnum w-7 shrink-0 text-right text-[8px] text-fg-muted">{total}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Operators: stacked columns */}
            <div className="rounded-md border border-border bg-surface p-2">
              <p className="mb-1.5 text-[9px] font-semibold">{labels.operatorChart}</p>
              <div className="flex h-[52px] items-end gap-1.5">
                {OPERATORS.map((o) => {
                  const total = o.answered + o.missed;
                  return (
                    <div key={o.name} className="flex flex-1 flex-col items-center gap-0.5">
                      <div className="flex w-full flex-col-reverse overflow-hidden rounded-t" style={{ height: `${(total / maxOp) * 40}px` }}>
                        <div className="w-full bg-accent" style={{ height: `${(o.answered / total) * 100}%` }} />
                        <div className="w-full bg-danger-500/80" style={{ height: `${(o.missed / total) * 100}%` }} />
                      </div>
                      <span className="truncate text-[7px] text-fg-muted">{o.name}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Latest successful calls */}
          <div className="rounded-md border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border px-2 py-1">
              <p className="text-[9px] font-semibold">{labels.latestSuccessful}</p>
              <span className="text-[8px] font-medium text-accent">→</span>
            </div>
            <ul className="divide-y divide-border">
              {CALLS.map((c) => (
                <li key={c.name + c.time} className="flex items-center gap-1.5 px-2 py-1 text-[9px]">
                  {c.dir === "in" ? (
                    <ArrowDownLeft className="size-2.5 text-accent" />
                  ) : (
                    <ArrowUpRight className="size-2.5 text-fg-muted" />
                  )}
                  <span className="tnum min-w-0 flex-1 truncate">{c.name}</span>
                  <span className="tnum text-[8px] text-fg-muted">{c.time}</span>
                  <span className="tnum w-6 text-right text-[8px] text-fg-muted">{c.dur}</span>
                  <span className="grid size-3.5 place-items-center rounded-full bg-accent-soft text-accent">
                    <Play className="size-2 fill-current" />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </main>
      </div>
    </div>
  );
}
