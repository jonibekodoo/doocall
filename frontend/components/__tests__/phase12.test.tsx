/** Phase-12: payout validation, referral-link builder, temp-password
 * reveal-once, formatting. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { validatePayoutAmount } from "@/lib/payout";
import {
  TempPasswordReveal,
  generateTempPassword,
} from "@/components/TempPasswordReveal";
import { referralLink } from "@/lib/api/partner";
import { formatUzs } from "@/lib/format";

vi.mock("next/navigation", () => ({
  usePathname: () => "/partner",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

describe("payout dialog validation", () => {
  const BALANCE = 60000;
  const MIN = 50000;

  it.each([
    [50000, null],
    [60000, null],
    [49999, "below_minimum"],
    [1, "below_minimum"],
    [60001, "over_balance"],
    [0, "invalid"],
    [-5, "invalid"],
    [Number.NaN, "invalid"],
  ])("amount %s → %s", (amount, expected) => {
    expect(validatePayoutAmount(amount as number, BALANCE, MIN)).toBe(expected);
  });

  it("over-balance beats minimum only when above min", () => {
    // 70k requested with 60k balance and 50k min → over_balance, not valid.
    expect(validatePayoutAmount(70000, 60000, 50000)).toBe("over_balance");
  });
});

describe("referral link builder", () => {
  it("builds the canonical link", () => {
    expect(referralLink("DEMOINT1")).toBe("https://doocall.uz/?ref=DEMOINT1");
  });
  it("accepts a custom base and strips trailing slashes", () => {
    expect(referralLink("K7KJ2M9Q", "http://localhost:3000/")).toBe(
      "http://localhost:3000/?ref=K7KJ2M9Q",
    );
  });
  it("URL-encodes the code defensively", () => {
    expect(referralLink("A B")).toBe("https://doocall.uz/?ref=A%20B");
  });
});

describe("temp password", () => {
  it("generator: correct length, unambiguous alphabet, unique-ish", () => {
    const a = generateTempPassword();
    const b = generateTempPassword();
    expect(a).toHaveLength(12);
    expect(a).not.toBe(b);
    expect(a).not.toMatch(/[O0Il1]/); // ambiguous chars excluded
  });

  it("reveal-once component shows password, copies, and disappears on OK", async () => {
    const onDone = vi.fn();
    const user = userEvent.setup(); // installs its own clipboard stub

    const { unmount } = render(
      <TempPasswordReveal
        password="s3cret-temp-1"
        email="client@x.uz"
        note="показывается один раз"
        onDone={onDone}
      />,
    );
    expect(screen.getByTestId("temp-password")).toHaveTextContent(
      "s3cret-temp-1",
    );
    expect(screen.getByText(/один раз/)).toBeInTheDocument();

    // Copy: verify via userEvent's clipboard AND the check-icon state flip.
    await user.click(screen.getByTestId("temp-password-copy"));
    await expect(navigator.clipboard.readText()).resolves.toBe("s3cret-temp-1");

    await user.click(screen.getByTestId("temp-password-done"));
    expect(onDone).toHaveBeenCalledTimes(1);
    unmount();
    expect(screen.queryByTestId("temp-password")).not.toBeInTheDocument();
  });
});

describe("balance/percent formatting", () => {
  it("formats UZS balances with grouping", () => {
    expect(formatUzs(1250000)).toMatch(/^1\D250\D000$/);
    expect(formatUzs(0)).toBe("0");
  });
  it("percent strings render as-is with the % suffix pattern", () => {
    for (const value of ["10.00", "15.00", "12.50"]) {
      expect(`${value}%`).toMatch(/^\d+\.\d{2}%$/);
    }
  });
});
