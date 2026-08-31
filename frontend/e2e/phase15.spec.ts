import { expect, test, type Page } from "@playwright/test";

/** Phase-15 E2E: APK release pipeline — admin uploads a build, the landing
 * shows the download button, the file round-trips through MinIO. */

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1440, height: 900 } });

const runId = `${Date.now()}`.slice(-6);
const VERSION = `9.${runId.slice(0, 3)}.${runId.slice(3)}`;

async function login(page: Page, email: string, password = "demo1234") {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
}

test("admin uploads APK → landing shows download → file served", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

  await login(page, "super@doocall.uz");
  await expect(page.getByTestId("admin-shell")).toBeVisible({
    timeout: 20_000,
  });

  await page.goto("/admin/app");
  await page.getByTestId("apk-version").fill(VERSION);
  await page.getByTestId("apk-notes").fill("e2e build");
  await page
    .getByTestId("apk-file")
    .setInputFiles("e2e/fixtures-doocall-e2e.apk");
  await page.getByTestId("apk-upload").click();
  await expect(page.getByTestId("apk-list")).toContainText(VERSION, {
    timeout: 20_000,
  });
  // Newest build is marked as current.
  await expect(
    page.locator('[data-testid="apk-list"] tr').first(),
  ).toContainText(VERSION);

  // Landing (through nginx) shows the download button with this version.
  await page.goto("http://localhost/");
  const button = page.getByTestId("download-apk");
  await expect(button).toBeVisible({ timeout: 15_000 });
  await expect(button).toContainText(`v${VERSION}`);

  // The public download endpoint round-trips the actual bytes.
  const download = await request.get(
    "http://localhost/api/public/app/download",
  );
  expect(download.status()).toBe(200); // followed the presigned redirect
  expect((await download.body()).length).toBe(4096);
});

test("landing dropdown offers registration", async ({ page }) => {
  await page.goto("http://localhost/");
  await page.getByTestId("cabinet-menu-button").click();
  const register = page.getByTestId("menu-register");
  await expect(register).toBeVisible({ timeout: 15_000 });
  await register.click();
  await expect(page).toHaveURL(/\/register/);
  await expect(page.locator('input[name="company_name"]')).toBeVisible({
    timeout: 15_000,
  });
});
