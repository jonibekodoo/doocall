import { describe, expect, it } from "vitest";

import { buildCallsQuery } from "@/lib/filters";

describe("buildCallsQuery", () => {
  it("returns empty string for no filters", () => {
    expect(buildCallsQuery({})).toBe("");
  });

  it("maps every filter to the backend param names", () => {
    const qs = buildCallsQuery({
      employees: [3, 7],
      dateFrom: "2026-08-01",
      dateTo: "2026-08-14",
      direction: "inbound",
      status: "answered",
      search: "Aziz",
      minDuration: 30,
      simSlot: 0,
      page: 2,
      ordering: "-duration",
    });
    const params = new URLSearchParams(qs.slice(1));
    expect(params.get("employees")).toBe("3,7");
    expect(params.get("date_from")).toBe("2026-08-01");
    expect(params.get("date_to")).toBe("2026-08-14");
    expect(params.get("direction")).toBe("inbound");
    expect(params.get("status")).toBe("answered");
    expect(params.get("search")).toBe("Aziz");
    expect(params.get("min_duration")).toBe("30");
    expect(params.get("sim_slot")).toBe("0");
    expect(params.get("page")).toBe("2");
    expect(params.get("ordering")).toBe("-duration");
  });

  it("omits empty and default values", () => {
    expect(
      buildCallsQuery({ employees: [], search: "  ", minDuration: 0, page: 1 }),
    ).toBe("");
  });

  it("keeps sim slot 0 but drops negative", () => {
    expect(buildCallsQuery({ simSlot: 0 })).toBe("?sim_slot=0");
    expect(buildCallsQuery({ simSlot: -1 })).toBe("");
  });

  it("trims search", () => {
    expect(buildCallsQuery({ search: "  hi  " })).toBe("?search=hi");
  });
});
