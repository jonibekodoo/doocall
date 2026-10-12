import { NextIntlClientProvider } from "next-intl";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import uz from "@/messages/uz.json";
import { Sidebar } from "@/components/shell/Sidebar";

const redirect = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: (url: string) => redirect(url),
}));

describe("staff monitoring is hidden", () => {
  it("sidebar has no link to /cabinet/monitoring", () => {
    render(
      <NextIntlClientProvider locale="uz" messages={uz}>
        <Sidebar collapsed={false} onToggle={() => {}} />
      </NextIntlClientProvider>,
    );
    const hrefs = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/cabinet");
    expect(hrefs).not.toContain("/cabinet/monitoring");
    expect(screen.queryByText(uz.nav.monitoring)).not.toBeInTheDocument();
  });

  it("direct URL redirects to /cabinet", async () => {
    const { default: MonitoringPage } = await import(
      "@/app/cabinet/monitoring/page"
    );
    MonitoringPage();
    expect(redirect).toHaveBeenCalledWith("/cabinet");
  });
});
