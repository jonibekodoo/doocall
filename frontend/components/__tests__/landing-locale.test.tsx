/** Landing locale strings: uz default, ru/en switch (message-level check —
 * the page itself is a server component; locale pick is covered by E2E). */

import { describe, expect, it } from "vitest";

import en from "@/messages/en.json";
import ru from "@/messages/ru.json";
import uz from "@/messages/uz.json";

describe("landing locale catalogs", () => {
  it("uz (default) carries the primary value prop", () => {
    expect(uz.landing.heroTitle).toBe("Har bir qo'ng'iroq — nazorat ostida");
    expect(uz.landing.heroCta).toContain("14 kun");
  });

  it("ru and en are complete mirrors of the uz key set", () => {
    const keys = Object.keys(uz.landing).sort();
    expect(Object.keys(ru.landing).sort()).toEqual(keys);
    expect(Object.keys(en.landing).sort()).toEqual(keys);
  });

  it("ru switch shows Russian copy", () => {
    expect(ru.landing.heroTitle).toBe("Каждый звонок — под контролем");
    expect(ru.landing.pricingTitle).toBe("Цена — простая");
  });

  it("pricing trial string keeps the {days} placeholder in every locale", () => {
    for (const catalog of [uz, ru, en]) {
      expect(catalog.landing.pricingTrial).toContain("{days}");
    }
  });

  it("onboarding checklist strings exist in all locales", () => {
    for (const catalog of [uz, ru, en]) {
      expect(catalog.onboarding.step1).toBeTruthy();
      expect(catalog.onboarding.step2).toBeTruthy();
      expect(catalog.onboarding.step3).toBeTruthy();
      expect(catalog.onboarding.dismiss).toBeTruthy();
    }
  });
});
