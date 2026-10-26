/** Remote Dial for integrations: the API-dial toggle (Settings →
 * Integratsiya), Bitrix24 click-to-call section, and the docs sections. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApiDocsPage from "@/app/docs/api/page";
import Bitrix24GuidePage from "@/app/docs/bitrix24/page";
import Bitrix24IntegrationPage from "@/app/cabinet/settings/integrations/bitrix24/page";
import SettingsPage from "@/app/cabinet/settings/page";
import uz from "@/messages/uz.json";

const intl = vi.hoisted(() => ({ locale: "uz" }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/settings",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));
vi.mock("next-intl/server", () => ({ getLocale: async () => intl.locale }));

type Call = { method: string; url: string; body: unknown };

function stubApi({
  account = {} as Record<string, unknown>,
  bitrix = null as Record<string, unknown> | null,
  put = { status: 200, body: { success: true } } as {
    status: number;
    body: unknown;
  },
} = {}) {
  const calls: Call[] = [];
  // Server-side account settings (PUT persists, like the real endpoint).
  const accountState: Record<string, unknown> = {
    contact_import_enabled: true,
    recording_enabled: true,
    pin_enabled: false,
    country: "UZ",
    timezone: "Asia/Tashkent",
    phone_code: "998",
    ...account,
  };
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
      const path = url.split("?")[0];
      if (path.endsWith("/settings/account")) {
        if (method === "PUT")
          Object.assign(accountState, JSON.parse(String(init.body)));
        const settings = accountState;
        return new Response(JSON.stringify({ success: true, settings }));
      }
      if (method === "PUT")
        return new Response(JSON.stringify(put.body), { status: put.status });
      if (path.endsWith("/settings/integrations")) {
        return new Response(
          JSON.stringify({
            success: true,
            integrations: bitrix
              ? [
                  {
                    provider: "bitrix24",
                    is_enabled: true,
                    configured: true,
                    config: bitrix,
                    last_status: "",
                    last_error: "",
                    last_delivery_at: null,
                  },
                ]
              : [],
          }),
        );
      }
      if (path.endsWith("/bitrix24/users")) {
        return new Response(
          JSON.stringify({ success: true, users: [], operators: [] }),
        );
      }
      if (path.includes("/deliveries")) {
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
        JSON.stringify({ success: true, entries: [], results: [], report: [] }),
      );
    }),
  );
  return calls;
}

function renderUi(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>{node}</QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  intl.locale = "uz";
});

describe("API-dial toggle (Settings → Integratsiya)", () => {
  it("is off by default and saves api_dial_enabled on change", async () => {
    const calls = stubApi();
    renderUi(<SettingsPage />);
    await userEvent
      .setup()
      .click(screen.getByTestId("settings-tab-integration"));
    const toggle = await screen.findByTestId("api-dial-toggle");
    expect(toggle).not.toBeChecked();
    expect(screen.getByTestId("api-dial")).toHaveTextContent(
      "API orqali masofaviy qo'ng'iroqqa ruxsat",
    );
    expect(screen.getByTestId("api-dial")).toHaveTextContent(
      /API kalitni sir saqlang/,
    );

    await userEvent.setup().click(toggle);
    await waitFor(() =>
      expect(
        calls.find(
          (call) =>
            call.method === "PUT" && call.url.endsWith("/settings/account"),
        )?.body,
      ).toEqual({ api_dial_enabled: true }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("api-dial-toggle")).toBeChecked(),
    );
  });

  it("shows the stored value", async () => {
    stubApi({ account: { api_dial_enabled: true } });
    renderUi(<SettingsPage />);
    await userEvent
      .setup()
      .click(screen.getByTestId("settings-tab-integration"));
    expect(await screen.findByTestId("api-dial-toggle")).toBeChecked();
  });
});

const B24 = {
  region: "ru",
  account: "cdti.bitrix24.ru",
  webhook_url: "http…xyz/",
  user_id: "1",
  user_map: {},
  click_to_call_enabled: false,
  click_to_call_url: "https://cdti.doocall.uz/api/public/b24/c2c/Tk3",
  b24_app_token_set: false,
  external_line_registered: true,
};

describe("Bitrix24 click-to-call section", () => {
  it("renders URL + status, copies the URL, saves toggle + token", async () => {
    const calls = stubApi({ bitrix: B24 });
    renderUi(<Bitrix24IntegrationPage />);
    const section = await screen.findByTestId("b24-click-to-call");
    expect(section).toHaveTextContent("Bir bosishda qo'ng'iroq");
    expect(within(section).getByTestId("b24-c2c-url")).toHaveValue(
      B24.click_to_call_url,
    );
    const status = within(section).getByTestId("b24-c2c-status");
    expect(status).toHaveTextContent("application_token kiritilmagan");
    expect(status).toHaveTextContent("ro'yxatdan o'tgan");
    expect(
      within(section).getByRole("link", { name: /qo'llanma/ }),
    ).toHaveAttribute("href", "/docs/bitrix24#click-to-call");

    // userEvent.setup() provides a clipboard stub; read back what was copied.
    const user = userEvent.setup();
    await user.click(within(section).getByTestId("b24-c2c-copy"));
    expect(await navigator.clipboard.readText()).toBe(B24.click_to_call_url);

    // Enabling needs a token: disabled + hint until one is typed.
    const toggle = within(section).getByTestId("b24-c2c-enabled");
    expect(toggle).toBeDisabled();
    expect(within(section).getByTestId("b24-c2c-need-token")).toHaveTextContent(
      "Avval Bitrix24 bergan application_token ni kiriting",
    );
    await user.type(
      within(section).getByTestId("b24-c2c-token"),
      "  app-tok-1 ",
    );
    expect(toggle).toBeEnabled();
    expect(
      within(section).queryByTestId("b24-c2c-need-token"),
    ).not.toBeInTheDocument();
    await user.click(toggle);
    await user.click(screen.getByTestId("crm-connect"));
    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const body = calls.find((call) => call.method === "PUT")!.body as {
      config: Record<string, unknown>;
    };
    expect(body.config).toMatchObject({
      click_to_call_enabled: true,
      b24_app_token: "app-tok-1",
    });
  });

  it("doesn't send an empty token; a stored one shows as saved", async () => {
    const calls = stubApi({
      bitrix: { ...B24, click_to_call_enabled: true, b24_app_token_set: true },
    });
    renderUi(<Bitrix24IntegrationPage />);
    const section = await screen.findByTestId("b24-click-to-call");
    expect(within(section).getByTestId("b24-c2c-enabled")).toBeChecked();
    expect(within(section).getByTestId("b24-c2c-token")).toHaveAttribute(
      "placeholder",
      expect.stringContaining("Saqlangan"),
    );
    expect(within(section).getByTestId("b24-c2c-status")).toHaveTextContent(
      "application_token saqlangan",
    );
    await userEvent.setup().click(screen.getByTestId("crm-connect"));
    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const body = calls.find((call) => call.method === "PUT")!.body as {
      config: Record<string, unknown>;
    };
    expect(body.config.click_to_call_enabled).toBe(true);
    expect(body.config).not.toHaveProperty("b24_app_token");
  });

  it("shows a hint when the handler URL doesn't exist yet", async () => {
    stubApi({ bitrix: { ...B24, click_to_call_url: "" } });
    renderUi(<Bitrix24IntegrationPage />);
    const section = await screen.findByTestId("b24-click-to-call");
    expect(
      within(section).getByTestId("b24-c2c-url-missing"),
    ).toHaveTextContent("integratsiyani «Ulash» tugmasi bilan saqlang");
    expect(
      within(section).queryByTestId("b24-c2c-copy"),
    ).not.toBeInTheDocument();
  });

  it("shows the backend's 400 text verbatim", async () => {
    const message = "Avval Bitrix24 bergan application_token ni kiriting";
    stubApi({
      bitrix: { ...B24, b24_app_token_set: true },
      put: {
        status: 400,
        body: { success: false, error_code: "MISSING_FIELD", message },
      },
    });
    renderUi(<Bitrix24IntegrationPage />);
    const section = await screen.findByTestId("b24-click-to-call");
    const user = userEvent.setup();
    await user.click(within(section).getByTestId("b24-c2c-enabled"));
    await user.click(screen.getByTestId("crm-connect"));
    expect(await screen.findByTestId("crm-save-error")).toHaveTextContent(
      message,
    );
  });

  it("an already-enabled setup without a token can still be switched off", async () => {
    const calls = stubApi({
      bitrix: { ...B24, click_to_call_enabled: true, b24_app_token_set: false },
    });
    renderUi(<Bitrix24IntegrationPage />);
    const section = await screen.findByTestId("b24-click-to-call");
    const toggle = within(section).getByTestId("b24-c2c-enabled");
    expect(toggle).toBeEnabled();
    const user = userEvent.setup();
    await user.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(toggle).toBeDisabled(); // can't turn it back on without a token
    await user.click(screen.getByTestId("crm-connect"));
    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const body = calls.find((call) => call.method === "PUT")!.body as {
      config: Record<string, unknown>;
    };
    expect(body.config.click_to_call_enabled).toBe(false);
  });

  it("is hidden until Bitrix24 is configured", async () => {
    stubApi({ bitrix: null });
    renderUi(<Bitrix24IntegrationPage />);
    await screen.findByTestId("crm-load-error"); // no bitrix24 row in the list
    expect(screen.queryByTestId("b24-click-to-call")).not.toBeInTheDocument();
  });
});

describe("Docs", () => {
  it.each(["uz", "ru", "en"])(
    "API docs have the Remote Dial section (%s)",
    async (locale) => {
      intl.locale = locale;
      renderUi(await ApiDocsPage());
      const section = document.getElementById("remote-dial")!;
      expect(section).not.toBeNull();
      expect(section).toHaveTextContent("calls.dial.status");
      expect(section).toHaveTextContent("1.16.3");
      expect(section).toHaveTextContent("+998");
      const reasons = within(section).getByTestId("dial-reasons");
      for (const reason of [
        "permission_denied",
        "invalid_number",
        "another_call_active",
        "sim_disabled",
        "duplicate",
        "feature_disabled",
        "user_declined",
        "timeout",
        "expired",
        "rate_limited",
      ]) {
        expect(within(reasons).getByText(reason)).toBeInTheDocument();
      }
      const statuses = within(section).getByTestId("dial-statuses");
      for (const status of [
        "sent",
        "received",
        "rejected",
        "dialing",
        "active",
        "disconnected",
        "expired",
        "offline",
      ]) {
        expect(within(statuses).getByText(status)).toBeInTheDocument();
      }
    },
  );

  it.each(["uz", "ru", "en"])(
    "Bitrix24 guide has the click-to-call anchor (%s)",
    async (locale) => {
      intl.locale = locale;
      renderUi(await Bitrix24GuidePage());
      const anchor = document.getElementById("click-to-call")!;
      expect(anchor).not.toBeNull();
      expect(document.body).toHaveTextContent("ONEXTERNALCALLSTART");
      expect(document.body).toHaveTextContent("application_token");
    },
  );

  describe("Bitrix24 guide step order", () => {
    it.each([
      [
        "ru",
        "скопируйте адрес обработчика",
        "ONEXTERNALCALLSTART",
        "Токен приложения",
        "Только теперь включите",
      ],
      [
        "uz",
        "manzilini nusxalang",
        "ONEXTERNALCALLSTART",
        "Ilova tokeni",
        "Faqat shundan keyin",
      ],
      [
        "en",
        "copy the handler URL",
        "ONEXTERNALCALLSTART",
        "Application token",
        "Only now turn",
      ],
    ])("%s: copy URL → webhook → token → enable", async (locale, ...steps) => {
      intl.locale = locale;
      renderUi(await Bitrix24GuidePage());
      const text = document.body.textContent ?? "";
      const positions = steps.map((step) => text.indexOf(step));
      for (const position of positions) expect(position).toBeGreaterThan(-1);
      expect([...positions].sort((a, b) => a - b)).toEqual(positions);
    });
  });
});
