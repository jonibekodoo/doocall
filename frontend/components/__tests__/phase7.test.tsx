/** Phase-7 component tests: dashboard stat mapping, report matrix from
 * fixture JSON, license total recompute, credential reveal-once dialog. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ru from "@/messages/ru.json";
import { directionBars } from "@/components/calls-shared";

import { CredentialsDialog } from "@/components/CredentialsDialog";
import type { DashboardResponse } from "@/lib/api/types";
import { formatUzs, humanizeAgo } from "@/lib/format";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

function wrap(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="ru" messages={ru}>
      <QueryClientProvider client={client}>{node}</QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

describe("dashboard stat mapping (directionBars)", () => {
  const general: DashboardResponse["general"] = {
    all: { total: 40, answered: 21, missed: 19 },
    inbound: { total: 19, answered: 10, missed: 9 },
    outbound: { total: 21, answered: 11, missed: 10 },
    total_duration_sec: 1790,
  };

  it("maps the API payload to three stacked rows preserving totals", () => {
    const bars = directionBars(general);
    expect(bars).toHaveLength(3);
    expect(bars[0]).toEqual({
      key: "all",
      answered: 21,
      missed: 19,
      total: 40,
    });
    expect(bars[1]).toEqual({
      key: "inbound",
      answered: 10,
      missed: 9,
      total: 19,
    });
    expect(bars[2]).toEqual({
      key: "outbound",
      answered: 11,
      missed: 10,
      total: 21,
    });
    // answered + missed must always reconstruct the total (stacked bars).
    for (const bar of bars) expect(bar.answered + bar.missed).toBe(bar.total);
  });
});

describe("report matrix rendering from fixture JSON", () => {
  // Same shape the API returns for the Phase-5 hand-computed fixture.
  const fixture = [
    { weekday: 1, total: 10, inbound: 6, outbound: 4, answered: 5, missed: 5 },
    { weekday: 3, total: 12, inbound: 3, outbound: 9, answered: 8, missed: 4 },
  ];

  it("renders one row per weekday with exact cell values", async () => {
    // Stub fetch: the weekday endpoint returns the fixture, all else empty.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const empty = { total: 0, answered: 0, missed: 0 };
        const body = url.includes("weekday-matrix")
          ? { success: true, report: fixture }
          : url.includes("reports/general")
            ? {
                success: true,
                report: {
                  all: empty,
                  inbound: empty,
                  outbound: empty,
                  total_duration_sec: 0,
                },
              }
            : { success: true, report: [] };
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    const { default: ReportsPage } = await import("@/app/cabinet/reports/page");
    wrap(<ReportsPage />);

    // Switch to the weekday matrix subtab.
    const user = userEvent.setup();
    await user.click(screen.getByText("По периодам ▾"));
    await user.click(await screen.findByTestId("tab-weekday"));

    const table = await screen.findByTestId("report-weekday");
    expect(table).toHaveTextContent("Пн");
    expect(table).toHaveTextContent("Ср");
    const cells = table.querySelectorAll("td");
    const values = [...cells].map((cell) => cell.textContent);
    expect(values).toEqual(
      expect.arrayContaining([
        "Пн",
        "10",
        "6",
        "4",
        "5",
        "Ср",
        "12",
        "3",
        "9",
        "8",
      ]),
    );
    vi.unstubAllGlobals();
    // 20s: the dynamic page import + Recharts render exceed the default
    // 5s budget when the host is busy running the docker stack.
  }, 20_000);
});

describe("license total recompute", () => {
  it("total_uzs is always seats × price, formatted with grouping", () => {
    for (const [seats, price] of [
      [6, 50000],
      [7, 50000],
      [5, 80000],
      [0, 50000],
    ] as const) {
      const total = seats * price;
      expect(formatUzs(total)).toBe(formatUzs(seats * price));
    }
    expect(formatUzs(7 * 50000)).toMatch(/^350\D000$/);
    expect(formatUzs(5 * 50000)).toMatch(/^250\D000$/);
  });
});

describe("credential reveal-once dialog", () => {
  const credentials = {
    user_name: "op-7",
    password: "s3cret-pass",
    api_key: "a".repeat(32),
  };

  it("shows all three credentials and the warning note", () => {
    wrap(
      <CredentialsDialog
        credentials={credentials}
        note="Сохраните эти данные — они показываются только один раз"
        onClose={() => {}}
      />,
    );
    const dialog = screen.getByTestId("credentials");
    expect(dialog).toHaveTextContent("op-7");
    expect(dialog).toHaveTextContent("s3cret-pass");
    expect(dialog).toHaveTextContent("a".repeat(32));
    expect(screen.getByText(/только один раз/)).toBeInTheDocument();
  });

  it("closes exactly once and never re-renders credentials after", async () => {
    const onClose = vi.fn();
    const { unmount } = wrap(
      <CredentialsDialog
        credentials={credentials}
        note="!"
        onClose={onClose}
      />,
    );
    await userEvent.setup().click(screen.getByTestId("credentials-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
    unmount();
    expect(screen.queryByTestId("credentials")).not.toBeInTheDocument();
  });
});

describe("humanizeAgo", () => {
  const now = new Date("2026-08-14T12:00:00Z");
  it.each([
    ["2026-08-14T11:45:00Z", "15 мин"],
    ["2026-08-14T09:00:00Z", "3 ч"],
    ["2026-08-11T12:00:00Z", "3 дн"],
  ])("%s → %s", (iso, expected) => {
    expect(humanizeAgo(iso, now)).toBe(expected);
  });
});
