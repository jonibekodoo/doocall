/** Missed (inbound unanswered) vs not reached (outbound unanswered): the
 * shared helper, the badge, the Calls status filter and the dashboard KPIs. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CabinetHome from "@/app/cabinet/page";
import CallsPage from "@/app/cabinet/calls/page";
import { CallStatusBadge } from "@/components/calls-shared";
import {
  callOutcome,
  splitByDirection,
  splitUnanswered,
} from "@/lib/call-status";
import en from "@/messages/en.json";
import ru from "@/messages/ru.json";
import uz from "@/messages/uz.json";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/calls",
  useRouter: () => ({ replace: nav.replace, refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
  useParams: () => ({}),
}));

beforeEach(() => {
  nav.search = "";
  nav.replace.mockReset();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("callOutcome", () => {
  it.each([
    ["answered", "inbound", "answered"],
    ["answered", "outbound", "answered"],
    ["no_answer", "inbound", "missed"],
    ["no_answer", "outbound", "not_reached"],
    ["busy", "inbound", "missed"],
    ["failed", "outbound", "not_reached"],
    ["no_answer", "internal", "not_reached"],
  ])("%s + %s → %s", (status, direction, outcome) => {
    expect(callOutcome(status, direction)).toBe(outcome);
  });
});

describe("splitUnanswered / splitByDirection", () => {
  it("uses the new fields when present", () => {
    expect(
      splitUnanswered({ missed: 9, missed_inbound: 4, not_reached: 5 }),
    ).toEqual({
      missed: 4,
      notReached: 5,
    });
    expect(splitUnanswered({ missed: 9, not_reached: 5 })).toEqual({
      missed: 0,
      notReached: 5,
    });
  });

  it("falls back to the legacy total with not-reached unknown", () => {
    expect(splitUnanswered({ missed: 9 })).toEqual({
      missed: 9,
      notReached: null,
    });
  });

  it("derives an exact split from inbound/outbound without the new fields", () => {
    const block = {
      all: { missed: 19 },
      inbound: { missed: 9 },
      outbound: { missed: 10 },
    };
    expect(splitByDirection(block)).toEqual({ missed: 9, notReached: 10 });
    expect(
      splitByDirection({
        ...block,
        all: { missed: 19, missed_inbound: 7, not_reached: 12 },
      }),
    ).toEqual({ missed: 7, notReached: 12 });
  });
});

describe("CallStatusBadge", () => {
  it.each([
    ["uz", uz, "Javob berilgan", "O'tkazib yuborilgan", "Javob bermadi"],
    ["ru", ru, "Отвечен", "Пропущен", "Не дозвонился"],
    ["en", en, "Answered", "Missed", "No answer"],
  ] as const)(
    "labels in %s",
    (locale, messages, answered, missed, notReached) => {
      render(
        <NextIntlClientProvider locale={locale} messages={messages}>
          <CallStatusBadge status="answered" direction="outbound" />
          <CallStatusBadge status="no_answer" direction="inbound" />
          <CallStatusBadge status="no_answer" direction="outbound" />
        </NextIntlClientProvider>,
      );
      const [a, m, n] = screen.getAllByTestId("call-status");
      expect(a).toHaveTextContent(answered);
      expect(a).toHaveAttribute("data-outcome", "answered");
      expect(m).toHaveTextContent(missed);
      expect(m).toHaveClass("text-danger");
      expect(n).toHaveTextContent(notReached);
      expect(n).toHaveAttribute("data-outcome", "not_reached");
      expect(n).toHaveClass("text-warning");
    },
  );
});

const ROW = {
  call_id: "c",
  status: "no_answer",
  operator_id: 3,
  operator_name: "Aziza",
  operator_number: "",
  counterparty_number: "+998901234567",
  counterparty_name: null,
  duration: 0,
  start_time: "2026-10-27T09:15:00+05:00",
  has_location: false,
  crm: [],
  ai: null,
};

function stubCalls() {
  const lists: URLSearchParams[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.split("?")[0];
      if (path.endsWith("/calls")) {
        lists.push(new URL(url, "http://x").searchParams);
        return new Response(
          JSON.stringify({
            success: true,
            count: 2,
            page: 1,
            pages: 1,
            page_size: 20,
            results: [
              { ...ROW, id: 1, direction: "inbound" },
              { ...ROW, id: 2, direction: "outbound" },
            ],
          }),
        );
      }
      return new Response(JSON.stringify({ success: true, report: [] }));
    }),
  );
  return lists;
}

function renderUi(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>{node}</QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

describe("Calls page", () => {
  it("labels inbound no-answer as missed and outbound as not reached", async () => {
    stubCalls();
    renderUi(<CallsPage />);
    await waitFor(() =>
      expect(screen.getAllByTestId("call-status")).toHaveLength(2),
    );
    const [inbound, outbound] = screen.getAllByTestId("call-status");
    expect(inbound).toHaveTextContent("O'tkazib yuborilgan");
    expect(outbound).toHaveTextContent("Javob bermadi");
  });

  it("status filter: separate missed / not reached options, sent and kept in the URL", async () => {
    const lists = stubCalls();
    renderUi(<CallsPage />);
    const status = await screen.findByRole("combobox", { name: "Holat" });
    const options = within(status)
      .getAllByRole("option")
      .map((option) => [option.getAttribute("value"), option.textContent]);
    expect(options).toEqual(
      expect.arrayContaining([
        ["answered", "Javob berilgan"],
        ["missed", "O'tkazib yuborilgan (kiruvchi)"],
        ["not_reached", "Javob bermadi (chiquvchi)"],
      ]),
    );

    await userEvent.setup().selectOptions(status, "not_reached");
    await waitFor(() =>
      expect(lists.at(-1)?.get("status")).toBe("not_reached"),
    );
    expect(nav.replace).toHaveBeenLastCalledWith(
      "/cabinet/calls?status=not_reached",
      {
        scroll: false,
      },
    );
  });

  it("restores status=missed from the URL", async () => {
    nav.search = "status=missed";
    const lists = stubCalls();
    renderUi(<CallsPage />);
    await waitFor(() => expect(lists.length).toBeGreaterThan(0));
    expect(lists[0].get("status")).toBe("missed");
    expect(screen.getByRole("combobox", { name: "Holat" })).toHaveValue(
      "missed",
    );
  });
});

function stubDashboard(general: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split("?")[0];
      if (path.endsWith("/dashboard")) {
        return new Response(
          JSON.stringify({
            success: true,
            period: "today",
            general: { total_duration_sec: 0, ...general },
            per_operator: [],
            latest_calls: [],
            unanswered_now: [],
          }),
        );
      }
      return new Response(
        JSON.stringify({ success: true, report: [], devices: [] }),
      );
    }),
  );
}

describe("Dashboard KPIs", () => {
  const legacy = {
    all: { total: 40, answered: 21, missed: 19 },
    inbound: { total: 19, answered: 10, missed: 9 },
    outbound: { total: 21, answered: 11, missed: 10 },
  };

  const tile = (label: string) =>
    screen.getAllByText(label, { selector: "p" })[0].parentElement!;

  it("splits missed (inbound) and not reached (outbound) from the legacy payload", async () => {
    stubDashboard(legacy);
    renderUi(<CabinetHome />);
    await screen.findByTestId("dashboard-page");
    await waitFor(() =>
      expect(tile("O'tkazib yuborilgan")).toHaveTextContent("9"),
    );
    expect(tile("Javob bermadi")).toHaveTextContent("10");
  });

  it("prefers missed_inbound / not_reached when the backend sends them", async () => {
    stubDashboard({
      ...legacy,
      all: { ...legacy.all, missed_inbound: 7, not_reached: 12 },
    });
    renderUi(<CabinetHome />);
    await waitFor(() =>
      expect(tile("O'tkazib yuborilgan")).toHaveTextContent("7"),
    );
    expect(tile("Javob bermadi")).toHaveTextContent("12");
  });
});
