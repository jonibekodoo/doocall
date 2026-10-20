/** Settings → Integratsiya: custom webhook card shows the last delivery
 * outcome (never / ok / each failure kind, plus the last success). */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "@/app/cabinet/settings/page";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/settings",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const OK_AT = "2026-10-20T13:16:04+05:00";
const ERR_AT = "2026-10-20T15:02:00+05:00";

/** Same local "dd.MM HH:mm" the card renders (runner's own zone). */
function local(iso: string): string {
  const date = new Date(iso);
  const two = (value: number) => String(value).padStart(2, "0");
  return `${two(date.getDate())}.${two(date.getMonth() + 1)} ${two(date.getHours())}:${two(date.getMinutes())}`;
}

function stubApi(webhook: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split("?")[0];
      if (path.endsWith("/settings/webhook")) {
        return new Response(
          JSON.stringify({
            success: true,
            webhook_url: "https://crm.example.uz/hook",
            secret_set: true,
            ...webhook,
          }),
        );
      }
      return new Response(
        JSON.stringify({
          success: true,
          integrations: [],
          entries: [],
          results: [],
        }),
      );
    }),
  );
}

async function openIntegration() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
  await userEvent.setup().click(screen.getByTestId("settings-tab-integration"));
  return screen.findByTestId("webhook-status");
}

afterEach(() => vi.unstubAllGlobals());

describe("Webhook delivery status", () => {
  it("never sent", async () => {
    stubApi({ last_status: null, last_ok_at: null, last_error_at: null });
    const line = await openIntegration();
    expect(line).toHaveAttribute("data-state", "never");
    expect(line).toHaveTextContent("Hali yuborilmagan");
  });

  it("older backend without the fields reads as never sent", async () => {
    stubApi({});
    expect(await openIntegration()).toHaveTextContent("Hali yuborilmagan");
  });

  it("ok — green with the last success time", async () => {
    stubApi({ last_status: "ok", last_ok_at: OK_AT, last_error_at: null });
    const line = await openIntegration();
    expect(line).toHaveAttribute("data-state", "ok");
    expect(line).toHaveClass("text-accent");
    expect(line).toHaveTextContent(
      `Oxirgi yuborish: muvaffaqiyatli — ${local(OK_AT)}`,
    );
  });

  it.each([
    [
      "http_401",
      "server HTTP 401 qaytardi — manzil yoki token noto'g'ri bo'lishi mumkin",
    ],
    [
      "http_404",
      "server HTTP 404 qaytardi — manzil yoki token noto'g'ri bo'lishi mumkin",
    ],
    ["http_502", "server HTTP 502 qaytardi (server xatosi)"],
    ["http_302", "server HTTP 302 qaytardi"],
    ["timeout", "server javob bermadi"],
    ["connection_error", "serverga ulanib bo'lmadi"],
    ["blocked", "manzil xavfsizlik tekshiruvidan o'tmadi"],
    ["error", "noma'lum xato"],
    ["something_new", "noma'lum xato"],
  ])("%s → red with the human reason", async (status, reason) => {
    stubApi({ last_status: status, last_ok_at: null, last_error_at: ERR_AT });
    const line = await openIntegration();
    expect(line).toHaveAttribute("data-state", "error");
    expect(line).toHaveTextContent(
      `Oxirgi yuborish: xato (${reason}) — ${local(ERR_AT)}`,
    );
    expect(screen.queryByTestId("webhook-last-ok")).not.toBeInTheDocument();
  });

  it("a failure after earlier successes also shows the last success", async () => {
    stubApi({
      last_status: "timeout",
      last_ok_at: OK_AT,
      last_error_at: ERR_AT,
    });
    await openIntegration();
    expect(screen.getByTestId("webhook-last-ok")).toHaveTextContent(
      `oxirgi muvaffaqiyatli: ${local(OK_AT)}`,
    );
  });

  it("no status line when no webhook is configured", async () => {
    stubApi({ webhook_url: null, last_status: null });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <NextIntlClientProvider locale="uz" messages={uz}>
        <QueryClientProvider client={client}>
          <SettingsPage />
        </QueryClientProvider>
      </NextIntlClientProvider>,
    );
    await userEvent
      .setup()
      .click(screen.getByTestId("settings-tab-integration"));
    // Wait until the webhook settings have actually loaded.
    await waitFor(() =>
      expect(client.getQueryState(["s-webhook"])?.status).toBe("success"),
    );
    expect(screen.queryByTestId("webhook-status")).not.toBeInTheDocument();
  });
});
