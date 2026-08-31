import { execSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/** End-to-end smoke against the live compose stack.
 * Each run registers throwaway companies (unique suffix) via the real API. */

const runId = `${Date.now()}`.slice(-8);
const password = "e2e-password-1";

function companyFor(tag: string) {
  return {
    company_name: `E2E ${tag} ${runId}`,
    admin_email: `e2e-${tag}-${runId}@test.uz`,
    phone: "+998901234567",
    password,
  };
}

/** Suspend a company directly through Django (test fixture manipulation). */
function suspendCompany(slugFragment: string) {
  execSync(
    `docker compose exec -T backend python manage.py shell -c "` +
      `from apps.companies.models import Company; ` +
      `c = Company.objects.get(slug__contains='${slugFragment}'); ` +
      `c.status='suspended'; c.save(update_fields=['status'])"`,
    { cwd: "..", stdio: "pipe" },
  );
}

test.describe("register → cabinet → logout → login", () => {
  test("full auth loop lands in the cabinet shell", async ({
    page,
  }, testInfo) => {
    const creds = companyFor(`main-${testInfo.project.name}`);

    await page.goto("/register");
    await page.getByLabel(/компан|company|kompaniya/i).fill(creds.company_name);
    await page.locator('input[name="admin_email"]').fill(creds.admin_email);
    await page.locator('input[name="phone"]').fill(creds.phone);
    await page.locator('input[name="password"]').fill(creds.password);
    await page.locator('button[type="submit"]').click();

    // Registration auto-logs-in → cabinet shell.
    await expect(page.getByTestId("cabinet-shell")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("topbar")).toBeVisible();

    // Sidebar on ≥640px, mobile strip below.
    if (testInfo.project.name === "mobile-380") {
      await expect(page.getByTestId("mobile-nav")).toBeVisible();
    } else {
      await expect(page.getByTestId("sidebar")).toBeVisible();
    }

    await page.screenshot({
      path: `../docs/screenshots/phase6-shell-${testInfo.project.name}.png`,
      fullPage: false,
    });

    // Logout → back to login; login again → cabinet.
    await page.getByTestId("user-menu").click();
    await page.getByTestId("logout").click();
    await page.waitForURL(/\/login/, { timeout: 10_000 }).catch(async () => {
      await page.goto("/login"); // guard redirect may race; navigate explicitly
    });

    await page.goto("/login");
    await page.locator('input[name="email"]').fill(creds.admin_email);
    await page.locator('input[name="password"]').fill(creds.password);
    await page.locator('button[type="submit"]').click();
    await expect(page.getByTestId("cabinet-shell")).toBeVisible({
      timeout: 15_000,
    });
  });
});

test.describe("suspended company", () => {
  test("shows the paywall screen with amounts", async ({ page }, testInfo) => {
    test.skip(
      testInfo.project.name !== "desktop",
      "fixture mutation once is enough",
    );

    const creds = companyFor("paywall");
    await page.goto("/register");
    await page.getByLabel(/компан|company|kompaniya/i).fill(creds.company_name);
    await page.locator('input[name="admin_email"]').fill(creds.admin_email);
    await page.locator('input[name="phone"]').fill(creds.phone);
    await page.locator('input[name="password"]').fill(creds.password);
    await page.locator('button[type="submit"]').click();
    await expect(page.getByTestId("cabinet-shell")).toBeVisible({
      timeout: 15_000,
    });

    suspendCompany(`e2e-paywall-${runId}`);

    await page.reload();
    await expect(page.getByTestId("paywall")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("paywall")).toContainText(/UZS/);
    await page.screenshot({ path: "../docs/screenshots/phase6-paywall.png" });
  });
});
