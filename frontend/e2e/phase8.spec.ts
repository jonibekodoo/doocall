import { execSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/** Phase-8 E2E: landing funnel + live pricing. */

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1440, height: 900 } });

const runId = `${Date.now()}`.slice(-6);

function backendShell(code: string) {
  execSync(
    `docker compose exec -T backend python manage.py shell -c "${code}"`,
    { cwd: "..", stdio: "pipe" },
  );
}

test.beforeAll(() => {
  // Pricing must be at the canonical 50000 and the cache cold.
  backendShell(
    "from apps.billing.models import PricingSetting; " +
      "row = PricingSetting.objects.get(company=None); " +
      "row.price_per_operator_uzs = 50000; row.save(); " +
      "from django.core.cache import cache; cache.delete('public:pricing')",
  );
});

test("full funnel: uz landing → ru → register → onboarding → operator → license", async ({
  page,
  context,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "single-project funnel");
  await context.clearCookies();

  // 1. Landing opens in UZ by default.
  await page.goto("/");
  await expect(page.getByTestId("hero-title")).toHaveText(
    "Har bir qo'ng'iroq — nazorat ostida",
  );

  // Live pricing renders and slider recomputes the total.
  await expect(page.getByTestId("unit-price")).toContainText("50", {
    timeout: 15_000,
  });
  await page.getByTestId("seat-slider").fill("10");
  await expect(page.getByTestId("monthly-total")).toContainText("500");

  // 2. Switch to RU.
  await page.getByTestId("landing-locale").getByText("ru").click();
  await expect(page.getByTestId("hero-title")).toHaveText(
    "Каждый звонок — под контролем",
    { timeout: 15_000 },
  );

  // 3. Register a fresh company from the hero CTA.
  await page.getByTestId("hero-cta").click();
  await page.locator('input[name="company_name"]').fill(`Funnel Co ${runId}`);
  await page
    .locator('input[name="admin_email"]')
    .fill(`funnel-${runId}@test.uz`);
  await page.locator('input[name="phone"]').fill("+998901234567");
  await page.locator('input[name="password"]').fill("funnel-pass-1");
  await page.locator('button[type="submit"]').click();

  // 4. Lands on the onboarding checklist.
  await expect(page.getByTestId("onboarding")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("onboarding")).toContainText(
    "Добавьте оператора",
  );

  // 5. Add an operator via settings.
  await page.goto("/cabinet/settings");
  await page.getByTestId("new-operator-name").fill(`funnel-op-${runId}`);
  await page.getByTestId("add-operator").click();
  await expect(page.getByTestId("credentials")).toBeVisible({
    timeout: 15_000,
  });
  await page.getByTestId("credentials-close").click();

  // 6. License tab: 1 seat and the trial countdown visible.
  await page.getByTestId("settings-tab-license").click();
  await expect(page.getByTestId("license-seats")).toHaveText("1", {
    timeout: 15_000,
  });
  await expect(page.getByText(/Осталось дней/)).toBeVisible();
  await expect(page.getByTestId("license-tab")).toContainText(/1[3-4]/); // ~14 left

  // 7. Onboarding step 1 now shows done; dismiss persists.
  await page.goto("/cabinet/onboarding");
  await expect(
    page.getByTestId("onboarding").getByText("Готово").first(),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("onboarding-dismiss").click();
  await page.waitForURL(/\/cabinet$/);
  await page.goto("/cabinet/onboarding");
  await page.waitForURL(/\/cabinet$/); // dismissed → bounced straight back
});

test("pricing change reflects on landing after cache TTL", async ({
  page,
  context,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "global pricing mutation");
  await context.clearCookies();
  await page.goto("/");
  await expect(page.getByTestId("unit-price")).toContainText("50", {
    timeout: 15_000,
  });

  // Admin changes the price; simulate TTL expiry by clearing the cache key.
  backendShell(
    "from apps.billing.models import PricingSetting; " +
      "row = PricingSetting.objects.get(company=None); " +
      "row.price_per_operator_uzs = 75000; row.save(); " +
      "from django.core.cache import cache; cache.delete('public:pricing')",
  );

  await page.reload();
  await expect(page.getByTestId("unit-price")).toContainText("75", {
    timeout: 15_000,
  });

  // Restore canonical pricing for subsequent runs.
  backendShell(
    "from apps.billing.models import PricingSetting; " +
      "row = PricingSetting.objects.get(company=None); " +
      "row.price_per_operator_uzs = 50000; row.save(); " +
      "from django.core.cache import cache; cache.delete('public:pricing')",
  );
});
