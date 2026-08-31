import { defineConfig } from "@playwright/test";

/** Smoke tests against the running compose stack (frontend :3000 with the
 * dev API proxy → backend). Start the stack first: `make up`. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  retries: 0,
  // Suites mutate shared platform state (global cashback %, partner
  // balances) on one live stack — cross-file parallelism is racy.
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { viewport: { width: 768, height: 1024 } } },
    { name: "mobile-380", use: { viewport: { width: 380, height: 800 } } },
  ],
});
