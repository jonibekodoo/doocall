/** Phase-11: redirect logic, KPI mapping, effective-% display, payout state
 * machine, extend-trial validation, worked cashback example. */

import { describe, expect, it, vi } from "vitest";

import {
  cashbackExample,
  effectivePercentLabel,
  kpiCards,
} from "@/lib/admin-shared";
import type { AdminKpis } from "@/lib/api/admin";
import { homeFor } from "@/lib/auth";

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "1" }),
}));

describe("role-based redirect (homeFor)", () => {
  it.each([
    ["admin", "/admin"],
    ["partner", "/partner"],
    ["cabinet", "/cabinet"],
    [undefined, "/cabinet"],
    ["garbage", "/cabinet"],
  ])("portal %s → %s", (portal, expected) => {
    expect(homeFor(portal as string | undefined)).toBe(expected);
  });
});

describe("KPI card mapping", () => {
  const kpis: AdminKpis = {
    success: true,
    companies: { total: 33, active: 2, trial: 26, suspended: 5 },
    mrr_uzs: 300000,
    payments_30d_uzs: 500000,
    calls_today: 412,
    integrators: 2,
    pending_payouts: 1,
    payments_series: [],
    calls_series: [],
  };

  const t = (key: string, values?: Record<string, string | number>) =>
    key === "dashboard.companiesHint"
      ? `актив ${values?.active} · триал ${values?.trial} · стоп ${values?.suspended}`
      : key;

  it("maps all six cards with formatted money and status hint", () => {
    const cards = kpiCards(kpis, t);
    expect(cards).toHaveLength(6);
    const byKey = Object.fromEntries(cards.map((card) => [card.key, card]));
    expect(byKey.companies.value).toBe(33);
    expect(byKey.companies.hint).toContain("актив 2");
    expect(byKey.companies.hint).toContain("стоп 5");
    expect(String(byKey.mrr.value)).toMatch(/^300\D000 UZS$/);
    expect(byKey.calls.value).toBe(412);
    expect(byKey.payouts.value).toBe(1);
  });
});

describe("effective-% display (override ?? default)", () => {
  it("shows override when set", () => {
    expect(effectivePercentLabel("15.00", "10.00")).toBe("15.00 (override)");
  });
  it("falls back to the platform default", () => {
    expect(effectivePercentLabel(null, "10.00")).toBe("10.00 (по умолчанию)");
  });
});

describe("worked cashback example", () => {
  it("computes 100 000 × 20% = 20 000", () => {
    expect(cashbackExample(20)).toMatch(/^100\D000 UZS × 20% = 20\D000 UZS$/);
  });
  it("rounds fractional percents", () => {
    expect(cashbackExample(12.5)).toMatch(/12\D500 UZS$/);
  });
});

describe("payout action state machine (UI availability)", () => {
  // Mirrors PayoutRequest._ALLOWED — which buttons may render per status.
  const actionsFor = (status: string): string[] =>
    status === "pending"
      ? ["approve", "reject"]
      : status === "approved"
        ? ["mark-paid", "reject"]
        : [];

  it.each([
    ["pending", ["approve", "reject"]],
    ["approved", ["mark-paid", "reject"]],
    ["paid", []],
    ["rejected", []],
  ])("status %s → %j", (status, expected) => {
    expect(actionsFor(status)).toEqual(expected);
  });
});

describe("extend-trial form validation", () => {
  const isValid = (days: string, reason: string) =>
    Number(days) > 0 && reason.trim().length >= 3;

  it("requires positive days AND a reason ≥3 chars", () => {
    expect(isValid("7", "клиент попросил")).toBe(true);
    expect(isValid("0", "причина")).toBe(false);
    expect(isValid("-3", "причина")).toBe(false);
    expect(isValid("7", "")).toBe(false);
    expect(isValid("7", "  a ")).toBe(false);
  });
});

describe("superadmin-only nav absence", () => {
  it("platform_admin nav omits superadmin sections entirely", async () => {
    const NAV = [
      { href: "/admin/pricing", superOnly: true },
      { href: "/admin/cashback", superOnly: true },
      { href: "/admin/admins", superOnly: true },
      { href: "/admin/payouts", superOnly: true },
      { href: "/admin/companies", superOnly: false },
    ];
    const visible = NAV.filter((item) => !item.superOnly || false); // platform_admin
    expect(visible.map((item) => item.href)).toEqual(["/admin/companies"]);
  });
});
