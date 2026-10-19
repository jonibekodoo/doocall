/** Calls page live filtering: controls apply at once, search is debounced,
 * page resets to 1, "Filtrni tozalash" restores defaults, URL persistence
 * (incl. the ?call= deep link) and exports use the live filters. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CallsPage from "@/app/cabinet/calls/page";
import uz from "@/messages/uz.json";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/calls",
  useRouter: () => ({ replace: nav.replace, refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
  useParams: () => ({}),
}));

function isoDaysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}
const DEFAULT_FROM = isoDaysAgo(30);
const DEFAULT_TO = isoDaysAgo(0);

const ROW = {
  id: 1,
  call_id: "c",
  direction: "inbound",
  status: "answered",
  operator_id: 3,
  operator_name: "Aziza",
  operator_number: "",
  counterparty_number: "+998901234567",
  counterparty_name: "Dastan",
  duration: 60,
  start_time: "2026-10-18T09:15:00+05:00",
  has_location: false,
  crm: [],
  ai: null,
};

function stubApi() {
  const lists: URLSearchParams[] = [];
  const exports: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const path = url.split("?")[0];
      if (path.endsWith("/calls/export") && init.method === "POST") {
        exports.push(JSON.parse(String(init.body)));
        return new Response(JSON.stringify({ success: true, export_id: 5 }));
      }
      if (path.endsWith("/calls")) {
        lists.push(new URL(url, "http://x").searchParams);
        return new Response(
          JSON.stringify({
            success: true,
            count: 45,
            page: 1,
            pages: 3,
            page_size: 20,
            results: [ROW],
          }),
        );
      }
      if (path.endsWith("/reports/per-employee")) {
        return new Response(
          JSON.stringify({
            success: true,
            report: [
              { operator_id: 3, user_name: "aziza", full_name: "Aziza" },
            ],
          }),
        );
      }
      return new Response(JSON.stringify({ success: true, report: [] }));
    }),
  );
  return { lists, exports };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>
        <CallsPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const last = (lists: URLSearchParams[]) => lists[lists.length - 1];
const searchBox = () => screen.getByRole("searchbox");
const select = (label: string) => screen.getByRole("combobox", { name: label });

beforeEach(() => {
  nav.search = "";
  nav.replace.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Calls live filters", () => {
  it("search is debounced: one request after the pause, none per keystroke", async () => {
    const { lists } = stubApi();
    renderPage();
    await waitFor(() => expect(lists.length).toBeGreaterThan(0));
    await screen.findByText("Dastan");
    const before = lists.length;

    // Fake timers only for the typing + debounce window.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    // Three keystrokes (userEvent's own waits don't mix with fake timers).
    for (const value of ["d", "da", "das"]) {
      fireEvent.change(searchBox(), { target: { value } });
      await act(() => vi.advanceTimersByTimeAsync(100));
    }
    await act(() => vi.advanceTimersByTimeAsync(299)); // 100 + 299 = 399 ms
    expect(lists.length).toBe(before); // 399 ms after the last keystroke

    await act(() => vi.advanceTimersByTimeAsync(1));
    await act(() => vi.advanceTimersByTimeAsync(50)); // let the query fire
    expect(lists.length).toBe(before + 1);
    expect(last(lists).get("search")).toBe("das");
    expect(
      lists.some((params) => ["d", "da"].includes(params.get("search") ?? "")),
    ).toBe(false);
    expect(nav.replace).toHaveBeenLastCalledWith("/cabinet/calls?search=das", {
      scroll: false,
    });
  });

  it("Enter searches immediately", async () => {
    const { lists } = stubApi();
    renderPage();
    await waitFor(() => expect(lists.length).toBeGreaterThan(0));
    await userEvent.setup().type(searchBox(), "dastan{Enter}");
    // Right away — no need to wait for the 400 ms pause.
    await waitFor(() => expect(last(lists).get("search")).toBe("dastan"), {
      timeout: 300,
    });
  });

  it("a select change fetches at once and resets to page 1", async () => {
    const { lists } = stubApi();
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Dastan");

    await user.click(screen.getByRole("button", { name: "next" }));
    await waitFor(() => expect(last(lists).get("page")).toBe("2"));

    await user.selectOptions(select("Yo'nalish"), "inbound");
    await waitFor(() => expect(last(lists).get("direction")).toBe("inbound"));
    expect(last(lists).has("page")).toBe(false); // back on page 1
    expect(last(lists).get("date_from")).toBe(DEFAULT_FROM);
    expect(screen.queryByTestId("apply-filters")).not.toBeInTheDocument();
    // Previous rows stay visible while the new page loads (no empty flash).
    expect(screen.getByText("Dastan")).toBeInTheDocument();
  });

  it("every control applies immediately", async () => {
    const { lists } = stubApi();
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Dastan");
    await user.selectOptions(select("Holat"), "no_answer");
    await user.selectOptions(select("SIM"), "1");
    await user.selectOptions(select("Operator"), "3");
    await user.type(screen.getByTestId("filter-min-duration"), "5");
    await waitFor(() => {
      const params = last(lists);
      expect(params.get("status")).toBe("no_answer");
      expect(params.get("sim_slot")).toBe("1");
      expect(params.get("employees")).toBe("3");
      expect(params.get("min_duration")).toBe("5");
    });
  });

  it("'Filtrni tozalash' appears only off-defaults and resets everything", async () => {
    const { lists } = stubApi();
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Dastan");
    expect(screen.queryByTestId("clear-filters")).not.toBeInTheDocument();

    await user.selectOptions(select("Yo'nalish"), "outbound");
    await user.type(searchBox(), "das{Enter}");
    await user.selectOptions(select("SIM"), "0");
    const clear = await screen.findByTestId("clear-filters");
    expect(clear).toHaveTextContent("Filtrni tozalash");

    await user.click(clear);
    await waitFor(() => {
      const params = last(lists);
      expect(params.has("direction")).toBe(false);
      expect(params.has("search")).toBe(false);
      expect(params.has("sim_slot")).toBe(false);
      expect(params.get("date_from")).toBe(DEFAULT_FROM);
      expect(params.get("date_to")).toBe(DEFAULT_TO);
    });
    expect(searchBox()).toHaveValue("");
    expect(select("Yo'nalish")).toHaveValue("");
    expect(screen.queryByTestId("clear-filters")).not.toBeInTheDocument();
    expect(nav.replace).toHaveBeenLastCalledWith("/cabinet/calls", {
      scroll: false,
    });
  });

  it("restores filters from the URL (empty date_from = no lower bound)", async () => {
    nav.search = "direction=outbound&search=das&employees=3&date_from=";
    const { lists } = stubApi();
    renderPage();
    await waitFor(() => expect(lists.length).toBeGreaterThan(0));
    const params = lists[0];
    expect(params.get("direction")).toBe("outbound");
    expect(params.get("search")).toBe("das");
    expect(params.get("employees")).toBe("3");
    expect(params.has("date_from")).toBe(false);
    expect(params.get("date_to")).toBe(DEFAULT_TO);
    expect(searchBox()).toHaveValue("das");
    expect(screen.getByTestId("clear-filters")).toBeInTheDocument();
  });

  it("keeps the ?call= deep link and the dashboard ?status= link", async () => {
    nav.search = "call=70&status=answered";
    const { lists } = stubApi();
    renderPage();
    await waitFor(() => expect(lists.length).toBeGreaterThan(0));
    expect(lists[0].get("status")).toBe("answered");
    await userEvent.setup().selectOptions(select("Yo'nalish"), "inbound");
    expect(nav.replace).toHaveBeenLastCalledWith(
      "/cabinet/calls?call=70&status=answered&direction=inbound",
      { scroll: false },
    );
  });

  it("exports use the live filters, including a search still being typed", async () => {
    const { exports } = stubApi();
    renderPage();
    const user = userEvent.setup();
    await screen.findByText("Dastan");
    await user.selectOptions(select("Yo'nalish"), "inbound");
    await user.selectOptions(select("Operator"), "3");
    await user.type(searchBox(), "das"); // export before the debounce fires
    await user.click(screen.getByRole("button", { name: /CSV/ }));

    await waitFor(() => expect(exports).toHaveLength(1));
    expect(exports[0]).toEqual({
      format: "csv",
      filters: {
        date_from: DEFAULT_FROM,
        date_to: DEFAULT_TO,
        direction: "inbound",
        employees: "3",
        search: "das",
      },
    });
  });
});
