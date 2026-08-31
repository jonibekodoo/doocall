import { NextIntlClientProvider } from "next-intl";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import en from "@/messages/en.json";
import ru from "@/messages/ru.json";
import uz from "@/messages/uz.json";
import { Sidebar } from "@/components/shell/Sidebar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cabinet",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const MESSAGES = { ru, uz, en } as const;

function renderNav(locale: keyof typeof MESSAGES) {
  return render(
    <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]}>
      <Sidebar collapsed={false} onToggle={() => {}} />
    </NextIntlClientProvider>,
  );
}

describe("Sidebar locale rendering", () => {
  it("renders Russian nav (primary, reference terminology)", () => {
    renderNav("ru");
    expect(screen.getByText("Рабочий стол")).toBeInTheDocument();
    expect(screen.getByText("Звонки")).toBeInTheDocument();
    expect(screen.getByText("Отчеты")).toBeInTheDocument();
    expect(screen.getByText("Мои звонки")).toBeInTheDocument();
  });

  it("renders Uzbek nav", () => {
    renderNav("uz");
    expect(screen.getByText("Ish stoli")).toBeInTheDocument();
    expect(screen.getByText("Qo'ng'iroqlar")).toBeInTheDocument();
  });

  it("renders English nav", () => {
    renderNav("en");
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("My calls")).toBeInTheDocument();
  });

  it("marks the active item with aria-current", () => {
    renderNav("ru");
    expect(screen.getByRole("link", { name: /Рабочий стол/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
