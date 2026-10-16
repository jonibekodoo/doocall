/** Reports page filter: presets in the company time zone (frozen clock), the
 * params every report fetcher receives, URL persistence and tab switching. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ReportsPage from "@/app/cabinet/reports/page";
import uz from "@/messages/uz.json";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/reports",
  useRouter: () => ({ replace: nav.replace, refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
  useParams: () => ({}),
}));

// 20:30 UTC on Oct 16 is already 01:30 on Oct 17 in Tashkent (UTC+5).
const NOW = new Date("2026-10-16T20:30:00Z");

function stubApi({ timezone = "Asia/Tashkent" as string | null } = {}) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      const path = url.split("?")[0];
      if (path.endsWith("/settings/account")) {
        if (timezone === null) {
          return new Response(
            JSON.stringify({ success: false, message: "forbidden" }),
            {
              status: 403,
            },
          );
        }
        return new Response(
          JSON.stringify({
            success: true,
            settings: { timezone, country: "UZ" },
          }),
        );
      }
      if (path.endsWith("/reports/general")) {
        const empty = { total: 0, answered: 0, missed: 0 };
        return new Response(
          JSON.stringify({
            success: true,
            report: {
              all: empty,
              inbound: empty,
              outbound: empty,
              total_duration_sec: 0,
            },
          }),
        );
      }
      if (path.endsWith("/reports/per-employee")) {
        return new Response(
          JSON.stringify({
            success: true,
            report: [
              {
                operator_id: 3,
                user_name: "aziza",
                full_name: "Aziza Karimova",
                total: 1,
              },
              {
                operator_id: 4,
                user_name: "bobur",
                full_name: "Bobur Aliyev",
                total: 1,
              },
            ],
          }),
        );
      }
      return new Response(JSON.stringify({ success: true, report: [] }));
    }),
  );
  return urls;
}

/** Query params of the latest request to a report endpoint. */
function lastParams(urls: string[], endpoint: string): URLSearchParams | null {
  const hit = urls.filter((url) => url.split("?")[0].endsWith(endpoint)).at(-1);
  return hit ? new URL(hit, "http://x").searchParams : null;
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>
        <ReportsPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  // Recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  nav.search = "";
  nav.replace.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Reports date presets (company time zone)", () => {
  it("defaults to the last 30 days ending today in the company zone", async () => {
    const urls = stubApi();
    renderPage();
    await waitFor(() => {
      const params = lastParams(urls, "/reports/general");
      expect(params?.get("date_from")).toBe("2026-09-18");
      expect(params?.get("date_to")).toBe("2026-10-17");
    });
    expect(screen.getByTestId("preset-last30")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByTestId("report-range")).toHaveTextContent(
      "Davr: 18.09.2026 – 17.10.2026",
    );
    expect(
      screen.getByText("Standart davr — oxirgi 30 kun"),
    ).toBeInTheDocument();
    // Opening the page doesn't rewrite the URL.
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it.each([
    ["today", "2026-10-17", "2026-10-17"],
    ["yesterday", "2026-10-16", "2026-10-16"],
    ["last7", "2026-10-11", "2026-10-17"],
    ["thisMonth", "2026-10-01", "2026-10-17"],
    ["lastMonth", "2026-09-01", "2026-09-30"],
  ])("%s → %s … %s", async (preset, from, to) => {
    const urls = stubApi();
    renderPage();
    await waitFor(() =>
      expect(lastParams(urls, "/reports/general")?.get("date_to")).toBe(
        "2026-10-17",
      ),
    );
    await userEvent.setup().click(screen.getByTestId(`preset-${preset}`));
    await waitFor(() => {
      const params = lastParams(urls, "/reports/general");
      expect(params?.get("date_from")).toBe(from);
      expect(params?.get("date_to")).toBe(to);
    });
    expect(screen.getByTestId(`preset-${preset}`)).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(nav.replace).toHaveBeenLastCalledWith(
      `/cabinet/reports?date_from=${from}&date_to=${to}`,
      { scroll: false },
    );
  });

  it("'Barcha vaqt' drops the date params and is kept as range=all", async () => {
    const urls = stubApi();
    renderPage();
    await waitFor(() =>
      expect(lastParams(urls, "/reports/general")).not.toBeNull(),
    );
    await userEvent.setup().click(screen.getByTestId("preset-all"));
    await waitFor(() => {
      const params = lastParams(urls, "/reports/general");
      expect(params?.has("date_from")).toBe(false);
      expect(params?.has("date_to")).toBe(false);
    });
    expect(screen.getByTestId("report-range")).toHaveTextContent(
      "Davr: barcha vaqt",
    );
    expect(nav.replace).toHaveBeenLastCalledWith("/cabinet/reports?range=all", {
      scroll: false,
    });
  });

  it("falls back to the browser zone when company settings aren't readable", async () => {
    const urls = stubApi({ timezone: null });
    renderPage();
    const browserToday = new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(NOW);
    await waitFor(() =>
      expect(lastParams(urls, "/reports/general")?.get("date_to")).toBe(
        browserToday,
      ),
    );
  });
});

describe("Reports filter persistence", () => {
  it("restores dates, operators and tab from the URL and sends them", async () => {
    nav.search =
      "date_from=2026-08-01&date_to=2026-08-31&employees=3,4&tab=weekday";
    const urls = stubApi();
    renderPage();
    await waitFor(() => {
      const params = lastParams(urls, "/reports/weekday-matrix");
      expect(params?.get("date_from")).toBe("2026-08-01");
      expect(params?.get("date_to")).toBe("2026-08-31");
      expect(params?.get("employees")).toBe("3,4");
    });
    expect(screen.getByTestId("report-range")).toHaveTextContent(
      "Davr: 01.08.2026 – 31.08.2026",
    );
    expect(await screen.findAllByTestId("card-range")).not.toHaveLength(0);
    expect(screen.getAllByTestId("card-range")[0]).toHaveTextContent(
      "01.08.2026 – 31.08.2026",
    );
    expect(screen.getByText(/Operatorlar: 2/)).toBeInTheDocument();
    // No preset matches a custom range.
    expect(
      screen.queryByRole("button", { pressed: true }),
    ).not.toBeInTheDocument();
  });

  it("selecting operators refetches and writes employees to the URL", async () => {
    const urls = stubApi();
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("filter-operator-4"));
    await user.click(screen.getByTestId("filter-operator-3"));
    await waitFor(() =>
      expect(lastParams(urls, "/reports/general")?.get("employees")).toBe(
        "3,4",
      ),
    );
    expect(nav.replace).toHaveBeenLastCalledWith(
      "/cabinet/reports?employees=3%2C4",
      {
        scroll: false,
      },
    );
    await user.click(screen.getByTestId("filter-operators-clear"));
    await waitFor(() =>
      expect(lastParams(urls, "/reports/general")?.has("employees")).toBe(
        false,
      ),
    );
  });

  it("switching tabs keeps the filter and records the tab", async () => {
    const urls = stubApi();
    renderPage();
    const user = userEvent.setup();
    await waitFor(() =>
      expect(lastParams(urls, "/reports/general")).not.toBeNull(),
    );
    await user.click(screen.getByTestId("preset-last7"));

    await user.click(
      screen.getByText(/Davrlar bo'yicha/, { selector: "summary" }),
    );
    await user.click(screen.getByTestId("tab-period"));

    await waitFor(() => {
      const params = lastParams(urls, "/reports/period-counts");
      expect(params?.get("group")).toBe("day");
      expect(params?.get("date_from")).toBe("2026-10-11");
      expect(params?.get("date_to")).toBe("2026-10-17");
    });
    expect(screen.getByTestId("preset-last7")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(nav.replace).toHaveBeenLastCalledWith(
      "/cabinet/reports?date_from=2026-10-11&date_to=2026-10-17&tab=period",
      { scroll: false },
    );
  });

  it("a manual date edit is sent as-is", async () => {
    const urls = stubApi();
    renderPage();
    await waitFor(() =>
      expect(lastParams(urls, "/reports/general")).not.toBeNull(),
    );
    const from = screen.getByTestId("filter-from");
    // Native date inputs: set the value the way a picker would.
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(from, { target: { value: "2026-10-05" } });
    await waitFor(() => {
      const params = lastParams(urls, "/reports/general");
      expect(params?.get("date_from")).toBe("2026-10-05");
      expect(params?.get("date_to")).toBe("2026-10-17");
    });
  });
});
