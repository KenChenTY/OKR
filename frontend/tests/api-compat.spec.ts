import { test, expect } from "@playwright/test";

for (const withoutRandomUUID of [false, true]) {
  test(`write sends unique idempotency keys ${withoutRandomUUID ? "without" : "with"} randomUUID`, async ({ page }) => {
    await page.route("**/auth/config", (route) =>
      route.fulfill({ json: { password_login: true, development_login: false } }),
    );
    await page.route("**/api/status", (route) =>
      route.fulfill({ json: { status: "ready" } }),
    );
    const keys: string[] = [];
    await page.route("**/api/compat-test", async (route) => {
      const headers = route.request().headers();
      keys.push(headers["idempotency-key"]);
      expect(headers["if-match"]).toBe('"revision-1"');
      expect(headers["x-csrf-token"]).toBe("test-csrf");
      expect(route.request().method()).toBe("PATCH");
      expect(route.request().postDataJSON()).toEqual({ name: "Test" });
      await route.fulfill({ json: { saved: true } });
    });
    await page.goto("/login");
    const results = await page.evaluate(async (disableUUID) => {
      if (disableUUID) {
        Object.defineProperty(crypto, "randomUUID", { value: undefined });
      }
      // Import the actual API module through Vite in the browser.
      const modulePath = "/src/api.ts";
      const { write, setCsrf } = await import(/* @vite-ignore */ modulePath);
      setCsrf("test-csrf");
      return Promise.all(
        Array.from({ length: 3 }, () =>
          write("/api/compat-test", { name: "Test" }, '"revision-1"', "PATCH"),
        ),
      );
    }, withoutRandomUUID);
    expect(results).toEqual(Array(3).fill({ saved: true }));
    expect(new Set(keys).size).toBe(3);
    for (const key of keys) {
      expect(key).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      );
    }
  });
}
