/** Bitrix24 page: "Qo'ng'iroqlarni saqlash" card options — defaults, portal
 * mode notes (simple / assumed / classic), lead-source validation and the
 * saved body; saving stays locked when the initial load failed. */

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

const BASE = {
  region: "ru",
  account: "cdti.bitrix24.ru",
  webhook_url: "http…xyz/",
  user_id: "1",
  user_map: {},
};

function stubApi(
  config: Record<string, unknown> | null,
  { listStatus = 200 }: { listStatus?: number } = {},
) {
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
      if (url.endsWith("/auth/refresh")) {
        return new Response("{}", { status: 401 });
      }
      if (method === "PUT")
        return new Response(JSON.stringify({ success: true }));
      if (url.endsWith("/bitrix24/users")) {
        return new Response(
          JSON.stringify({ success: true, users: [], operators: [] }),
        );
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
              provider: "bitrix24",
              is_enabled: true,
              configured: true,
              config: config ?? BASE,
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

const radio = (mode: string) =>
  within(screen.getByTestId(`b24-card-${mode}`)).getByRole("radio");

afterEach(() => vi.unstubAllGlobals());

describe("Bitrix24 card options", () => {
  it("renders backend defaults for a row saved before the options existed", async () => {
    stubApi({
      ...BASE,
      crm_mode: "",
      crm_mode_checked_at: null,
      crm_mode_assumed: false,
    });
    renderPage();
    const section = await screen.findByTestId("b24-card-options");
    expect(section).toHaveTextContent("Qo'ng'iroqlarni saqlash");
    expect(screen.getByTestId("b24-save-external")).toBeChecked();
    expect(radio("auto")).toBeChecked();
    expect(screen.getByTestId("b24-card-auto")).toHaveTextContent(
      "Avtomatik (tavsiya etiladi)",
    );
    expect(screen.getByTestId("b24-card-deal")).toHaveTextContent(
      "Kontakt + Bitim",
    );
    expect(screen.getByTestId("b24-only-answered")).not.toBeChecked();
    // Mode not known yet → auto may still create a lead → source is shown.
    expect(screen.getByTestId("b24-lead-source")).toHaveValue("CALL");
    expect(screen.queryByTestId("b24-portal-mode")).not.toBeInTheDocument();
  });

  it("simple (lead-less) portal: note, Lead annotated, no lead source", async () => {
    stubApi({
      ...BASE,
      create_card: "auto",
      crm_mode: "simple",
      crm_mode_assumed: false,
    });
    renderPage();
    expect(await screen.findByTestId("b24-portal-mode")).toHaveTextContent(
      "Portal rejimi: lidlarsiz (oddiy CRM) — lid yaratilmaydi",
    );
    expect(screen.getByTestId("b24-card-lead")).toHaveTextContent(
      "Bu portalda lid yaratilmaydi",
    );
    expect(screen.queryByTestId("b24-lead-source")).not.toBeInTheDocument();
  });

  it("undetected mode is shown as 'no leads, for safety'", async () => {
    stubApi({
      ...BASE,
      create_card: "lead",
      crm_mode: "simple",
      crm_mode_assumed: true,
    });
    renderPage();
    expect(await screen.findByTestId("b24-portal-mode")).toHaveTextContent(
      "rejimi aniqlanmadi — xavfsizlik uchun lid yaratilmaydi",
    );
    expect(radio("lead")).toBeChecked();
    expect(screen.queryByTestId("b24-lead-source")).not.toBeInTheDocument();
  });

  it("classic portal shows its mode and keeps the lead source for auto", async () => {
    stubApi({ ...BASE, crm_mode: "classic", lead_source: "WEB" });
    renderPage();
    expect(await screen.findByTestId("b24-portal-mode")).toHaveTextContent(
      "klassik",
    );
    expect(screen.getByTestId("b24-lead-source")).toHaveValue("WEB");
    expect(screen.getByTestId("b24-card-lead")).not.toHaveTextContent(
      "Bu portalda lid yaratilmaydi",
    );
  });

  it("saves the options with the rest of the config", async () => {
    const calls = stubApi({
      ...BASE,
      crm_mode: "classic",
      save_external_calls: true,
      create_card: "auto",
      lead_source: "CALL",
      only_answered: false,
    });
    renderPage();
    const user = userEvent.setup();
    await screen.findByTestId("b24-card-options");

    await user.click(radio("lead"));
    const source = screen.getByTestId("b24-lead-source");
    await user.clear(source);
    await user.type(source, "uc_abc1");
    await user.click(screen.getByTestId("b24-only-answered"));
    await user.click(screen.getByTestId("crm-connect"));

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const body = calls.find((call) => call.method === "PUT")!.body as {
      config: Record<string, unknown>;
    };
    expect(body.config).toMatchObject({
      account: "cdti.bitrix24.ru",
      save_external_calls: true,
      create_card: "lead",
      lead_source: "UC_ABC1",
      only_answered: true,
    });
  });

  it("unchecking 'save external calls' disables the card choice and saves false", async () => {
    const calls = stubApi({ ...BASE, crm_mode: "classic" });
    renderPage();
    const user = userEvent.setup();
    await screen.findByTestId("b24-card-options");
    await user.click(screen.getByTestId("b24-save-external"));
    expect(screen.getByTestId("b24-create-card")).toBeDisabled();
    expect(screen.queryByTestId("b24-lead-source")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("crm-connect"));
    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const body = calls.find((call) => call.method === "PUT")!.body as {
      config: Record<string, unknown>;
    };
    expect(body.config.save_external_calls).toBe(false);
  });

  it("an invalid lead source blocks saving while it applies", async () => {
    const calls = stubApi({ ...BASE, crm_mode: "classic" });
    renderPage();
    const user = userEvent.setup();
    const source = await screen.findByTestId("b24-lead-source");
    await user.clear(source);
    await user.type(source, "web-site");

    expect(source).toHaveValue("WEB-SITE");
    expect(source).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByTestId("b24-lead-source-error")).toBeInTheDocument();
    expect(screen.getByTestId("crm-connect")).toBeDisabled();

    // Switching to a mode that never creates leads lifts the block; the bad
    // value is not sent (the stored source is kept).
    await user.click(radio("contact"));
    expect(screen.getByTestId("crm-connect")).toBeEnabled();
    await user.click(screen.getByTestId("crm-connect"));
    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const body = calls.find((call) => call.method === "PUT")!.body as {
      config: Record<string, unknown>;
    };
    expect(body.config.create_card).toBe("contact");
    expect(body.config).not.toHaveProperty("lead_source");
  });

  it("no options form and no save when the integrations list failed to load", async () => {
    const calls = stubApi(null, { listStatus: 500 });
    renderPage();
    expect(await screen.findByTestId("crm-load-error")).toBeInTheDocument();
    expect(screen.queryByTestId("b24-card-options")).not.toBeInTheDocument();
    expect(screen.queryByTestId("crm-connect")).not.toBeInTheDocument();
    expect(calls.some((call) => call.method === "PUT")).toBe(false);
  });
});
