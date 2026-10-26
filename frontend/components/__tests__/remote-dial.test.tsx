/** Remote Dial button + modal: device list / preselect / offline disabled,
 * POST body, live status progression (fake timers), rejected reasons,
 * offline (409), rate limit (429), invalid number (400), hidden states. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  normalizeDialNumber,
  RemoteDialButton,
} from "@/components/RemoteDialButton";
import uz from "@/messages/uz.json";

const ONLINE = {
  device_id: "dev-a",
  operator: { id: 3, full_name: "Aziza Karimova" },
  model: "TECNO Spark 20",
  online: true,
  last_seen: "2026-10-26T10:00:00+05:00",
};
const OFFLINE = {
  device_id: "dev-b",
  operator: { id: 4, full_name: "Bobur Aliyev" },
  model: "Redmi 12",
  online: false,
  last_seen: "2026-10-20T10:00:00+05:00",
};

type Reply = { status: number; body: unknown };

/** devices → GET /dial/devices; post → POST /dial; states → successive GETs. */
function stubApi({
  devices = [ONLINE, OFFLINE] as unknown,
  devicesStatus = 200,
  post = {
    status: 200,
    body: { success: true, command_id: "cmd-1", status: "sent" },
  } as Reply,
  states = [] as Record<string, unknown>[],
} = {}) {
  const posts: Record<string, unknown>[] = [];
  const polls: string[] = [];
  let index = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const path = url.split("?")[0];
      if (path.endsWith("/auth/refresh"))
        return new Response("{}", { status: 401 });
      if (path.endsWith("/dial/devices")) {
        return new Response(JSON.stringify(devices), { status: devicesStatus });
      }
      if (path.endsWith("/dial") && init.method === "POST") {
        posts.push(JSON.parse(String(init.body)));
        return new Response(JSON.stringify(post.body), { status: post.status });
      }
      if (/\/dial\/[^/]+$/.test(path)) {
        polls.push(path);
        const state = states[Math.min(index, states.length - 1)] ?? {
          status: "sent",
        };
        index += 1;
        return new Response(JSON.stringify(state));
      }
      return new Response("{}", { status: 404 });
    }),
  );
  return { posts, polls };
}

function renderButton(number = "+998901234567") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>
        <RemoteDialButton number={number} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

/** Let fetches/react-query settle under fake timers. */
const flush = (ms = 20) => act(() => vi.advanceTimersByTimeAsync(ms));

async function openModal() {
  await flush();
  fireEvent.click(screen.getByTestId("remote-dial"));
  await flush();
  return screen.getByTestId("dial-modal");
}

async function startCall() {
  fireEvent.click(screen.getByTestId("dial-start"));
  await flush();
}

const statusLine = () => screen.getByTestId("dial-status");

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("RemoteDialButton", () => {
  it.each([
    ["no devices", { devices: [] }],
    ["devices request fails", { devicesStatus: 500 }],
    ["envelope without devices", { devices: { success: true } }],
  ])("is hidden when %s", async (_label, options) => {
    vi.useFakeTimers();
    stubApi(options as Parameters<typeof stubApi>[0]);
    renderButton();
    await flush(50);
    expect(screen.queryByTestId("remote-dial")).not.toBeInTheDocument();
  });

  it("lists devices, preselects the single online one, disables offline", async () => {
    vi.useFakeTimers();
    stubApi();
    renderButton();
    const modal = await openModal();
    expect(within(modal).getByTestId("dial-number")).toHaveValue(
      "+998 90 123-45-67",
    );

    const online = within(screen.getByTestId("dial-device-dev-a")).getByRole(
      "radio",
    );
    const offline = within(screen.getByTestId("dial-device-dev-b")).getByRole(
      "radio",
    );
    expect(online).toBeChecked();
    expect(offline).toBeDisabled();
    expect(screen.getByTestId("dial-device-dev-a")).toHaveTextContent(
      "Aziza Karimova · TECNO Spark 20",
    );
    expect(screen.getByTestId("dial-device-dev-b")).toHaveTextContent("oflayn");
    expect(screen.getByTestId("dial-start")).toBeEnabled();
  });

  it("no preselect with two online devices; the call button waits for a choice", async () => {
    vi.useFakeTimers();
    stubApi({
      devices: [ONLINE, { ...OFFLINE, device_id: "dev-c", online: true }],
    });
    renderButton();
    await openModal();
    expect(screen.getByTestId("dial-start")).toBeDisabled();
    fireEvent.click(
      within(screen.getByTestId("dial-device-dev-c")).getByRole("radio"),
    );
    expect(screen.getByTestId("dial-start")).toBeEnabled();
  });

  it("posts digits + a fresh idempotency key and follows the status live", async () => {
    vi.useFakeTimers();
    const { posts, polls } = stubApi({
      states: [
        { status: "received", used_sim_slot: 1 },
        { status: "dialing" },
        { status: "active" },
        { status: "disconnected", duration_sec: 65, cause: "normal" },
      ],
    });
    renderButton();
    await openModal();
    await startCall();

    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatchObject({
      device_id: "dev-a",
      number: "+998901234567",
    });
    expect(typeof posts[0].idempotency_key).toBe("string");
    expect(String(posts[0].idempotency_key).length).toBeGreaterThan(8);

    expect(statusLine()).toHaveTextContent("Telefonga yuborildi…");
    await flush(1000);
    expect(statusLine()).toHaveTextContent("Telefon qabul qildi (SIM 2)");
    await flush(1000);
    expect(statusLine()).toHaveTextContent("Terilmoqda…");
    await flush(1000);
    expect(statusLine()).toHaveTextContent("Suhbat davom etmoqda");
    await flush(1000);
    expect(statusLine()).toHaveTextContent("Tugadi (1:05, normal)");
    expect(screen.getByText(/standart qo'ng'iroq ilovasi/)).toBeInTheDocument();

    // Final → polling stops.
    const count = polls.length;
    await flush(5000);
    expect(polls.length).toBe(count);

    // A new call gets a new idempotency key.
    fireEvent.click(screen.getByTestId("dial-again"));
    await flush();
    await startCall();
    expect(posts).toHaveLength(2);
    expect(posts[1].idempotency_key).not.toBe(posts[0].idempotency_key);
  });

  it("shows 'device asks for SIM' when sim_mode is ask", async () => {
    vi.useFakeTimers();
    stubApi({ states: [{ status: "received", sim_mode: "ask" }] });
    renderButton();
    await openModal();
    await startCall();
    await flush(1000);
    expect(statusLine()).toHaveTextContent(
      "Telefon qabul qildi (qurilma SIM so'raydi)",
    );
  });

  it.each([
    ["permission_denied", "Telefonda qo'ng'iroq ruxsati yo'q"],
    ["invalid_number", "Raqam noto'g'ri"],
    ["another_call_active", "Telefonda boshqa qo'ng'iroq bor"],
    ["sim_disabled", "Ilovada SIM o'chirilgan"],
    ["duplicate", "Bu buyruq allaqachon bajarilgan"],
    ["feature_disabled", "Operator masofaviy qo'ng'iroqni o'chirgan"],
    ["user_declined", "Operator qo'ng'iroqni rad etdi"],
    ["timeout", "Operator 30 soniya ichida tasdiqlamadi"],
    ["something_new", "Telefon buyruqni rad etdi"],
  ])("rejected: %s", async (reason, text) => {
    vi.useFakeTimers();
    stubApi({ states: [{ status: "rejected", reject_reason: reason }] });
    renderButton();
    await openModal();
    await startCall();
    await flush(1000);
    expect(statusLine()).toHaveAttribute("data-status", "rejected");
    expect(statusLine()).toHaveTextContent(text);
  });

  it("expired → 'Telefon javob bermadi'", async () => {
    vi.useFakeTimers();
    stubApi({ states: [{ status: "expired" }] });
    renderButton();
    await openModal();
    await startCall();
    await flush(1000);
    expect(statusLine()).toHaveTextContent("Telefon javob bermadi");
  });

  it("409 device offline → 'Telefon onlayn emas', no polling", async () => {
    vi.useFakeTimers();
    const { polls } = stubApi({
      post: {
        status: 409,
        body: {
          success: false,
          error_code: "device_offline",
          command_id: "cmd-9",
          status: "offline",
          message: "offline",
        },
      },
    });
    renderButton();
    await openModal();
    await startCall();
    expect(statusLine()).toHaveTextContent("Telefon onlayn emas");
    await flush(3000);
    expect(polls).toHaveLength(0);
  });

  it("429 → rate-limit message, still on the form", async () => {
    vi.useFakeTimers();
    stubApi({
      post: {
        status: 429,
        body: { success: false, error_code: "THROTTLED", message: "x" },
      },
    });
    renderButton();
    await openModal();
    await startCall();
    expect(screen.getByTestId("dial-error")).toHaveTextContent(
      "So'rovlar juda ko'p",
    );
    expect(screen.getByTestId("dial-start")).toBeEnabled();
  });

  it.each([
    ["invalid number"],
    ["Bu yo'nalishga masofaviy qo'ng'iroq ruxsat etilmagan"],
  ])("400 → the backend's message verbatim: %s", async (message) => {
    vi.useFakeTimers();
    stubApi({
      post: {
        status: 400,
        body: { success: false, error_code: "MISSING_FIELD", message },
      },
    });
    renderButton("+79001234567");
    await openModal();
    await startCall();
    expect(screen.getByTestId("dial-error")).toHaveTextContent(message);
    expect(screen.getByTestId("dial-start")).toBeEnabled();
  });

  it("'Telefon qabul qildi' tells that the operator must confirm", async () => {
    vi.useFakeTimers();
    stubApi({ states: [{ status: "received" }, { status: "dialing" }] });
    renderButton();
    await openModal();
    await startCall();
    expect(screen.queryByTestId("dial-confirm-note")).not.toBeInTheDocument();
    await flush(1000);
    expect(statusLine()).toHaveTextContent("Telefon qabul qildi");
    expect(screen.getByTestId("dial-confirm-note")).toHaveTextContent(
      "Operator telefonda tasdiqlashi kerak",
    );
    await flush(1000);
    expect(screen.queryByTestId("dial-confirm-note")).not.toBeInTheDocument();
  });

  it.each([
    ["12", "too short"],
    ["+9989012345678901", "more than 15 digits"],
    ["+99890abc1234", "letters"],
    ["*99#1234567", "USSD-like characters"],
  ])("pre-check blocks %s (%s) with a hint", async (number) => {
    vi.useFakeTimers();
    const { posts } = stubApi();
    renderButton(number);
    await openModal();
    expect(screen.getByTestId("dial-number")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByTestId("dial-number-hint")).toHaveTextContent(
      "Faqat raqamlar va + belgisi (7–15 ta raqam)",
    );
    expect(screen.getByTestId("dial-start")).toBeDisabled();
    fireEvent.click(screen.getByTestId("dial-start"));
    await flush();
    expect(posts).toHaveLength(0);
  });

  it("formatted input is accepted and sent as digits", async () => {
    vi.useFakeTimers();
    const { posts } = stubApi();
    renderButton();
    await openModal();
    fireEvent.change(screen.getByTestId("dial-number"), {
      target: { value: " +998 (90) 123-45.67 " },
    });
    expect(screen.queryByTestId("dial-number-hint")).not.toBeInTheDocument();
    await startCall();
    expect(posts[0].number).toBe("+998901234567");
  });
});

describe("normalizeDialNumber", () => {
  it.each([
    ["+998 90 123-45-67", "+998901234567", true],
    ["901234567", "901234567", true],
    ["1234567", "1234567", true],
    ["123456", "123456", false],
    ["+1234567890123456", "+1234567890123456", false],
    ["++998901234567", "++998901234567", false],
    ["99890123+4567", "99890123+4567", false],
    ["+99890abc", "+99890abc", false],
  ])("%j → %j (valid: %s)", (raw, value, valid) => {
    expect(normalizeDialNumber(raw)).toEqual({ value, valid });
  });
});
