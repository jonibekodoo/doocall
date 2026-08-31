import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HealthBadge } from "@/components/HealthBadge";

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
