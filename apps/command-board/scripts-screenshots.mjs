// Verification screenshots for the Command Board app (TRK-0686).
// Expects the service on :8798 and the Vite dev server on :5179.
// Usage: node scripts-screenshots.mjs [outDir]
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const outDir = process.argv[2] || 'screenshots';
mkdirSync(outDir, { recursive: true });
const base = process.env.BOARD_UI_URL || 'http://127.0.0.1:5179';

const browser = await chromium.launch();

// Desktop 1280x800
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: 'Money' }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${outDir}/01-board-money-desktop.png` });
  console.log('shot 01 board money desktop');

  await page.getByText(/Bridgecrest \$321 due Sat Nov 14/).first().click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${outDir}/02-item-detail-desktop.png` });
  console.log('shot 02 item detail desktop');
  await page.close();
}

// Phone 390x844
{
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${outDir}/03-inbox-mobile.png` });
  console.log('shot 03 inbox mobile');

  await page.getByRole('tab', { name: 'Quantum / Fleet' }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${outDir}/04-board-fleet-mobile.png` });
  console.log('shot 04 fleet board mobile');

  await page.getByRole('button', { name: 'Activity' }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${outDir}/05-activity-mobile.png` });
  console.log('shot 05 activity mobile');
  await page.close();
}

await browser.close();
console.log('SCREENSHOTS DONE');
