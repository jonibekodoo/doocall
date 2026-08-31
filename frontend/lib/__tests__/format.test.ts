import { describe, expect, it } from "vitest";

import { formatDuration, formatPhone, formatUzs } from "@/lib/format";

describe("formatDuration", () => {
  it.each([
    [0, "0:00"],
    [7, "0:07"],
    [47, "0:47"],
    [60, "1:00"],
    [605, "10:05"],
    [3599, "59:59"],
    [3600, "1:00:00"],
    [3661, "1:01:01"],
    [7325, "2:02:05"],
  ])("%d s → %s", (input, expected) => {
    expect(formatDuration(input)).toBe(expected);
  });

  it("handles garbage defensively", () => {
    expect(formatDuration(-5)).toBe("0:00");
    expect(formatDuration(Number.NaN)).toBe("0:00");
    expect(formatDuration(47.9)).toBe("0:47");
  });
});

describe("formatPhone", () => {
  it("formats Uzbek E.164", () => {
    expect(formatPhone("+998901234567")).toBe("+998 90 123-45-67");
  });
  it("passes foreign numbers through", () => {
    expect(formatPhone("+12025550123")).toBe("+12025550123");
  });
  it("handles empty", () => {
    expect(formatPhone("")).toBe("—");
    expect(formatPhone(null)).toBe("—");
    expect(formatPhone(undefined)).toBe("—");
  });
});

describe("formatUzs", () => {
  it("groups thousands", () => {
    expect(formatUzs(300000)).toMatch(/^300\D000$/);
    expect(formatUzs(50000)).toMatch(/^50\D000$/);
  });
});
