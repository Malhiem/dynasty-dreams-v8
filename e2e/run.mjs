// Waits for the Compose services before starting the browser suite.
import { spawn } from "node:child_process";

const targets = ["http://web/health", "http://backend:8000/api/health"];
const deadline = Date.now() + 90_000;

async function waitFor(url) {
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The service is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

for (const target of targets) await waitFor(target);

const playwright = spawn(
  "yarn",
  ["playwright", "test", "--config=e2e/playwright.config.ts"],
  {
    stdio: "inherit",
    env: process.env,
  },
);

playwright.on("exit", (code) => process.exit(code ?? 1));
