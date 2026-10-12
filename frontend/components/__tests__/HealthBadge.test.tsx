import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HealthBadge } from "@/components/HealthBadge";

// React picks its dev/prod build from NODE_ENV at load time, and RTL's act()
// only exists in the dev build. A shell with NODE_ENV=production (e.g. a
// prod-like dev box) would otherwise fail every render. vi.hoisted runs ahead
// of the imports above, so React loads its dev build.
vi.hoisted(() => {
  vi.stubEnv("NODE_ENV", "test");
});

describe("HealthBadge", () => {
  it("renders the default label", () => {
    render(<HealthBadge />);
    expect(screen.getByRole("status")).toHaveTextContent("healthy");
  });

  it("renders a custom label", () => {
    render(<HealthBadge label="ok" />);
    expect(screen.getByText("ok")).toBeInTheDocument();
  });
});
