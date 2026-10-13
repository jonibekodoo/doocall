/** Kotib Analytics connector page: single API-key field, connected summary
 * (company + operator counts), and the backend's connect error on the card. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import en from "@/messages/en.json";
import KotibIntegrationPage from "@/app/cabinet/settings/integrations/kotib/page";
import type { CrmIntegrationRow } from "@/lib/api/endpoints";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/settings/integrations/kotib",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

function kotibRow(overrides: Partial<CrmIntegrationRow> = {}): CrmIntegrationRow {
  return {
    provider: "kotib",
    is_enabled: false,
    configured: false,
    config: { api_key: "" },
    last_status: "",
    last_error: "",
    last_delivery_at: null,
    ...overrides,
  };
}

/** Stub fetch: GET integrations → `row`; PUT kotib → `put` (status, body). */
function stubApi(
  row: CrmIntegrationRow,
  put: { status: number; body: unknown } = {
    status: 200,
    body: { success: true, integration: row },
  },
) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const method = init.method ?? "GET";
      calls.push({
        url,
        method,
        body: init.body ? JSON.parse(String(init.body)) : undefined,
      });
      if (method === "PUT" && url.endsWith("/settings/integrations/kotib")) {
        return new Response(JSON.stringify(put.body), { status: put.status });
      }
      if (url.includes("/deliveries")) {
        return new Response(
          JSON.stringify({
            success: true,
            deliveries: [],
            pages: 1,
            summary: { ok_30d: 0, error_30d: 0 },
          }),
          { status: 200 },
        );
      }
      return new Response(
        JSON.stringify({ success: true, integrations: [row] }),
        { status: 200 },
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
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={client}>
        <KotibIntegrationPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Kotib integration page", () => {
  it("renders exactly one field — the Kotib API key — and no enable toggle", async () => {
    stubApi(kotibRow());
    renderPage();
    expect(await screen.findByTestId("crm-page-kotib")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Integration — Kotib Analytics",
    );
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.getByTestId("crm-field-api_key")).toBeInTheDocument();
    expect(screen.getByText("Kotib API key")).toBeInTheDocument();
    expect(screen.queryByTestId("crm-enabled")).not.toBeInTheDocument();
    expect(screen.queryByTestId("crm-connected-info")).not.toBeInTheDocument();
  });

  it("shows the company name and operator counts when connected", async () => {
    stubApi(
      kotibRow({
        is_enabled: true,
        configured: true,
        config: {
          api_key: "ab12…ef90",
          company_name: "My Company",
          employees_created: "12",
          employees_existing: "3",
          employees_created_inactive: "2",
        },
      }),
    );
    renderPage();
    expect(await screen.findByText("Connected: My Company")).toBeInTheDocument();
    expect(screen.getByTestId("kotib-employees")).toHaveTextContent(
      "created — 12, already existed — 3, inactive — 2",
    );
    expect(screen.getByTestId("kotib-inactive-warning")).toHaveTextContent(
      "Inactive operators: 2",
    );
    // The masked key is shown as-is (the backend keeps the stored secret).
    expect(screen.getByTestId("crm-field-api_key")).toHaveValue("ab12…ef90");
  });

  it("hides the inactive warning when every operator is active", async () => {
    stubApi(
      kotibRow({
        is_enabled: true,
        configured: true,
        config: {
          api_key: "ab12…ef90",
          company_name: "My Company",
          employees_created: "5",
          employees_existing: "0",
          employees_created_inactive: "0",
        },
      }),
    );
    renderPage();
    expect(await screen.findByText("Connected: My Company")).toBeInTheDocument();
    expect(screen.queryByTestId("kotib-inactive-warning")).not.toBeInTheDocument();
  });

  it("saves with is_enabled=true and keeps Kotib's error message on the card", async () => {
    const calls = stubApi(kotibRow(), {
      status: 400,
      body: {
        success: false,
        error_code: "MISSING_FIELD",
        message: "Kotib API kaliti noto'g'ri",
      },
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByTestId("crm-field-api_key"), "bad-key");
    await user.click(screen.getByTestId("crm-connect"));

    expect(await screen.findByTestId("crm-save-error")).toHaveTextContent(
      "Kotib API kaliti noto'g'ri",
    );
    const put = calls.find((call) => call.method === "PUT");
    expect(put?.body).toEqual({
      is_enabled: true,
      config: { api_key: "bad-key" },
    });
    expect(screen.queryByTestId("crm-connected-info")).not.toBeInTheDocument();
  });
});
