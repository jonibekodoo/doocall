/** amoCRM page: operator → amoCRM manager mapping (shared CrmUserMapEditor):
 * select / manual mode, auto-match, saved user_map, errors, load guard. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AmoCrmIntegrationPage from "@/app/cabinet/settings/integrations/amocrm/page";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/settings/integrations/amocrm",
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
];
const USERS = [
  {
    id: 504141,
    name: "Admin",
    email: "admin@acme.uz",
    phone: "",
    position: "",
  },
  {
    id: 777,
    name: "Aziza Karimova",
    email: "aziza@acme.uz",
    phone: "",
    position: "",
  },
  { id: 888, name: "Bobur Aliyev", email: "", phone: "", position: "" },
];
const CONFIG = {
  region: "amocrm.ru",
  base_url: "https://acme.amocrm.ru",
  access_token: "eyJ0…xyz",
  responsible_user_id: "504141",
  user_map: { "3": "777" },
};

function stubApi({
  configured = true,
  listStatus = 200,
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
      if (url.endsWith("/auth/refresh"))
        return new Response("{}", { status: 401 });
      if (method === "PUT") {
        return new Response(JSON.stringify(put.body), { status: put.status });
      }
      if (url.endsWith("/amocrm/users"))
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
      if (listStatus !== 200) {
        return new Response(
          JSON.stringify({ success: false, message: "boom" }),
          {
            status: listStatus,
          },
        );
      }
      return new Response(
        JSON.stringify({
          success: true,
          integrations: [
            {
              provider: "amocrm",
              is_enabled: true,
              configured,
              config: configured ? CONFIG : {},
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
        <AmoCrmIntegrationPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const select = (id: number) =>
  screen.getByTestId(`amo-select-${id}`) as HTMLSelectElement;
const putBody = (calls: { method: string; body: unknown }[]) =>
  calls.find((call) => call.method === "PUT")!.body as {
    config: Record<string, unknown>;
  };

afterEach(() => vi.unstubAllGlobals());

describe("amoCRM operator mapping", () => {
  it("relabels the responsible field and hides the mapping until configured", async () => {
    stubApi({ configured: false });
    renderPage();
    expect(
      await screen.findByText(/Standart mas'ul \(amoCRM foydalanuvchi ID\)/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("amo-user-map")).not.toBeInTheDocument();
  });

  it("renders a select per operator with amoCRM managers and fallback marks", async () => {
    stubApi();
    renderPage();
    const section = await screen.findByTestId("amo-user-map");
    expect(section).toHaveTextContent(
      "Operatorlarni amoCRM menejerlariga moslash",
    );
    expect(section).toHaveTextContent("amoCRM menejeri");
    await screen.findByTestId("amo-select-3");

    expect(select(3)).toHaveValue("777");
    expect(select(4)).toHaveValue("");
    expect(
      within(select(4)).getByRole("option", { name: "— Standart —" }),
    ).toBeInTheDocument();
    expect(
      within(select(4)).getByRole("option", { name: "Admin · admin@acme.uz" }),
    ).toHaveValue("504141");
    expect(screen.queryByTestId("amo-default-3")).not.toBeInTheDocument();
    expect(screen.getByTestId("amo-default-4")).toHaveTextContent(
      "standart mas'ul: 504141",
    );
  });

  it("auto-match fills only empty rows and reports the count", async () => {
    stubApi({
      users: {
        success: true,
        users: USERS,
        operators: OPERATORS,
        suggestions: { "3": "504141", "4": "888" },
      },
    });
    renderPage();
    const user = userEvent.setup();
    await screen.findByTestId("amo-select-3");
    await user.click(screen.getByTestId("amo-auto-match"));
    expect(select(3)).toHaveValue("777"); // manual choice kept
    expect(select(4)).toHaveValue("888");
    expect(screen.getByTestId("amo-matched")).toHaveTextContent(
      "Moslandi: 1 ta operator",
    );
  });

  it("manual numeric inputs + the error when amoCRM users can't be loaded", async () => {
    stubApi({
      users: { success: false, error: "403 Forbidden", operators: OPERATORS },
    });
    renderPage();
    const user = userEvent.setup();
    const input = await screen.findByTestId("amo-input-4");
    expect(screen.getByTestId("amo-users-error")).toHaveTextContent(
      "amoCRM foydalanuvchilarini yuklab bo'lmadi: 403 Forbidden",
    );
    expect(screen.getByTestId("amo-input-3")).toHaveValue("777");
    await user.type(input, "9x9");
    expect(input).toHaveValue("99");
  });

  it("saves user_map (non-empty entries) with the rest of the config", async () => {
    const calls = stubApi();
    renderPage();
    const user = userEvent.setup();
    await screen.findByTestId("amo-select-3");
    await user.selectOptions(select(3), "");
    await user.selectOptions(select(4), "888");
    await user.click(screen.getByTestId("crm-connect"));

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    expect(calls.find((call) => call.method === "PUT")!.url).toMatch(
      /\/settings\/integrations\/amocrm$/,
    );
    expect(putBody(calls)).toEqual({
      is_enabled: true,
      config: { ...CONFIG, user_map: { "4": "888" } },
    });
  });

  it("shows the backend message on a rejected save", async () => {
    stubApi({
      put: {
        status: 400,
        body: {
          success: false,
          message: "user_map: amoCRM user 888 not found",
        },
      },
    });
    renderPage();
    const user = userEvent.setup();
    await screen.findByTestId("amo-select-4");
    await user.selectOptions(select(4), "888");
    await user.click(screen.getByTestId("crm-connect"));
    expect(await screen.findByTestId("crm-save-error")).toHaveTextContent(
      "user_map: amoCRM user 888 not found",
    );
  });

  it("no mapping and no save when the integrations list failed to load", async () => {
    const calls = stubApi({ listStatus: 500 });
    renderPage();
    expect(await screen.findByTestId("crm-load-error")).toBeInTheDocument();
    expect(screen.queryByTestId("amo-user-map")).not.toBeInTheDocument();
    expect(screen.queryByTestId("crm-connect")).not.toBeInTheDocument();
    expect(calls.some((call) => call.method === "PUT")).toBe(false);
  });
});
