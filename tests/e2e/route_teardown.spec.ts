import { createServer } from "node:http";
import { expect } from "@playwright/test";
import { test } from "./support/test";

test("keeps a page alive until an active route.fetch handler completes", async ({ page }) => {
  let markHandlerStarted!: () => void;
  const handlerStarted = new Promise<void>((resolve) => {
    markHandlerStarted = resolve;
  });

  const server = createServer((_request, response) => {
    setTimeout(() => {
      response.writeHead(200, {
        "access-control-allow-origin": "*",
        "content-type": "text/plain",
      });
      response.end("delayed route response");
      server.close();
    }, 1_500);
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (address === null || typeof address === "string") {
    throw new Error("The delayed route server did not bind to a TCP port.");
  }
  const url = `http://127.0.0.1:${address.port}/delayed`;

  await page.route(url, async (route) => {
    markHandlerStarted();
    const response = await route.fetch();
    await route.fulfill({ response });
  });

  await page.goto("/");
  await page.evaluate((requestUrl) => {
    void fetch(requestUrl).catch(() => undefined);
  }, url);
  await handlerStarted;
  expect(page.url()).toBe("http://127.0.0.1:5173/");
});
