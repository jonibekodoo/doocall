/** Webhook card: masked signing-secret hint, "Kalitni yangilash" (confirmed),
 * the new secret shown once with copy, 429 message; docs signature section. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApiDocsPage from "@/app/docs/api/page";
import SettingsPage from "@/app/cabinet/settings/page";
import { ConfirmHost } from "@/components/ui/Confirm";
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
  webhook = {
    webhook_url: "https://crm.example.uz/hook",
    secret_set: true,
    secret_hint: "a1b2",
  } as Record<string, unknown>,
  rotate = {
    status: 200,
    body: { success: true, secret: "whsec_NEW_9f8e7d" },
  } as {
    status: number;
    body: unknown;
  },
  save = {
    status: 200,
    body: { success: true, webhook_url: "x", secret: null },
  } as {
    status: number;
    body: unknown;
  },
} = {}) {
  const calls: Call[] = [];
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
      if (path.endsWith("/settings/webhook/rotate-secret")) {
        return new Response(JSON.stringify(rotate.body), {
          status: rotate.status,
        });
      }
      if (path.endsWith("/settings/webhook")) {
        if (method === "PUT") {
          return new Response(JSON.stringify(save.body), {
            status: save.status,
          });
        }
        return new Response(JSON.stringify({ success: true, ...webhook }));
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
  return calls;
}

function renderSettings() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>
        <SettingsPage />
        <ConfirmHost />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

async function openIntegration() {
  const user = userEvent.setup();
  renderSettings();
  await user.click(screen.getByTestId("settings-tab-integration"));
  await screen.findByTestId("webhook-secret");
  return user;
}

afterEach(() => {
  vi.unstubAllGlobals();
  intl.locale = "uz";
});

describe("Webhook signing secret", () => {
  it("shows the masked hint and the signature help", async () => {
    stubApi();
    await openIntegration();
    expect(screen.getByTestId("webhook-secret-hint")).toHaveTextContent(
      "••••a1b2",
    );
    const block = screen.getByTestId("webhook-secret");
    expect(block).toHaveTextContent(
      "Imzo: X-Doocall-Signature = HMAC-SHA256(kalit, so'rov tanasi), hex.",
    );
    expect(
      within(block).getByRole("link", { name: "Tekshirish misollari" }),
    ).toHaveAttribute("href", "/docs/api#webhook-signature");
    expect(
      screen.queryByTestId("webhook-secret-fresh"),
    ).not.toBeInTheDocument();
  });

  it("rotates after confirmation and shows the new secret once, copyable", async () => {
    const calls = stubApi();
    const user = await openIntegration();
    await user.click(screen.getByTestId("webhook-secret-rotate"));
    const dialog = await screen.findByTestId("app-confirm");
    expect(dialog).toHaveTextContent("Eski kalit darhol ishlamay qoladi");
    await user.click(screen.getByTestId("app-confirm-ok"));

    const fresh = await screen.findByTestId("webhook-secret-fresh");
    expect(within(fresh).getByTestId("webhook-secret-value")).toHaveValue(
      "whsec_NEW_9f8e7d",
    );
    expect(fresh).toHaveTextContent("Bu kalit faqat hozir ko'rsatiladi");
    expect(
      calls.filter(
        (call) => call.method === "POST" && call.url.endsWith("/rotate-secret"),
      ),
    ).toHaveLength(1);

    await user.click(within(fresh).getByTestId("webhook-secret-copy"));
    expect(await navigator.clipboard.readText()).toBe("whsec_NEW_9f8e7d");
  });

  it("does nothing when the confirmation is cancelled", async () => {
    const calls = stubApi();
    const user = await openIntegration();
    await user.click(screen.getByTestId("webhook-secret-rotate"));
    await user.click(await screen.findByTestId("app-confirm-cancel"));
    expect(calls.some((call) => call.url.endsWith("/rotate-secret"))).toBe(
      false,
    );
    expect(
      screen.queryByTestId("webhook-secret-fresh"),
    ).not.toBeInTheDocument();
  });

  it("429 shows the rate-limit message", async () => {
    stubApi({
      rotate: {
        status: 429,
        body: { success: false, error_code: "THROTTLED", message: "x" },
      },
    });
    const user = await openIntegration();
    await user.click(screen.getByTestId("webhook-secret-rotate"));
    await user.click(await screen.findByTestId("app-confirm-ok"));
    expect(await screen.findByTestId("webhook-secret-error")).toHaveTextContent(
      "Kalit juda tez-tez yangilanmoqda",
    );
    expect(
      screen.queryByTestId("webhook-secret-fresh"),
    ).not.toBeInTheDocument();
  });

  it("the secret issued on first save uses the same show-once box", async () => {
    stubApi({
      webhook: { webhook_url: null, secret_set: false },
      save: {
        status: 200,
        body: {
          success: true,
          webhook_url: "https://n.uz/h",
          secret: "whsec_FIRST_1",
        },
      },
    });
    const user = userEvent.setup();
    renderSettings();
    await user.click(screen.getByTestId("settings-tab-integration"));
    const input = await screen.findByPlaceholderText(
      "https://crm.example.uz/hook",
    );
    await user.type(input, "https://n.uz/h");
    await user.click(screen.getByRole("button", { name: "OK" }));
    await waitFor(() =>
      expect(screen.getByTestId("webhook-secret-value")).toHaveValue(
        "whsec_FIRST_1",
      ),
    );
  });
});

describe("API docs: webhook signature", () => {
  it.each(["uz", "ru", "en"])(
    "has verification examples (%s)",
    async (locale) => {
      intl.locale = locale;
      const client = new QueryClient();
      render(
        <NextIntlClientProvider locale={locale} messages={uz}>
          <QueryClientProvider client={client}>
            {await ApiDocsPage()}
          </QueryClientProvider>
        </NextIntlClientProvider>,
      );
      const section = document.getElementById("webhook-signature")!;
      expect(section).not.toBeNull();
      for (const marker of [
        "X-Doocall-Signature",
        "hmac.compare_digest",
        "hash_hmac('sha256'",
        "hash_equals",
        "timingSafeEqual",
      ]) {
        expect(section).toHaveTextContent(marker);
      }
    },
  );
});
