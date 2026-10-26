/** Bitrix24 page: operator → Bitrix24 user mapping (select / manual mode),
 * auto-match from suggestions and the saved user_map. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import Bitrix24IntegrationPage from "@/app/cabinet/settings/integrations/bitrix24/page";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/settings/integrations/bitrix24",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const OPERATORS = [
  {
    id: 3,
    full_name: "Aziza Karimova",
    user_name: "aziza",
    phones: ["+998901112233"],
  },
  { id: 4, full_name: "Bobur Aliyev", user_name: "bobur", phones: [] },
  { id: 5, full_name: "", user_name: "sardor", phones: "+998907778899" },
];
const USERS = [
  { id: "1", name: "Admin", email: "admin@acme.uz", phone: "", position: "" },
  {
    id: "7",
    name: "Aziza Karimova",
    email: "aziza@acme.uz",
    phone: "",
    position: "",
  },
  { id: 9, name: "Bobur Aliyev", email: "", phone: "", position: "Sotuvchi" },
];

function stubApi({
  configured = true,
  users = { success: true, users: USERS, operators: OPERATORS } as Record<
    string,
    unknown
  >,
  put = { status: 200, body: { success: true } } as {
    status: number;
    body: unknown;
  },
} = {}) {
  const calls: { method: string; url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const method = init.method ?? "GET";
      calls.push({
        method,
        url,
        body: init.body ? JSON.parse(String(init.body)) : undefined,
      });
      if (method === "PUT") {
        return new Response(JSON.stringify(put.body), { status: put.status });
      }
      if (url.endsWith("/bitrix24/users"))
        return new Response(JSON.stringify(users));
      if (url.includes("/deliveries")) {
        return new Response(
          JSON.stringify({
            success: true,
            deliveries: [],
            pages: 1,
            summary: { ok_30d: 0, error_30d: 0 },
          }),
        );
      }
      return new Response(
        JSON.stringify({
          success: true,
          integrations: [
            {
              provider: "bitrix24",
              is_enabled: true,
              configured,
              config: configured
                ? {
                    region: "ru",
                    account: "acme.bitrix24.ru",
                    webhook_url: "http…xyz/",
                    user_id: "1",
                    user_map: { "3": "7" },
                  }
                : {},
              last_status: "",
              last_error: "",
              last_delivery_at: null,
            },
          ],
        }),
      );
    }),
  );
  return calls;
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>
        <Bitrix24IntegrationPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const select = (id: number) =>
  screen.getByTestId(`b24-select-${id}`) as HTMLSelectElement;

afterEach(() => vi.unstubAllGlobals());

describe("Bitrix24 operator mapping", () => {
  it("relabels the default user field and hides the mapping until configured", async () => {
    stubApi({ configured: false });
    renderPage();
    expect(
      await screen.findByText(/moslanmagan operatorlar uchun \(odatda 1\)/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("b24-user-map")).not.toBeInTheDocument();
  });

  it("renders one select per operator with the saved mapping and fallback marks", async () => {
    stubApi();
    renderPage();
    await screen.findByTestId("b24-select-3");

    expect(select(3)).toHaveValue("7");
    expect(select(4)).toHaveValue("");
    expect(
      within(select(4)).getByRole("option", { name: "— Standart —" }),
    ).toBeInTheDocument();
    expect(
      within(select(4)).getByRole("option", {
        name: "Aziza Karimova · aziza@acme.uz",
      }),
    ).toBeInTheDocument();
    // Name only when there is no e-mail; numeric ids work too.
    expect(
      within(select(4)).getByRole("option", { name: "Bobur Aliyev" }),
    ).toHaveValue("9");

    const row5 = screen.getByTestId("b24-row-5");
    expect(row5).toHaveTextContent("sardor");
    expect(row5).toHaveTextContent("+998907778899");
    expect(screen.queryByTestId("b24-default-3")).not.toBeInTheDocument();
    expect(screen.getByTestId("b24-default-4")).toHaveTextContent(
      "standart ID: 1",
    );
  });

  it("auto-match fills only empty rows with known users and reports the count", async () => {
    stubApi({
      users: {
        success: true,
        users: USERS,
        operators: OPERATORS,
        // 3 is already chosen by hand; 99 is not a Bitrix24 user in the list.
        suggestions: { "3": "1", "4": "9", "5": "99" },
      },
    });
    renderPage();
    const user = userEvent.setup();
    await screen.findByTestId("b24-select-3");

    await user.click(screen.getByTestId("b24-auto-match"));

    expect(select(3)).toHaveValue("7");
    expect(select(4)).toHaveValue("9");
    expect(select(5)).toHaveValue("");
    expect(screen.getByTestId("b24-matched")).toHaveTextContent(
      "Moslandi: 1 ta operator",
    );
    expect(screen.queryByTestId("b24-default-4")).not.toBeInTheDocument();
  });

  it("falls back to number inputs with the error text when users can't be loaded", async () => {
    stubApi({
      users: {
        success: false,
        error: "insufficient_scope",
        operators: OPERATORS,
      },
    });
    renderPage();
    const user = userEvent.setup();
    const input = await screen.findByTestId("b24-input-4");
    expect(screen.getByTestId("b24-users-error")).toHaveTextContent(
      "insufficient_scope",
    );
    expect(screen.queryByTestId("b24-select-4")).not.toBeInTheDocument();
    expect(screen.getByTestId("b24-input-3")).toHaveValue("7");

    await user.type(input, "1a2");
    expect(input).toHaveValue("12");
  });

  it("saves user_map (non-empty entries only) with the other config fields", async () => {
    const calls = stubApi();
    renderPage();
    const user = userEvent.setup();
    await screen.findByTestId("b24-select-3");

    await user.selectOptions(select(3), "");
    await user.selectOptions(select(4), "9");
    await user.click(screen.getByTestId("crm-connect"));

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const put = calls.find((call) => call.method === "PUT")!;
    expect(put.url).toMatch(/\/settings\/integrations\/bitrix24$/);
    expect(put.body).toEqual({
      is_enabled: true,
      config: {
        region: "ru",
        account: "acme.bitrix24.ru",
        webhook_url: "http…xyz/",
        user_id: "1",
        user_map: { "4": "9" },
        // Card options: defaults for a row saved before they existed.
        save_external_calls: true,
        create_card: "auto",
        lead_source: "CALL",
        only_answered: false,
        // Click-to-call toggle (off; no application_token typed → not sent).
        click_to_call_enabled: false,
      },
    });
  });

  it("shows the backend's validation message on a rejected save", async () => {
    stubApi({
      put: {
        status: 400,
        body: {
          success: false,
          error_code: "MISSING_FIELD",
          message: "user_map: Bitrix24 user 9 not found",
        },
      },
    });
    renderPage();
    const user = userEvent.setup();
    await screen.findByTestId("b24-select-4");
    await user.selectOptions(select(4), "9");
    await user.click(screen.getByTestId("crm-connect"));
    expect(await screen.findByTestId("crm-save-error")).toHaveTextContent(
      "user_map: Bitrix24 user 9 not found",
    );
  });
});
