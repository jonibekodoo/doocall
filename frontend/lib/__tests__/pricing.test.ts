import { describe, expect, it } from "vitest";

import {
  clampSeats,
  computeMonthlyTotal,
  MAX_SEATS,
  MIN_SEATS,
} from "@/lib/pricing";

describe("pricing calculator", () => {
  it("computes seats × live price", () => {
    expect(computeMonthlyTotal(1, 50000)).toBe(50000);
    expect(computeMonthlyTotal(5, 50000)).toBe(250000);
    expect(computeMonthlyTotal(6, 50000)).toBe(300000); // the seeded company
    expect(computeMonthlyTotal(10, 80000)).toBe(800000); // after a price change
  });

  it("clamps seats to the slider range", () => {
    expect(clampSeats(0)).toBe(MIN_SEATS);
    expect(clampSeats(-5)).toBe(MIN_SEATS);
    expect(clampSeats(999)).toBe(MAX_SEATS);
    expect(clampSeats(Number.NaN)).toBe(MIN_SEATS);
    expect(clampSeats(7.6)).toBe(8); // rounds
  });

  it("never returns negative totals", () => {
    expect(computeMonthlyTotal(5, -100)).toBe(0);
  });
});
