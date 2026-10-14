/** Settings → Hisob: the contact-import / PIN toggle labels follow the UI
 * locale (they used to be hardcoded Russian). */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "@/app/cabinet/settings/page";
import en from "@/messages/en.json";
import ru from "@/messages/ru.json";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/settings",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const MESSAGES = { uz, ru, en } as const;

afterEach(() => vi.unstubAllGlobals());

describe("account toggles locale", () => {
  it.each([
    ["uz", "Kontaktlarni import qilish", "PIN-kod"],
    ["ru", "Импорт контактов", "PIN-код"],
    ["en", "Contact import", "PIN code"],
  ] as const)("renders %s labels", async (locale, contactImport, pin) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const body = String(input).endsWith("/settings/account")
          ? {
              success: true,
              settings: {
                contact_import_enabled: true,
                recording_enabled: true,
                pin_enabled: false,
                country: "UZ",
                timezone: "Asia/Tashkent",
                phone_code: "998",
              },
            }
          : { success: true, results: [], users: [], groups: [], count: 0 };
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]}>
        <QueryClientProvider client={client}>
          <SettingsPage />
        </QueryClientProvider>
      </NextIntlClientProvider>,
    );
    await userEvent.setup().click(screen.getByTestId("settings-tab-account"));

    expect(
      await screen.findByRole("checkbox", { name: contactImport }),
    ).toBeChecked();
    expect(screen.getByRole("checkbox", { name: pin })).not.toBeChecked();
    if (locale !== "ru") {
      expect(screen.queryByText("Импорт контактов")).not.toBeInTheDocument();
      expect(screen.queryByText("PIN-код")).not.toBeInTheDocument();
    }
  });
});
