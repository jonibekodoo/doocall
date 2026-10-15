/** A failed GET /settings/integrations must never look like "integration
 * disabled": skeleton while loading, an error state (session-expired aware)
 * on 401/500, and no way to save a blank form over the real config. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "@/app/cabinet/settings/page";
import { CrmProviderPage } from "@/components/CrmProviderPage";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/settings/integrations/bitrix24",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const ENABLED = {
  success: true,
  integrations: [
    {
      provider: "bitrix24",
      is_enabled: true,
      configured: true,
      config: {
        account: "cdti.bitrix24.ru",
        webhook_url: "http…xyz/",
        user_id: "1",
      },
      last_status: "ok",
      last_error: "",
      last_delivery_at: null,
    },
  ],
};

type Mode = "ok" | "401" | "500" | "hang";

/** Integrations endpoint follows `state.mode`; refresh always fails (401). */
function stubApi(initial: Mode) {
  const state = { mode: initial };
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const method = init.method ?? "GET";
      calls.push({ method, url });
      if (url.endsWith("/auth/refresh")) {
        return new Response(JSON.stringify({ success: false }), {
          status: 401,
        });
      }
      if (url.endsWith("/settings/integrations") && method === "GET") {
        if (state.mode === "hang") return new Promise<Response>(() => {});
        if (state.mode === "401") {
          return new Response(
            JSON.stringify({
              success: false,
              error_code: "UNAUTHORIZED",
              message: "expired",
            }),
            { status: 401 },
          );
        }
        if (state.mode === "500") {
          return new Response(
            JSON.stringify({ success: false, message: "boom" }),
            {
              status: 500,
            },
          );
        }
        return new Response(JSON.stringify(ENABLED));
      }
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
          entries: [],
          results: [],
          users: [],
          report: [],
        }),
      );
    }),
  );
  return { state, calls };
}

function renderUi(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>{node}</QueryClientProvider>
    </NextIntlClientProvider>,
  );
  return client;
}

const page = (
  <CrmProviderPage
    provider="bitrix24"
    title="Bitrix24"
    info="info"
    fields={[{ key: "account", label: "Account" }]}
  />
);

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("CrmProviderPage load states", () => {
  it("shows a skeleton — not an unchecked form — while loading", async () => {
    stubApi("hang");
    renderUi(page);
    expect(await screen.findByTestId("crm-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("crm-enabled")).not.toBeInTheDocument();
    expect(screen.queryByTestId("crm-connect")).not.toBeInTheDocument();
  });

  it("401 (expired session): error + re-login, no form, nothing saved", async () => {
    const { calls } = stubApi("401");
    renderUi(page);
    expect(await screen.findByTestId("crm-load-error")).toHaveTextContent(
      "Ma'lumotni yuklab bo'lmadi",
    );
    expect(screen.getByTestId("crm-session-expired")).toHaveTextContent(
      "Sessiya muddati tugagan",
    );
    expect(screen.getByTestId("crm-relogin")).toHaveAttribute("href", "/login");
    expect(screen.queryByTestId("crm-enabled")).not.toBeInTheDocument();
    expect(screen.queryByTestId("crm-connect")).not.toBeInTheDocument();
    expect(
      calls.some(
        (call) => call.method !== "GET" && !call.url.includes("/auth/"),
      ),
    ).toBe(false);
  });

  it("401 while impersonating points back to the admin panel", async () => {
    window.sessionStorage.setItem(
      "doocall_impersonation",
      JSON.stringify({ token: "t", company: "cdti", user: "owner@cdti.uz" }),
    );
    stubApi("401");
    renderUi(page);
    expect(await screen.findByTestId("crm-session-expired")).toHaveTextContent(
      "Mijoz sifatida kirish muddati tugagan",
    );
    expect(screen.getByTestId("crm-relogin")).toHaveAttribute("href", "/admin");
  });

  it("500: error without the session hint; retry loads the real (enabled) state", async () => {
    const { state } = stubApi("500");
    renderUi(page);
    expect(await screen.findByTestId("crm-load-error")).toBeInTheDocument();
    expect(screen.queryByTestId("crm-session-expired")).not.toBeInTheDocument();
    expect(screen.queryByTestId("crm-connect")).not.toBeInTheDocument();

    state.mode = "ok";
    await userEvent.setup().click(screen.getByTestId("crm-load-retry"));
    expect(await screen.findByTestId("crm-enabled")).toBeChecked();
    expect(screen.getByTestId("crm-field-account")).toHaveValue(
      "cdti.bitrix24.ru",
    );
    expect(screen.queryByTestId("crm-load-error")).not.toBeInTheDocument();
    expect(screen.getByTestId("crm-connect")).toBeEnabled();
  });

  it("a failed background refetch locks saving even with the old data on screen", async () => {
    const { state, calls } = stubApi("ok");
    const client = renderUi(page);
    expect(await screen.findByTestId("crm-enabled")).toBeChecked();

    state.mode = "500";
    await client.refetchQueries({ queryKey: ["s-integrations"] });

    expect(await screen.findByTestId("crm-load-error")).toBeInTheDocument();
    const connect = screen.getByTestId("crm-connect");
    expect(connect).toBeDisabled();
    expect(screen.getByTestId("crm-disconnect")).toBeDisabled();
    expect(screen.getByTestId("crm-test")).toBeDisabled();
    await userEvent.setup().click(connect);
    expect(calls.some((call) => call.method === "PUT")).toBe(false);
  });
});

describe("Settings integration tiles", () => {
  async function openIntegrationTab() {
    renderUi(<SettingsPage />);
    await userEvent
      .setup()
      .click(screen.getByTestId("settings-tab-integration"));
  }

  it("marks tiles as unknown (not off) when the list fails to load", async () => {
    stubApi("500");
    await openIntegrationTab();
    expect(await screen.findByTestId("crm-tiles-error")).toBeInTheDocument();
    expect(screen.getByTestId("crm-tile-status-bitrix24")).toHaveAttribute(
      "data-status",
      "unknown",
    );
  });

  it("shows the real status once loaded", async () => {
    stubApi("ok");
    await openIntegrationTab();
    await waitFor(() =>
      expect(screen.getByTestId("crm-tile-status-bitrix24")).toHaveAttribute(
        "data-status",
        "ok",
      ),
    );
    expect(screen.queryByTestId("crm-tiles-error")).not.toBeInTheDocument();
  });
});
