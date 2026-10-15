/** Kotib page (connected): "AI tahlil natijalari" — webhook URL + copy,
 * signing-secret save, rotate (confirmed), stats and the unsigned warning. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import KotibIntegrationPage from "@/app/cabinet/settings/integrations/kotib/page";
import { ConfirmHost } from "@/components/ui/Confirm";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/settings/integrations/kotib",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const URL_ = "https://acme.doocall.uz/api/public/kotib/analysis/Xk3q9";

function stubApi(config: Record<string, unknown>) {
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
      if (method !== "GET") {
        return new Response(JSON.stringify({ success: true }));
      }
      return new Response(
        JSON.stringify({
          success: true,
          integrations: [
            {
              provider: "kotib",
              is_enabled: true,
              configured: true,
              config: {
                api_key: "ab12…ef90",
                company_name: "My Company",
                ...config,
              },
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
        <KotibIntegrationPage />
        <ConfirmHost />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Kotib AI analysis settings", () => {
  it("shows the webhook URL, stats, and warns while no secret is set", async () => {
    stubApi({
      analysis_webhook_url: URL_,
      analysis_secret: "",
      analysis_last_received_at: "2026-10-14T09:20:00+05:00",
      analysis_count: 12,
    });
    renderPage();
    expect(await screen.findByTestId("kotib-analysis-url")).toHaveValue(URL_);
    expect(
      screen.getByText(/Kotib menejeringizga yuboring/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("kotib-analysis-stats")).toHaveTextContent(
      "Oxirgi natija: 2026-10-14 09:20 · jami: 12",
    );
    expect(screen.getByTestId("kotib-analysis-unsigned")).toBeInTheDocument();
  });

  it("saves the signing secret with PUT …/kotib/analysis", async () => {
    const calls = stubApi({
      analysis_webhook_url: URL_,
      analysis_secret: "",
      analysis_count: 0,
    });
    renderPage();
    const user = userEvent.setup();
    const input = await screen.findByTestId("kotib-analysis-secret");
    expect(screen.getByTestId("kotib-analysis-secret-save")).toBeDisabled();
    expect(screen.getByTestId("kotib-analysis-stats")).toHaveTextContent(
      "Hali natija kelmagan",
    );

    await user.type(input, "  s3cr3t  ");
    await user.click(screen.getByTestId("kotib-analysis-secret-save"));

    await waitFor(() =>
      expect(
        calls.find(
          (call) =>
            call.method === "PUT" &&
            call.url.endsWith("/settings/integrations/kotib/analysis"),
        )?.body,
      ).toEqual({ secret: "s3cr3t" }),
    );
    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("hides the warning once a secret is stored and shows it masked", async () => {
    stubApi({ analysis_webhook_url: URL_, analysis_secret: "s3c…r3t" });
    renderPage();
    const input = await screen.findByTestId("kotib-analysis-secret");
    expect(input).toHaveAttribute(
      "placeholder",
      expect.stringContaining("s3c…r3t"),
    );
    expect(input).toHaveValue("");
    expect(
      screen.queryByTestId("kotib-analysis-unsigned"),
    ).not.toBeInTheDocument();
  });

  it("rotates the URL only after confirmation", async () => {
    const calls = stubApi({
      analysis_webhook_url: URL_,
      analysis_secret: "x…y",
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("kotib-analysis-rotate"));
    await user.click(await screen.findByTestId("app-confirm-cancel"));
    expect(calls.some((call) => call.url.endsWith("/analysis/rotate"))).toBe(
      false,
    );

    await user.click(screen.getByTestId("kotib-analysis-rotate"));
    await user.click(await screen.findByTestId("app-confirm-ok"));
    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.method === "POST" && call.url.endsWith("/analysis/rotate"),
        ),
      ).toBe(true),
    );
  });
});
