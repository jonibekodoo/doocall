/** AI Tahlil (Kotib): page states, list, detail rendering, helpers and the
 * Calls-page AI badge — all against mocked web API endpoints. */

import { NextIntlClientProvider } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AiAnalysisDetailPage from "@/app/cabinet/ai/[id]/page";
import {
  formatAnswer,
  parseTranscript,
  scoreTone,
} from "@/app/cabinet/ai/ai-shared";
import AiAnalysisPage from "@/app/cabinet/ai/page";
import CallsPage from "@/app/cabinet/calls/page";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet/ai",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "7" }),
}));

type Routes = Record<string, unknown>;

/** Stub fetch by path suffix (query string ignored); records requested URLs. */
function stubApi(routes: Routes) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      const path = url.split("?")[0];
      const key = Object.keys(routes).find((suffix) => path.endsWith(suffix));
      const body = key ? routes[key] : { success: true, report: [] };
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
  return urls;
}

function renderUi(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="uz" messages={uz}>
      <QueryClientProvider client={client}>{node}</QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const status = (over: Partial<Record<string, boolean>> = {}) => ({
  success: true,
  kotib_connected: true,
  has_analyses: true,
  is_admin: false,
  ...over,
});

const LIST = {
  success: true,
  count: 2,
  pages: 1,
  page: 1,
  summary: { count: 2, avg_score: 61.25, violations: 1 },
  analyses: [
    {
      id: 7,
      call_id: 70,
      start_time: "2026-10-14T09:15:00+05:00",
      operator: { id: 3, full_name: "Aziza Karimova" },
      phone: "+998901234567",
      final_score: 87,
      summary: "Mijoz narx haqida so'radi, operator to'liq javob berdi.",
      has_violation: false,
    },
    {
      id: 8,
      call_id: null,
      start_time: "2026-10-14T10:00:00+05:00",
      operator: null,
      phone: "+992901234567",
      final_score: -5,
      summary: "Operator qo'pollik qildi.",
      has_violation: true,
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

describe("AI Tahlil page states", () => {
  it("not connected, no history: contact-admin screen without settings link for operators", async () => {
    stubApi({
      "/ai/status": status({ kotib_connected: false, has_analyses: false }),
    });
    renderUi(<AiAnalysisPage />);
    expect(await screen.findByTestId("ai-not-connected")).toBeInTheDocument();
    expect(screen.getByText("AI tahlil yoqilmagan")).toBeInTheDocument();
    expect(
      screen.getByText(/administratorga murojaat qiling/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("ai-open-settings")).not.toBeInTheDocument();
  });

  it("company admins also get a link to the Kotib settings", async () => {
    stubApi({
      "/ai/status": status({
        kotib_connected: false,
        has_analyses: false,
        is_admin: true,
      }),
    });
    renderUi(<AiAnalysisPage />);
    expect(await screen.findByTestId("ai-open-settings")).toHaveAttribute(
      "href",
      "/cabinet/settings/integrations/kotib",
    );
  });

  it("disconnected with history: banner + list", async () => {
    stubApi({
      "/ai/status": status({ kotib_connected: false }),
      "/ai/analyses": LIST,
    });
    renderUi(<AiAnalysisPage />);
    expect(
      await screen.findByTestId("ai-disconnected-banner"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Aziza Karimova")).toBeInTheDocument();
  });

  it("connected but nothing yet: waiting message", async () => {
    stubApi({ "/ai/status": status({ has_analyses: false }) });
    renderUi(<AiAnalysisPage />);
    expect(await screen.findByTestId("ai-empty")).toHaveTextContent(
      "Tahlillar hali kelmagan",
    );
  });
});

describe("AI analyses list", () => {
  it("renders tiles, rows with score tones, violation icon and detail links", async () => {
    stubApi({ "/ai/status": status(), "/ai/analyses": LIST });
    renderUi(<AiAnalysisPage />);

    expect(await screen.findByText("Aziza Karimova")).toBeInTheDocument();
    expect(screen.getByText("61.3")).toBeInTheDocument(); // avg, 1 decimal
    expect(screen.getByText("+998 90 123-45-67")).toBeInTheDocument();
    expect(screen.getByText("+992 90 123-45-67")).toBeInTheDocument();

    const scores = screen.getAllByTestId("ai-score");
    expect(
      scores.map((badge) => [badge.textContent, badge.dataset.tone]),
    ).toEqual([
      ["87", "good"],
      ["-5", "bad"],
    ]);
    expect(screen.getByTestId("ai-violation-8")).toBeInTheDocument();
    expect(screen.queryByTestId("ai-violation-7")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /narx haqida/ })).toHaveAttribute(
      "href",
      "/cabinet/ai/7",
    );
  });

  it("sends the applied filters to the API", async () => {
    const urls = stubApi({ "/ai/status": status(), "/ai/analyses": LIST });
    renderUi(<AiAnalysisPage />);
    await screen.findByText("Aziza Karimova");
    const user = userEvent.setup();
    await user.type(screen.getByTestId("ai-min-score"), "50");
    await user.type(screen.getByTestId("ai-max-score"), "79");
    await user.click(screen.getByTestId("ai-only-violations"));
    await user.click(screen.getByTestId("ai-apply"));

    await vi.waitFor(() => {
      const last = urls.filter((url) => url.includes("/ai/analyses")).at(-1)!;
      const query = new URL(last, "http://x").searchParams;
      expect(query.get("min_score")).toBe("50");
      expect(query.get("max_score")).toBe("79");
      expect(query.get("violations")).toBe("1");
      expect(query.get("date_from")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });
});

const DETAIL = {
  success: true,
  analysis: {
    ...LIST.analyses[0],
    end_time: "2026-10-14T09:18:00+05:00",
    conversation_text:
      "Agent: Assalomu alaykum, DooCall kompaniyasi. 00:01\n\nClient: Narxlar qancha? 00:06\n\n[tizim izohi]",
    prompt_scores: [
      {
        key: "greeting",
        name: "Salomlashish",
        score: 100,
        comment_html: "<p>Operator <strong>to'g'ri</strong> salomlashdi.</p>",
        is_violation: false,
      },
      {
        key: "rudeness",
        name: "Odob",
        score: 20,
        comment_html: "",
        is_violation: true,
      },
    ],
    client_data: {
      phone_number: "+998901234567",
      summary: "Narxga qiziqqan yangi mijoz.",
      answers: [
        { key: "products", name: "Mahsulotlar", value: ["CRM", "Telefoniya"] },
        { key: "ready", name: "Sotib olishga tayyor", value: true },
        { key: "budget", name: "Byudjet", value: null },
        { key: "empty", name: "Bo'sh ro'yxat", value: [] },
      ],
    },
    call: { id: 70, duration: 185, direction: "inbound", has_audio: true },
    signature_verified: false,
    received_at: "2026-10-14T09:20:00+05:00",
  },
};

describe("AI analysis detail", () => {
  it("renders header, criteria comment HTML, transcript bubbles and portrait", async () => {
    stubApi({ "/ai/analyses/7": DETAIL });
    renderUi(<AiAnalysisDetailPage />);

    expect(await screen.findByTestId("ai-detail")).toBeInTheDocument();
    expect(screen.getAllByTestId("ai-score")[0]).toHaveTextContent("87");
    expect(screen.getByTestId("ai-unsigned")).toBeInTheDocument();
    // Our own player for the stored call (never Kotib's audio URL).
    expect(
      within(screen.getByTestId("ai-audio")).getByTestId("row-audio"),
    ).toBeInTheDocument();

    // Comment HTML is rendered as markup, not escaped text.
    const comment = screen.getByTestId("ai-comment-greeting");
    expect(comment.querySelector("strong")).toHaveTextContent("to'g'ri");
    expect(screen.queryByTestId("ai-comment-rudeness")).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId("ai-criterion-rudeness")).getByText(
        "Qoidabuzarlik",
      ),
    ).toBeInTheDocument();

    const turns = screen.getAllByTestId("ai-turn");
    expect(turns.map((turn) => turn.dataset.speaker)).toEqual([
      "agent",
      "client",
      "other",
    ]);
    expect(turns[0]).toHaveTextContent(
      "Assalomu alaykum, DooCall kompaniyasi.",
    );
    expect(turns[0]).toHaveTextContent("00:01");
    expect(turns[1]).toHaveTextContent("Narxlar qancha?");
    expect(turns[1]).toHaveTextContent("00:06");

    const answers = screen.getByTestId("ai-answers");
    const value = (name: string) =>
      within(answers).getByText(name).closest("tr")!.querySelector("td")!
        .textContent;
    expect(value("Mahsulotlar")).toBe("CRM, Telefoniya");
    expect(value("Sotib olishga tayyor")).toBe("Ha");
    expect(value("Byudjet")).toBe("—");
    expect(value("Bo'sh ro'yxat")).toBe("—");
  });
});

describe("AI helpers", () => {
  it("scoreTone thresholds", () => {
    expect([100, 80, 79, 50, 49, 0, -10].map(scoreTone)).toEqual([
      "good",
      "good",
      "mid",
      "mid",
      "bad",
      "bad",
      "bad",
    ]);
  });

  it("parseTranscript handles CRLF, missing timestamps and unknown speakers", () => {
    expect(
      parseTranscript(
        "agent: Salom\r\n\r\nCLIENT: Ha, eshitaman 1:02:03\n\n\nNoma'lum",
      ),
    ).toEqual([
      { speaker: "agent", text: "Salom", time: null },
      { speaker: "client", text: "Ha, eshitaman", time: "1:02:03" },
      { speaker: "other", text: "Noma'lum", time: null },
    ]);
    expect(parseTranscript("   ")).toEqual([]);
  });

  it("formatAnswer", () => {
    const labels = { yes: "Ha", no: "Yo'q" };
    expect(formatAnswer(false, labels)).toBe("Yo'q");
    expect(formatAnswer(undefined, labels)).toBe("—");
    expect(formatAnswer("", labels)).toBe("—");
    expect(formatAnswer(42, labels)).toBe("42");
    expect(formatAnswer([true, null, "x"], labels)).toBe("Ha, x");
    expect(formatAnswer({ a: 1 }, labels)).toBe('{"a":1}');
  });
});

describe("Calls page AI badge", () => {
  it("links scored calls to their analysis and shows nothing for the rest", async () => {
    const row = {
      call_id: "c",
      direction: "inbound",
      status: "answered",
      operator_id: 3,
      operator_name: "Aziza",
      operator_number: "",
      counterparty_number: "+998901234567",
      counterparty_name: null,
      duration: 60,
      start_time: "2026-10-14T09:15:00+05:00",
      has_location: false,
      crm: [],
    };
    stubApi({
      "/calls": {
        success: true,
        count: 2,
        page: 1,
        pages: 1,
        page_size: 20,
        results: [
          { ...row, id: 70, ai: { analysis_id: 7, final_score: 64 } },
          { ...row, id: 71, ai: null },
        ],
      },
    });
    renderUi(<CallsPage />);
    const badge = await screen.findByTestId("call-ai-7");
    expect(badge).toHaveAttribute("href", "/cabinet/ai/7");
    expect(badge).toHaveTextContent("AI 64");
    expect(screen.getAllByText(/^AI \d+$/)).toHaveLength(1);
  });
});
