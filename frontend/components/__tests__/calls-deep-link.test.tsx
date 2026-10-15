/** Calls page deep link: /cabinet/calls?call=<id> opens that call in a drawer
 * (fetched by id, independent of the listed page) and closing drops the param. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CallsPage from "@/app/cabinet/calls/page";
import uz from "@/messages/uz.json";

const nav = vi.hoisted(() => ({
  search: "",
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/calls",
  useRouter: () => ({ replace: nav.replace, refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
  useParams: () => ({}),
}));

const BASE_ROW = {
  call_id: "c",
  direction: "inbound",
  status: "answered",
  operator_id: 3,
  operator_name: "Aziza Karimova",
  operator_number: "",
  counterparty_number: "+998901234567",
  counterparty_name: "Alisher",
  duration: 185,
  start_time: "2026-10-14T09:15:00+05:00",
  has_location: false,
  crm: [],
};

/** The list only has call 1; the deep-linked call 70 is NOT on this page. */
function stubApi({ detailStatus = 200 }: { detailStatus?: number } = {}) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      const path = url.split("?")[0];
      if (path.endsWith("/calls/70")) {
        if (detailStatus !== 200) {
          return new Response(
            JSON.stringify({
              success: false,
              error_code: "NOT_FOUND",
              message: "nf",
            }),
            { status: detailStatus },
          );
        }
        return new Response(
          JSON.stringify({
            success: true,
            call: {
              ...BASE_ROW,
              id: 70,
              ai: { analysis_id: 7, final_score: 87 },
              audios: [
                {
                  kind: "primary",
                  filename: "70.m4a",
                  size_bytes: 1000,
                  url: "https://acme.doocall.uz/media/70.m4a?sig=x",
                },
              ],
            },
          }),
        );
      }
      if (path.endsWith("/calls")) {
        return new Response(
          JSON.stringify({
            success: true,
            count: 1,
            page: 1,
            pages: 1,
            page_size: 20,
            results: [
              {
                ...BASE_ROW,
                id: 1,
                counterparty_name: "Boshqa mijoz",
                ai: null,
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

beforeEach(() => {
  nav.search = "";
  nav.replace.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe("Calls deep link", () => {
  it("?call=<id> opens the drawer with that call fetched by id", async () => {
    nav.search = "call=70";
    const urls = stubApi();
    renderPage();

    const drawer = await screen.findByTestId("call-drawer");
    expect(await within(drawer).findByText("Alisher")).toBeInTheDocument();
    expect(within(drawer).getByText("+998 90 123-45-67")).toBeInTheDocument();
    expect(within(drawer).getByText("Aziza Karimova")).toBeInTheDocument();
    expect(within(drawer).getByText("3:05")).toBeInTheDocument();
    expect(within(drawer).getByTestId("call-drawer-audio")).toBeInTheDocument();
    expect(within(drawer).getByTestId("call-ai-7")).toHaveAttribute(
      "href",
      "/cabinet/ai/7",
    );
    expect(urls.some((url) => url.split("?")[0].endsWith("/calls/70"))).toBe(
      true,
    );
    // The list itself is untouched (call 70 is not on it).
    expect(await screen.findByText("Boshqa mijoz")).toBeInTheDocument();
  });

  it("closing removes only the call param", async () => {
    nav.search = "call=70&status=answered";
    stubApi();
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("call-drawer-close"));
    expect(nav.replace).toHaveBeenCalledWith("/cabinet/calls?status=answered", {
      scroll: false,
    });
  });

  it("Escape closes the drawer too", async () => {
    nav.search = "call=70";
    stubApi();
    renderPage();
    await screen.findByTestId("call-drawer");
    await userEvent.setup().keyboard("{Escape}");
    expect(nav.replace).toHaveBeenCalledWith("/cabinet/calls", {
      scroll: false,
    });
  });

  it("an unknown call shows 'not found' instead of crashing", async () => {
    nav.search = "call=70";
    stubApi({ detailStatus: 404 });
    renderPage();
    const drawer = await screen.findByTestId("call-drawer");
    expect(
      await within(drawer).findByText("Qo'ng'iroq topilmadi"),
    ).toBeInTheDocument();
  });

  it.each(["", "call=abc", "call=0", "call=-3", "call=1.5"])(
    "no drawer for %j",
    async (search) => {
      nav.search = search;
      stubApi();
      renderPage();
      await screen.findByText("Boshqa mijoz");
      expect(screen.queryByTestId("call-drawer")).not.toBeInTheDocument();
    },
  );
});
