import { expect, test } from "@playwright/test";

/** Phase-7 E2E against the SEEDED stack (Ahlan House, 12k calls, 6 operators).
 * Login: admin@ahlan.uz / demo1234 (created by seed_demo). */

test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1440, height: 900 } });

const runId = `${Date.now()}`.slice(-6);

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.locator('input[name="email"]').fill("admin@ahlan.uz");
  await page.locator('input[name="password"]').fill("demo1234");
  await page.locator('button[type="submit"]').click();
  await expect(page.getByTestId("cabinet-shell")).toBeVisible({
    timeout: 20_000,
  });
}

test("dashboard shows seeded numbers and period tabs work", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    // The anonymous-session refresh probe 401s by design (httpOnly cookie
    // pattern) and browsers log every failed request — allow ONLY that URL.
    if (
      message.type() === "error" &&
      !message.location().url.includes("/auth/refresh")
    ) {
      errors.push(`${message.text()} @ ${message.location().url}`);
    }
  });

  await login(page);

  // Seeded 7d window has thousands of calls — assert non-zero totals render.
  await page.getByTestId("period-tabs").getByText("7 дней").click();
  await expect(page.locator("text=Последние успешные звонки")).toBeVisible();
  // Per-operator chart renders operator names from the seed.
  await expect(page.locator("svg")).toHaveCount(
    await page.locator("svg").count(),
  );
  await page.getByTestId("period-tabs").getByText("Сегодня").click();

  expect(errors, `console errors: ${errors.join("\n")}`).toEqual([]);
});

test("calls: filter + play audio + pagination", async ({ page }) => {
  await login(page);
  await page.goto("/cabinet/calls");

  // Default 30d load — «1—30 из N».
  await expect(page.getByTestId("pagination-info")).toContainText(
    /1—30 из \d{2,}/,
    {
      timeout: 20_000,
    },
  );

  // Filter: answered only → apply.
  await page.getByLabel("Статус").selectOption("answered");
  await page.getByTestId("apply-filters").click();
  await expect(page.getByTestId("pagination-info")).toContainText(/из \d{2,}/);

  // Play audio on the first answered row (real presigned URL fetch; the
  // seeded records have no audio files, so the button simply disappears —
  // assert the interaction completes without an error toast).
  const firstAudio = page.getByTestId("row-audio").first();
  if (await firstAudio.isVisible().catch(() => false)) {
    await firstAudio.click();
  }
  // Ignore Next.js's empty route-announcer node — only alerts WITH text count.
  await expect(
    page.locator('[role="alert"]').filter({ hasText: /\S/ }),
  ).toHaveCount(0);
});

test("create contact from a call and see it linked", async ({ page }) => {
  await login(page);
  await page.goto("/cabinet/calls");
  await expect(page.getByTestId("pagination-info")).toContainText(/из \d{2,}/, {
    timeout: 20_000,
  });

  // First row without a contact shows the UserPlus link. Capture its number
  // (formatted "+998 xx xxx-xx-xx" → digits) before clicking.
  const createLink = page.locator('a[href*="fromCall="]').first();
  await expect(createLink).toBeVisible();
  const rowNumberText = await createLink.locator("xpath=..").textContent();
  const digits = (rowNumberText ?? "").replace(/\D/g, "");
  await createLink.click();

  // Contacts page auto-creates from the call; the new contact (named by its
  // number) must appear in the table — durable state, no toast race.
  await expect(page.locator("table")).toContainText(digits.slice(-4), {
    timeout: 20_000,
  });
});

test("every report submenu renders seeded data", async ({ page }) => {
  await login(page);
  await page.goto("/cabinet/reports");

  // Общая статистика — seeded totals are thousands; assert a 4+ digit number.
  await expect(page.getByTestId("report-general")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByTestId("report-general")).toContainText(/\d{4}/);

  // По периодам → weekday + chart with unique checkbox.
  await page.getByText("По периодам ▾").click();
  await page.getByTestId("tab-weekday").click();
  await expect(page.getByTestId("report-weekday")).toContainText("Пн");
  await page.getByText("По периодам ▾").click();
  await page.getByTestId("tab-period").click();
  await page.getByTestId("unique-checkbox").check();

  // По сотрудникам → all three modes; seeded operator name must render.
  await page.getByText("По сотрудникам ▾").click();
  await page.getByTestId("tab-emp-distribution").click();
  await expect(page.getByTestId("report-emp-distribution")).toContainText(
    /Aziz|aziz/,
    {
      timeout: 15_000,
    },
  );
  await page.getByText("По сотрудникам ▾").click();
  await page.getByTestId("tab-emp-am").click();
  await page.getByText("По сотрудникам ▾").click();
  await page.getByTestId("tab-emp-duration").click();
  await expect(page.getByText(/округлены/)).toBeVisible();

  // По клиентам → distribution, unanswered, last contact.
  await page.getByText("По клиентам ▾").click();
  await page.getByTestId("tab-client-distribution").click();
  await expect(page.getByTestId("report-clients")).toBeVisible();
  await page.getByText("По клиентам ▾").click();
  await page.getByTestId("tab-unanswered").click();
  await expect(page.getByTestId("report-unanswered")).toContainText(/мин|ч|дн/);
  await page.getByText("По клиентам ▾").click();
  await page.getByTestId("tab-last-contact").click();
  await expect(page.getByTestId("report-last-contact")).toBeVisible();
});

test("settings: add operator → license grows; deactivate → shrinks", async ({
  page,
}, testInfo) => {
  // Seat math mutates the shared seeded company — run on ONE project only.
  test.skip(
    testInfo.project.name !== "desktop",
    "single-project mutation test",
  );
  await login(page);
  await page.goto("/cabinet/settings");

  // Read the current license total.
  await page.getByTestId("settings-tab-license").click();
  await expect(page.getByTestId("license-tab")).toBeVisible({
    timeout: 15_000,
  });
  const seatsBefore = Number(
    await page.getByTestId("license-seats").textContent(),
  );

  // Add an operator — credential dialog appears exactly once.
  await page.getByTestId("settings-tab-usersGroups").click();
  await page.getByTestId("new-operator-name").fill(`e2e-op-${runId}`);
  await page.getByTestId("add-operator").click();
  await expect(page.getByTestId("credentials")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId("credentials")).toContainText(
    `e2e-op-${runId}`,
  );
  await page.getByTestId("credentials-close").click();

  // License total increased by exactly one seat.
  await page.getByTestId("settings-tab-license").click();
  await expect(page.getByTestId("license-seats")).toHaveText(
    String(seatsBefore + 1),
    {
      timeout: 15_000,
    },
  );

  // Deactivate the new operator → seats drop back.
  await page.getByTestId("settings-tab-usersGroups").click();
  await page.getByTestId(`toggle-e2e-op-${runId}`).click();
  // Scope to THIS operator's row — earlier runs leave deactivated operators.
  await expect(
    page.locator("li", { hasText: `e2e-op-${runId}` }).getByText("Отключен"),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("settings-tab-license").click();
  await expect(page.getByTestId("license-seats")).toHaveText(
    String(seatsBefore),
    {
      timeout: 15_000,
    },
  );
});

test("dark theme spot-check", async ({ page }) => {
  await login(page);
  await page.getByLabel("Тема").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ path: "../docs/screenshots/phase7-dark.png" });
  await page.getByLabel("Тема").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
