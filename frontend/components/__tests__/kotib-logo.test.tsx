/** Kotib mark: two logos on one page get distinct gradient ids that their
 * own path references; the landing tile shows the mark + wordmark and opens
 * kotib.ai in a new tab. */

import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KotibLogo } from "@/components/KotibLogo";
import { IntegrationsSection } from "@/components/landing/IntegrationsSection";

afterEach(() => vi.unstubAllGlobals());

describe("KotibLogo", () => {
  it("keeps the original viewBox and gives each instance its own gradient id", () => {
    render(
      <>
        <KotibLogo className="h-6" />
        <KotibLogo />
      </>,
    );
    const logos = screen.getAllByTestId("kotib-logo");
    expect(logos).toHaveLength(2);
    const ids = logos.map((svg) => {
      expect(svg).toHaveAttribute("viewBox", "0 0 617 410");
      const id = svg.querySelector("radialGradient")!.getAttribute("id")!;
      // The gradient-filled path points at this instance's own defs.
      expect(svg.querySelector("path")).toHaveAttribute("fill", `url(#${id})`);
      return id;
    });
    expect(ids[0]).not.toBe(ids[1]);
    expect(logos[0]).toHaveClass("h-6");
  });
});

describe("landing integrations strip", () => {
  it("renders the Kotib tile with the mark, wordmark and an external link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ success: true, entries: [] }), {
          status: 200,
        }),
      ),
    );
    render(<IntegrationsSection strings={{ title: "T", text: "X" }} />);
    // The mark is decorative inside the tile: the link reads just "Kotib".
    const link = screen.getByRole("link", { name: "Kotib" });
    expect(link).toHaveAttribute("href", "https://kotib.ai");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(link).getByTestId("kotib-logo")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(within(link).getByText("Kotib")).toBeInTheDocument();
    // Internal docs tiles stay in the same tab.
    expect(screen.getByRole("link", { name: /amoCRM/ })).not.toHaveAttribute(
      "target",
    );
  });
});
