import { test, expect } from '@playwright/test';

// Command Board E2E (TRK-0686): the app must open on the seeded real
// backlog, accept a quick capture into the Inbox, and file/comment it —
// the same loop Scotty runs in the Muse Space.

test('board opens on the seeded backlog', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Command Board' })).toBeVisible();
  // Seeded boards render as tabs
  await expect(page.getByRole('tab', { name: 'Money' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Quantum / Fleet' })).toBeVisible();
  // A seeded card is visible on its board (scoped to the card: the card's
  // sr-only move label repeats the title and would trip strict mode)
  await page.getByRole('tab', { name: 'Money' }).click();
  await expect(page.getByTestId('item-card').filter({ hasText: 'Bridgecrest $321' })).toBeVisible();
});

test('quick capture lands in the inbox and can be commented on', async ({ page }) => {
  const marker = `E2E capture ${Date.now()}`;
  await page.goto('/');
  await page.getByTestId('quick-capture-input').fill(marker);
  await page.getByTestId('quick-capture-add').click();
  const card = page.getByTestId('item-card').filter({ hasText: marker });
  await expect(card).toBeVisible();

  await card.locator('h3').click();
  await page.getByTestId('comment-input').fill('E2E comment from the app');
  await page.getByTestId('comment-send').click();
  await expect(page.getByText('E2E comment from the app')).toBeVisible();
});

test('activity feed shows the setup entry', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Activity' }).click();
  await expect(page.getByTestId('activity-feed')).toBeVisible();
});
