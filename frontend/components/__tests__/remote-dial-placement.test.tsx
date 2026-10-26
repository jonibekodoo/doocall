/** Remote Dial button placement: Calls rows and contact phones (one shared
 * device request), hidden when the user has no devices. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import CallsPage from "@/app/cabinet/calls/page";
import ContactCardPage from "@/app/cabinet/contacts/[id]/page";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/calls",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "5" }),
}));

const DEVICE = {
  device_id: "dev-a",
  operator: { id: 3, full_name: "Aziza" },
  model: "TECNO",
  online: true,
  last_seen: null,
};
const ROW = {
  id: 1,
  call_id: "c",
  direction: "inbound",
  status: "answered",
  operator_id: 3,
  operator_name: "Aziza",
  operator_number: "",
  counterparty_number: "+998901234567",
  counterparty_name: null,
  duration: 60,
  start_time: "2026-10-26T09:15:00+05:00",
  has_location: false,
  crm: [],
  ai: null,
};

function stubApi(devices: unknown[]) {
  const deviceCalls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split("?")[0];
      if (path.endsWith("/dial/devices")) {
        deviceCalls.push(path);
        return new Response(JSON.stringify(devices));
      }
      if (path.endsWith("/calls")) {
        return new Response(
          JSON.stringify({
            success: true,
            count: 2,
            page: 1,
            pages: 1,
            page_size: 20,
            results: [ROW, { ...ROW, id: 2, counterparty_name: "Dastan" }],
          }),
        );
      }
      if (path.endsWith("/contacts/5")) {
        return new Response(
          JSON.stringify({
            success: true,
            contact: {
              id: 5,
              name: "Dastan",
              note: "",
              phones: ["+998901234567", "+998935554433"],
            },
            calls: [],
          }),
        );
      }
      return new Response(JSON.stringify({ success: true, report: [] }));
    }),
  );
  return deviceCalls;
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

afterEach(() => vi.unstubAllGlobals());

describe("Remote Dial placement", () => {
  it("Calls rows get a dial button (one devices request) that opens the modal", async () => {
    const deviceCalls = stubApi([DEVICE]);
    renderUi(<CallsPage />);
    await waitFor(() =>
      expect(screen.getAllByTestId("remote-dial")).toHaveLength(2),
    );
    expect(deviceCalls).toHaveLength(1);

    await userEvent.setup().click(screen.getAllByTestId("remote-dial")[0]);
    const modal = await screen.findByTestId("dial-modal");
    expect(within(modal).getByTestId("dial-number")).toHaveValue(
      "+998 90 123-45-67",
    );
  });

  it("contact phones each get a dial button", async () => {
    stubApi([DEVICE]);
    renderUi(<ContactCardPage />);
    await waitFor(() =>
      expect(screen.getAllByTestId("remote-dial")).toHaveLength(2),
    );
  });

  it("no devices → no dial buttons", async () => {
    stubApi([]);
    renderUi(<CallsPage />);
    expect(await screen.findAllByText("+998 90 123-45-67")).not.toHaveLength(0);
    await waitFor(() =>
      expect(screen.queryByTestId("remote-dial")).not.toBeInTheDocument(),
    );
  });
});
