import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

/** Phase-13 E2E: portal i18n (ru/uz/en switcher), modern profiles,
 * admin editing of companies and integrators. Runs on the seeded stack. */

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1440, height: 900 } });

const runId = `${Date.now()}`.slice(-6);

async function login(page: Page, email: string, password = "demo1234") {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
}

async function apiToken(request: APIRequestContext, email: string) {
  const res = await request.post("/api/web/v1/auth/login", {
    data: { email, password: "demo1234" },
  });
  return (await res.json()).access as string;
}

test("admin: uz locale via sidebar switcher + profile page + edit company", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

  // A fresh company to rename (never touch seeded companies other suites use).
  const partnerToken = await apiToken(request, "partner1@demo.uz");
  const created = await (
    await request.post("/api/partner/v1/companies", {
      headers: { Authorization: `Bearer ${partnerToken}` },
      data: {
        company_name: `Editable ${runId}`,
        admin_email: `editable-${runId}@x.uz`,
        phone: "+998900000090",
        password: "editable-pw-1",
      },
    })
  ).json();
  const companyId = created.company.id as number;

  await login(page, "super@doocall.uz");
  await expect(page.getByTestId("admin-shell")).toBeVisible({
    timeout: 20_000,
  });

  // Switch to uz via the sidebar switcher — nav re-renders in Uzbek.
  await page
    .getByTestId("portal-locale")
    .getByRole("button", { name: "uz" })
    .click();
  await expect(page.getByTestId("admin-shell")).toContainText("Kompaniyalar", {
    timeout: 15_000,
  });

  // Modern profile page renders with role identity.
  await page.goto("/admin/profile");
  await expect(page.getByTestId("admin-profile")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId("admin-profile")).toContainText(
    "super@doocall.uz",
  );
  await expect(page.getByTestId("admin-profile")).toContainText("superadmin");

  // Edit the company from its detail page.
  await page.goto(`/admin/companies/${companyId}`);
  await page.getByTestId("edit-company-btn").click({ timeout: 15_000 });
  await page.getByTestId("edit-company-name").fill(`Edited ${runId}`);
  await page.getByTestId("edit-company-retention").fill("120");
  await page.getByTestId("edit-company-submit").click();
  await expect(page.getByTestId("admin-company-detail")).toContainText(
    `Edited ${runId}`,
    { timeout: 15_000 },
  );

  // Persisted server-side too.
  const superToken = await apiToken(request, "super@doocall.uz");
  const detail = await (
    await request.get(`/api/admin/v1/companies/${companyId}`, {
      headers: { Authorization: `Bearer ${superToken}` },
    })
  ).json();
  expect(detail.company.name).toBe(`Edited ${runId}`);
  expect(detail.company.audio_retention_days).toBe(120);
});

test("admin: edit integrator contacts from detail page", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

  // Fresh integrator so seeded partners stay untouched.
  const superToken = await apiToken(request, "super@doocall.uz");
  const created = await (
    await request.post("/api/admin/v1/integrators", {
      headers: { Authorization: `Bearer ${superToken}` },
      data: {
        name: `Editable Int ${runId}`,
        email: `edit-int-${runId}@x.uz`,
        password: "integrator-pw-1",
      },
    })
  ).json();
  const integratorId = created.integrator.id as number;

  await login(page, "super@doocall.uz");
  await expect(page.getByTestId("admin-shell")).toBeVisible({
    timeout: 20_000,
  });
  await page.goto(`/admin/integrators/${integratorId}`);
  await page.getByTestId("edit-int-btn").click({ timeout: 15_000 });
  await page.getByTestId("edit-int-name").fill(`Edited Int ${runId}`);
  await page.getByTestId("edit-int-phone").fill("+998901234599");
  await page.getByTestId("edit-int-card").fill("8600 1234 5678 9012");
  await page.getByTestId("edit-int-submit").click();
  await expect(page.getByTestId("admin-integrator-detail")).toContainText(
    `Edited Int ${runId}`,
    { timeout: 15_000 },
  );
  await expect(page.getByTestId("admin-integrator-detail")).toContainText(
    "+998901234599",
  );

  const detail = await (
    await request.get(`/api/admin/v1/integrators/${integratorId}`, {
      headers: { Authorization: `Bearer ${superToken}` },
    })
  ).json();
  expect(detail.integrator.name).toBe(`Edited Int ${runId}`);
  expect(detail.integrator.phone).toBe("+998901234599");
  expect(detail.integrator.payout_details.card).toBe("8600 1234 5678 9012");
});

test("partner: uz locale + modern profile save", async ({ page }) => {
  test.setTimeout(60_000);

  await login(page, "partner1@demo.uz");
  await expect(page.getByTestId("partner-shell")).toBeVisible({
    timeout: 20_000,
  });

  await page
    .getByTestId("portal-locale")
    .getByRole("button", { name: "uz" })
    .click();
  await expect(page.getByTestId("partner-shell")).toContainText(
    "Mening kompaniyalarim",
    { timeout: 15_000 },
  );

  await page.goto("/partner/profile");
  await expect(page.getByTestId("partner-profile")).toBeVisible({
    timeout: 15_000,
  });
  // Hero shows referral code chip + percent badge.
  await expect(page.getByTestId("partner-profile")).toContainText("DEMOINT1");
  await expect(page.getByTestId("partner-profile")).toContainText("%");

  await page.getByTestId("profile-save").click();
  await expect(page.locator('[role="status"]').last()).toContainText(
    "Saqlandi",
    { timeout: 15_000 },
  );
});
