import { expect, test } from "@playwright/test";

/** Phase-14 E2E: MoiZvonki-style flow through the real nginx stack.
 * Landing «Личный кабинет» dropdown → inline login (visitor STAYS on the
 * landing) → company list → click opens <slug>.localhost cabinet, with the
 * session carried by the domain-wide refresh cookie. */

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1440, height: 900 } });

const LANDING = "http://localhost";

test("landing dropdown login → companies list → subdomain cabinet", async ({
  page,
}) => {
  test.setTimeout(90_000);

  await page.goto(`${LANDING}/`);
  await expect(page.getByTestId("cabinet-menu-button")).toBeVisible({
    timeout: 20_000,
  });

  // Open the dropdown → inline login form (no navigation away).
  await page.getByTestId("cabinet-menu-button").click();
  await expect(page.getByTestId("cabinet-menu-login")).toBeVisible({
    timeout: 15_000,
  });
  await page
    .locator('[data-testid="cabinet-menu-login"] input[name="email"]')
    .fill("admin@ahlan.uz");
  await page
    .locator('[data-testid="cabinet-menu-login"] input[name="password"]')
    .fill("demo1234");
  await page
    .locator('[data-testid="cabinet-menu-login"] button[type="submit"]')
    .click();

  // Still on the landing; the account's companies are listed.
  await expect(page.getByTestId("cabinet-menu-companies")).toBeVisible({
    timeout: 15_000,
  });
  expect(new URL(page.url()).pathname).toBe("/");
  const link = page.getByTestId("company-link-ahlan-house");
  await expect(link).toContainText("Ahlan House");
  await expect(link).toContainText("ahlan-house.localhost");

  // Click → the company opens on ITS OWN subdomain, already signed in
  // (one-time ?sso= hand-off code).
  await link.click();
  await page.waitForURL(/ahlan-house\.localhost\/cabinet/, {
    timeout: 20_000,
  });
  await expect(page.getByTestId("cabinet-shell")).toBeVisible({
    timeout: 20_000,
  });
});

test("wrong-company subdomain API access is rejected", async ({ request }) => {
  const login = await request.post(
    "http://ahlan-house.localhost/api/web/v1/auth/login",
    { data: { email: "admin@ahlan.uz", password: "demo1234" } },
  );
  const token = (await login.json()).access as string;

  const own = await request.get(
    "http://ahlan-house.localhost/api/web/v1/dashboard",
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(own.status()).toBe(200);

  const wrong = await request.get(
    "http://demo-client-co.localhost/api/web/v1/dashboard",
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(wrong.status()).toBe(403);
});

test("foreign-company login on a subdomain is refused", async ({ request }) => {
  // admin@ahlan.uz belongs to ahlan-house — demo-client-co must refuse it.
  const foreign = await request.post(
    "http://demo-client-co.localhost/api/web/v1/auth/login",
    { data: { email: "admin@ahlan.uz", password: "demo1234" } },
  );
  expect(foreign.status()).toBe(401);

  // And a valid own-domain session cannot be refreshed on a foreign host.
  const ctx = request;
  const own = await ctx.post(
    "http://ahlan-house.localhost/api/web/v1/auth/login",
    { data: { email: "admin@ahlan.uz", password: "demo1234" } },
  );
  expect(own.status()).toBe(200);
  const wrongRefresh = await ctx.post(
    "http://demo-client-co.localhost/api/web/v1/auth/refresh",
  );
  expect(wrongRefresh.status()).toBe(401);
  const okRefresh = await ctx.post(
    "http://ahlan-house.localhost/api/web/v1/auth/refresh",
  );
  expect(okRefresh.status()).toBe(200);
});
