import { execSync } from "node:child_process";
import { expect, test, type Page } from "@playwright/test";

/** Phase-11 E2E: admin portal against the seeded stack.
 * Seed gives: super@doocall.uz (superadmin), partner integrators DEMOINT1/2,
 * one pending payout, admin@ahlan.uz (company admin). */

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1440, height: 900 } });

const runId = `${Date.now()}`.slice(-6);
const PA_EMAIL = `pa-${runId}@platform.uz`;
const PA_PASS = "platform-pw-1";

async function login(page: Page, email: string, password: string) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
}

test("superadmin: KPIs → create integrator 25% → payout → cashback % → audit", async ({
  page,
  request,
}) => {
  // Self-sufficient pending payout: earlier runs may have consumed the
  // seeded one — request a fresh one as the seeded partner.
  const partnerLogin = await request.post("/api/web/v1/auth/login", {
    data: { email: "partner1@demo.uz", password: "demo1234" },
  });
  const partnerToken = (await partnerLogin.json()).access;
  const wallet = await (
    await request.get("/api/partner/v1/payouts", {
      headers: { Authorization: `Bearer ${partnerToken}` },
    })
  ).json();
  const minPayout: number = wallet.min_payout_uzs ?? 50000;
  if (wallet.balance_uzs < minPayout) {
    // Prior runs drained the balance — accrue enough cashback via an
    // applied payment on one of DEMOINT1's bound companies.
    const needed = Math.ceil(((minPayout - wallet.balance_uzs) / 0.1) * 1.2);
    execSync(
      `docker compose exec -T backend python manage.py shell -c "` +
        `from apps.billing.models import Payment; from apps.billing import services; ` +
        `from apps.partners.models import Integrator; ` +
        `i = Integrator.objects.get(referral_code='DEMOINT1'); ` +
        `c = i.companies.first(); ` +
        `p = Payment.all_objects.create(company=c, provider='manual', amount_uzs=${needed}); ` +
        `services.apply_payment(p)"`,
      { cwd: "..", stdio: "pipe" },
    );
  }
  await request.post("/api/partner/v1/payouts", {
    headers: { Authorization: `Bearer ${partnerToken}` },
    data: { amount_uzs: minPayout, note: `e2e-${runId}` },
  });

  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !m.location().url.includes("/auth/refresh"))
      errors.push(`${m.text()} @ ${m.location().url}`);
  });

  await login(page, "super@doocall.uz", "demo1234");
  await expect(page.getByTestId("admin-shell")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("admin-badge")).toHaveText("Admin");

  // KPIs render with real numbers.
  await expect(page.getByTestId("admin-dashboard")).toContainText("Компании");
  await expect(page.getByTestId("admin-dashboard")).toContainText(/MRR/);
  await expect(page.getByTestId("admin-dashboard")).toContainText(/\d/);

  // Create an integrator with a 25% override.
  await page.goto("/admin/integrators");
  await page.getByTestId("new-integrator").click();
  await page.getByTestId("int-name").fill(`E2E Partner ${runId}`);
  await page.getByTestId("int-email").fill(`e2e-int-${runId}@x.uz`);
  await page.getByTestId("int-password").fill("integrator-pw-1");
  await page.getByTestId("int-override").fill("25");
  await page.getByTestId("int-create").click();
  await expect(page.locator('[role="status"]').last()).toContainText(/Код:/, {
    timeout: 15_000,
  });

  // Open its detail — effective % shows the override.
  await page.getByRole("link", { name: `E2E Partner ${runId}` }).click();
  await expect(page.getByTestId("effective-percent")).toContainText("25", {
    timeout: 15_000,
  });
  await expect(page.getByTestId("effective-percent")).toContainText("override");

  // Approve the seeded pending payout from the queue.
  await page.goto("/admin/payouts");
  const approveButton = page
    .locator('[data-testid^="payout-approve-"]')
    .first();
  await expect(approveButton).toBeVisible({ timeout: 15_000 });
  await approveButton.click();
  await expect(page.locator('[role="status"]').last()).toContainText(
    "approved",
    {
      timeout: 15_000,
    },
  );

  // Change the global cashback %.
  await page.goto("/admin/cashback");
  await page.getByTestId("cashback-percent").fill("11");
  await expect(page.getByTestId("cashback-example")).toContainText("11");
  await page.getByTestId("cashback-save").click();
  await expect(page.locator('[role="status"]').last()).toContainText(
    "обновлены",
    {
      timeout: 15_000,
    },
  );

  // Audit shows both events.
  await page.goto("/admin/audit");
  await page.getByTestId("audit-filter").fill("payout");
  await expect(page.getByTestId("audit-list")).toContainText(
    "payout.approved",
    {
      timeout: 15_000,
    },
  );
  await page.getByTestId("audit-filter").fill("integrator_created");
  await expect(page.getByTestId("audit-list")).toContainText(
    "admin.integrator_created",
  );

  expect(errors, errors.join("\n")).toEqual([]);
});

test("platform_admin: superadmin screens 403 + hidden from nav", async ({
  page,
  request,
}) => {
  // Superadmin provisions a platform_admin via the API.
  const loginRes = await request.post("/api/web/v1/auth/login", {
    data: { email: "super@doocall.uz", password: "demo1234" },
  });
  const token = (await loginRes.json()).access;
  const created = await request.post("/api/admin/v1/admins", {
    headers: { Authorization: `Bearer ${token}` },
    data: { email: PA_EMAIL, password: PA_PASS },
  });
  expect(created.status()).toBe(201);

  await login(page, PA_EMAIL, PA_PASS);
  await expect(page.getByTestId("admin-shell")).toBeVisible({
    timeout: 20_000,
  });

  // Nav: superadmin sections ABSENT.
  const nav = page.getByTestId("admin-shell").locator("aside");
  await expect(nav).toContainText("Компании");
  await expect(nav).not.toContainText("Тарифы");
  await expect(nav).not.toContainText("Кэшбэк");
  await expect(nav).not.toContainText("Администраторы");
  await expect(nav).not.toContainText("Выплаты");

  // The superadmin-only API truly refuses this platform_admin (403, not
  // just hidden UI). page.request has no in-memory Bearer — log in directly.
  const paLogin = await request.post("/api/web/v1/auth/login", {
    data: { email: PA_EMAIL, password: PA_PASS },
  });
  const paToken = (await paLogin.json()).access;
  for (const path of [
    "/api/admin/v1/settings/pricing",
    "/api/admin/v1/settings/cashback",
  ]) {
    const res = await request.get(path, {
      headers: { Authorization: `Bearer ${paToken}` },
    });
    expect(res.status(), path).toBe(403);
  }
  // …while a staff endpoint works fine for the same user.
  const companiesRes = await request.get("/api/admin/v1/companies", {
    headers: { Authorization: `Bearer ${paToken}` },
  });
  expect(companiesRes.status()).toBe(200);
});

test("company admin: /admin/* renders the 403 page", async ({ page }) => {
  await login(page, "admin@ahlan.uz", "demo1234");
  await expect(page.getByTestId("cabinet-shell")).toBeVisible({
    timeout: 20_000,
  });

  await page.goto("/admin");
  await expect(page.getByTestId("forbidden")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("forbidden")).toContainText("403");
});

test("impersonation: banner in cabinet, exit returns to admin", async ({
  page,
}) => {
  await login(page, "super@doocall.uz", "demo1234");
  await expect(page.getByTestId("admin-shell")).toBeVisible({
    timeout: 20_000,
  });

  // Open a company detail and impersonate.
  await page.goto("/admin/companies");
  await page.getByRole("link", { name: "Ahlan House" }).click();
  await expect(page.getByTestId("admin-company-detail")).toBeVisible({
    timeout: 15_000,
  });
  await page.getByTestId("impersonate-btn").click();

  // Cabinet with the persistent banner.
  await expect(page.getByTestId("impersonation-banner")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("impersonation-banner")).toContainText(
    "ahlan-house",
  );

  // Exit → back in the admin portal, banner gone.
  await page.getByTestId("impersonation-exit").click();
  await expect(page.getByTestId("admin-shell")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("impersonation-banner")).toHaveCount(0);
});
