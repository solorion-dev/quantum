// Capture render evidence for Developer Hub slice 1 (TRK-0075).
// Run on Tritium:  node scripts/capture.mjs
// Env: DEVHUB_URL (default http://100.66.182.7:8420/)
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, "..", "screenshots");
mkdirSync(outDir, { recursive: true });
const url = process.env.DEVHUB_URL ?? "http://100.66.182.7:8420/";

const browser = await chromium.launch();
const lines = [`url: ${url}`, `captured_at: ${new Date().toISOString()}`];

async function capture(name, viewport) {
  const page = await browser.newPage({ viewport });
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(2500);
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: true });
  const title = await page.title();
  const headings = await page.locator("h1, h2, h3").allInnerTexts();
  const serviceCount = await page.locator('[data-service-row="true"]').count();
  const bodyText = (await page.locator("body").innerText()).slice(0, 600);
  lines.push(
    `--- ${name} (${viewport.width}x${viewport.height})`,
    `title: ${title}`,
    `headings: ${headings.join(" | ")}`,
    `service_rows_rendered: ${serviceCount}`,
    `body_excerpt: ${bodyText.replace(/\s+/g, " ").trim()}`,
  );
  await page.close();
  return file;
}

const desktop = await capture("overview-desktop.png", { width: 1440, height: 900 });
const phone = await capture("overview-phone.png", { width: 390, height: 844 });
await browser.close();

writeFileSync(path.join(outDir, "render-evidence.txt"), lines.join("\n") + "\n");
console.log(`wrote ${desktop}`);
console.log(`wrote ${phone}`);
console.log(lines.join("\n"));
