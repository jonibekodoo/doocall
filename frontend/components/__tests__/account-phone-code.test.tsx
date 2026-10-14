/** Settings → Hisob: "Telefon kodi" select — shows the saved code, follows a
 * Davlat change (Tajikistan → +992) and saves phone_code via the account API. */

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

/** Stateful /settings/account stub: PUT merges into the server copy. */
function stubApi(initial: Record<string, unknown>) {
  const server = {
    contact_import_enabled: true,
    recording_enabled: true,
    pin_enabled: false,
    country: "UZ",
    timezone: "Asia/Tashkent",
    phone_code: "998",
    ...initial,
  };
  const puts: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      if (url.endsWith("/settings/account")) {
        if (init.method === "PUT") {
          const body = JSON.parse(String(init.body));
          puts.push(body);
          Object.assign(server, body);
        }
        return new Response(
          JSON.stringify({ success: true, settings: server }),
          {
            status: 200,
          },
        );
      }
      // Other tabs' queries (users list on first render) — empty payloads.
      return new Response(
        JSON.stringify({
          success: true,
          results: [],
          users: [],
          groups: [],
          count: 0,
        }),
        { status: 200 },
      );
    }),
  );
  return puts;
}

async function openAccountTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
  const user = userEvent.setup();
  await user.click(screen.getByTestId("settings-tab-account"));
  return {
    user,
    select: (await screen.findByTestId(
      "account-phone-code",
    )) as HTMLSelectElement,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("account phone code", () => {
  it("renders the saved code with labelled options and the help text", async () => {
    stubApi({ country: "TJ", timezone: "Asia/Dushanbe", phone_code: "992" });
    const { select } = await openAccountTab();
    expect(select).toHaveValue("992");
    expect(
      screen.getByRole("option", { name: "+992 — Tajikistan" }),
    ).toBeInTheDocument();
    // Countries sharing +7 collapse into one option.
    expect(
      screen.getByRole("option", { name: "+7 — Kazakhstan / Russia" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Telefon kodi")).toBeInTheDocument();
    expect(screen.getByText(/shu kod bilan saqlanadi/)).toBeInTheDocument();
  });

  it("keeps an unknown saved code selectable instead of hiding it", async () => {
    stubApi({ phone_code: "380" });
    const { select } = await openAccountTab();
    expect(select).toHaveValue("380");
    expect(screen.getByRole("option", { name: "+380" })).toBeInTheDocument();
  });

  it("switching Davlat to Tajikistan pre-selects +992 and saves it", async () => {
    const puts = stubApi({});
    const { user, select } = await openAccountTab();
    expect(select).toHaveValue("998");

    await user.selectOptions(screen.getByTestId("account-country"), "TJ");

    expect(puts).toContainEqual({
      country: "TJ",
      timezone: "Asia/Dushanbe",
      phone_code: "992",
    });
    await waitFor(() =>
      expect(screen.getByTestId("account-phone-code")).toHaveValue("992"),
    );
  });

  it("overriding the code saves only phone_code", async () => {
    const puts = stubApi({
      country: "TJ",
      timezone: "Asia/Dushanbe",
      phone_code: "992",
    });
    const { user, select } = await openAccountTab();

    await user.selectOptions(select, "998");

    expect(puts).toEqual([{ phone_code: "998" }]);
    await waitFor(() =>
      expect(screen.getByTestId("account-phone-code")).toHaveValue("998"),
    );
    expect(screen.getByTestId("account-country")).toHaveValue("TJ");
  });
});
