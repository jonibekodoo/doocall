/** Admin company detail: integrator row, superadmin-only reassign modal,
 * integrator history and cashback tables (API mocked). */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminCompanyDetailPage from "@/app/admin/companies/[id]/page";
import * as admin from "@/lib/api/admin";
import uz from "@/messages/uz.json";

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/companies/7",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useParams: () => ({ id: "7" }),
}));

const auth = vi.hoisted(() => ({ role: "superadmin" }));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: { role: auth.role }, status: "authenticated" }),
}));

vi.mock("@/lib/api/admin", () => ({
  companyAction: vi.fn(),
  deleteAdminCompany: vi.fn(),
  fetchAdminCompany: vi.fn(),
  fetchCompanyIntegratorHistory: vi.fn(),
  fetchIntegrators: vi.fn(),
  impersonate: vi.fn(),
  reassignCompanyIntegrator: vi.fn(),
  resetCompanyUserPassword: vi.fn(),
  updateAdminCompany: vi.fn(),
}));

const api = vi.mocked(admin);

const COMPANY = {
  id: 7,
  name: "Delever",
  slug: "delever",
  phone: "",
  status: "active",
  trial_ends_at: null,
  trial_expired: false,
  created_at: "2026-09-01T10:00:00Z",
  acquired_via: "referral",
  integrator_id: 3,
  integrator_name: "Ali Valiyev",
  integrator_company: "Soft LLC",
  integrations_count: 0,
  audio_retention_days: null,
  seats: 5,
  subscription_status: "active",
  period_end: null,
  operators: [],
  payments: [],
  users: [],
  integrations: [],
  autopay: null,
  cashbacks: [
    {
      id: 41,
      payment_id: 900,
      integrator_id: 3,
      integrator_name: "Ali Valiyev",
      percent: "20.00",
      amount_uzs: 120000,
      status: "accrued",
      created_at: "2026-10-01T09:30:00Z",
    },
  ],
};

const HISTORY = [
  {
    id: 5,
    at: "2026-10-02T12:00:00Z",
    actor: { id: 1, email: "root@doocall.uz" },
    from: null,
    to: { id: 3, name: "Ali Valiyev", company_name: "Soft LLC" },
    note: "shartnoma bo'yicha",
  },
];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="uz" messages={uz}>
        <AdminCompanyDetailPage />
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.role = "superadmin";
  api.fetchAdminCompany.mockResolvedValue({
    success: true,
    company: COMPANY,
  } as unknown as Awaited<ReturnType<typeof admin.fetchAdminCompany>>);
  api.fetchCompanyIntegratorHistory.mockResolvedValue({
    success: true,
    history: HISTORY,
  });
  api.fetchIntegrators.mockResolvedValue({
    success: true,
    integrators: [
      {
        id: 3,
        name: "Ali Valiyev",
        company_name: "Soft LLC",
        status: "active",
      },
      {
        id: 9,
        name: "Bek Karimov",
        company_name: "Tech Group",
        status: "active",
      },
      { id: 11, name: "Blocked One", company_name: "X", status: "suspended" },
    ],
  } as unknown as Awaited<ReturnType<typeof admin.fetchIntegrators>>);
});

describe("admin company detail — integrator", () => {
  it("shows the integrator name linking to the integrator page", async () => {
    renderPage();
    const link = await screen.findByTestId("company-integrator-link");
    expect(link).toHaveTextContent("Ali Valiyev (Soft LLC)");
    expect(link).toHaveAttribute("href", "/admin/integrators/3");
    expect(screen.queryByText(/#3 ·/)).not.toBeInTheDocument();
  });

  it("hides the reassign button for non-superadmins", async () => {
    auth.role = "admin";
    renderPage();
    await screen.findByTestId("company-integrator-link");
    expect(
      screen.queryByTestId("reassign-integrator-btn"),
    ).not.toBeInTheDocument();
  });

  it("submits the chosen active integrator with the note", async () => {
    api.reassignCompanyIntegrator.mockResolvedValue({
      success: true,
    } as unknown as Awaited<
      ReturnType<typeof admin.reassignCompanyIntegrator>
    >);
    renderPage();
    fireEvent.click(await screen.findByTestId("reassign-integrator-btn"));
    expect(
      screen.getByText(/keyingi to'lovlar keshbeki yangi integratorga/),
    ).toBeInTheDocument();

    await screen.findByTestId("integrator-option-9");
    // Only active integrators are offered.
    expect(
      screen.queryByTestId("integrator-option-11"),
    ).not.toBeInTheDocument();
    // Search narrows the list.
    fireEvent.change(screen.getByTestId("integrator-search"), {
      target: { value: "tech" },
    });
    expect(screen.queryByTestId("integrator-option-3")).not.toBeInTheDocument();
    // Keeping the current integrator can't be submitted.
    expect(screen.getByTestId("reassign-submit")).toBeDisabled();

    fireEvent.click(screen.getByTestId("integrator-option-9"));
    fireEvent.change(screen.getByTestId("integrator-note"), {
      target: { value: "  yangi shartnoma " },
    });
    fireEvent.click(screen.getByTestId("reassign-submit"));
    await waitFor(() =>
      expect(api.reassignCompanyIntegrator).toHaveBeenCalledWith(7, {
        integrator_id: 9,
        note: "yangi shartnoma",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("reassign-submit")).not.toBeInTheDocument(),
    );
    // Detail + history are refetched.
    expect(api.fetchCompanyIntegratorHistory).toHaveBeenCalledTimes(2);
  });

  it("can remove the integrator (null)", async () => {
    api.reassignCompanyIntegrator.mockResolvedValue({
      success: true,
    } as unknown as Awaited<
      ReturnType<typeof admin.reassignCompanyIntegrator>
    >);
    renderPage();
    fireEvent.click(await screen.findByTestId("reassign-integrator-btn"));
    fireEvent.click(screen.getByTestId("integrator-option-none"));
    fireEvent.click(screen.getByTestId("reassign-submit"));
    await waitFor(() =>
      expect(api.reassignCompanyIntegrator).toHaveBeenCalledWith(7, {
        integrator_id: null,
      }),
    );
  });

  it("shows the backend error message and keeps the modal open", async () => {
    api.reassignCompanyIntegrator.mockRejectedValue(
      new Error("Integrator faol emas"),
    );
    renderPage();
    fireEvent.click(await screen.findByTestId("reassign-integrator-btn"));
    fireEvent.click(await screen.findByTestId("integrator-option-9"));
    fireEvent.click(screen.getByTestId("reassign-submit"));
    expect(await screen.findByTestId("reassign-error")).toHaveTextContent(
      "Integrator faol emas",
    );
    expect(screen.getByTestId("reassign-submit")).toBeInTheDocument();
  });

  it("renders the history and cashback tables", async () => {
    renderPage();
    const row = await screen.findByTestId("history-row-5");
    expect(row).toHaveTextContent("root@doocall.uz");
    expect(row).toHaveTextContent("— → Ali Valiyev (Soft LLC)");
    expect(row).toHaveTextContent("shartnoma bo'yicha");

    const cashback = within(
      screen.getByTestId("company-cashbacks"),
    ).getByTestId("cashback-row-41");
    expect(cashback).toHaveTextContent("#900");
    expect(cashback).toHaveTextContent("Ali Valiyev");
    expect(cashback).toHaveTextContent("20%");
    expect(cashback).toHaveTextContent(/120\D000 UZS/);
    expect(cashback).toHaveTextContent("Hisoblangan");
  });

  it("shows empty states", async () => {
    api.fetchCompanyIntegratorHistory.mockResolvedValue({
      success: true,
      history: [],
    });
    api.fetchAdminCompany.mockResolvedValue({
      success: true,
      company: {
        ...COMPANY,
        integrator_id: null,
        integrator_name: null,
        cashbacks: [],
      },
    } as unknown as Awaited<ReturnType<typeof admin.fetchAdminCompany>>);
    renderPage();
    expect(
      await screen.findByText("Integrator hali o'zgartirilmagan"),
    ).toBeInTheDocument();
    expect(screen.getByText("Keshbeklar yo'q")).toBeInTheDocument();
    expect(screen.getByTestId("reassign-integrator-btn")).toHaveTextContent(
      "Integrator biriktirish",
    );
  });
});
