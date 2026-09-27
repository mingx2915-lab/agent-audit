import { test as base, expect } from "@playwright/test";

export { expect };

export const test = base.extend({
  page: async ({ page }, use) => {
    await use(page);
    await page.unrouteAll({ behavior: "wait" });
  },
});
