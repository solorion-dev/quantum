import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { createHmac } from 'node:crypto'

// Fake local-only secret from apps/tracker-api/README.md; never a real credential.
const API = `http://127.0.0.1:${process.env.TB_API_PORT || '7656'}/api`
const FAKE_SECRET = 'e2e-test-only-fake' // must match TRACKER_WEBHOOK_SECRET in playwright.config.ts

const axe = async (page: Page, name: string) => {
  // wait out dialog/sheet entry animations: mid-fade opacity makes axe report false contrast failures
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()
  const summary = r.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} — ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`)
  test.info().annotations.push({ type: `axe:${name}`, description: summary.join('\n') || 'clean' })
  expect(summary, `axe violations on ${name}`).toEqual([])
}

test.describe.configure({ mode: 'serial' })

test.beforeEach(async ({ page }) => {
  await page.goto('/#/board')
  await expect(page.getByText('Live: tracker-api')).toBeVisible()
  await expect(page.locator('.tb-card').first()).toBeVisible()
})

test('board: 5 primary columns, collapsed backlog/cancelled, axe clean', async ({ page }) => {
  for (const c of ['Planned', 'In progress', 'In review', 'Blocked', 'Done']) await expect(page.getByRole('heading', { name: new RegExp(`^${c}`) })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Backlog/ })).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('button', { name: /^Cancelled/ })).toHaveAttribute('aria-expanded', 'false')
  await axe(page, 'board')
})

test('board keyboard: arrows move focus, Shift+Right moves card (PATCH), Enter opens detail', async ({ page, isMobile }) => {
  await page.locator('.tb-card[data-col="1"]').first().focus()
  await page.keyboard.press('ArrowDown')
  await expect(page.locator('.tb-card[data-col="1"][data-idx="1"]')).toBeFocused()
  await page.keyboard.press('ArrowRight')
  await expect(page.locator('.tb-card[data-col="2"][data-idx="1"]')).toBeFocused()
  const id = (await page.locator(':focus').getAttribute('data-id'))!
  await page.keyboard.press('Shift+ArrowRight')
  await expect(page.getByText(`${id} updated`)).toBeVisible()
  // Since dac0650 a board edit by an agent (X-Actor: pixel) is a directed write, not automated:
  // the card stays visible in In review instead of folding into the A2A group.
  await expect(page.locator(`.tb-card[data-id="${id}"]`)).toHaveAttribute('data-col', '3')
  await page.locator(`.tb-card[data-id="${id}"]`).focus()
  await page.keyboard.press('Enter')
  const dlg = page.getByRole('dialog')
  for (const h of ['Links', 'Sync', 'Relations', 'History']) await expect(dlg.getByRole('heading', { name: h })).toBeVisible()
  await expect(dlg.getByText(/In progress → In review/).first()).toBeVisible()
  await expect(dlg.getByText(/by Pixel/).last()).toBeVisible()
  await axe(page, isMobile ? 'detail-sheet' : 'detail-drawer')
  await page.keyboard.press('Escape')
  await expect(dlg).toBeHidden()
  // put it back so the run is repeatable
  await page.request.patch(`${API}/items/${id}`, { data: { status: 'in_progress' }, headers: { 'X-Actor': 'pixel' } })
})

test('shared filters: priority chip, flags, applies across tabs', async ({ page }) => {
  await page.getByRole('button', { name: /^Priority filter/ }).click()
  await page.getByRole('checkbox', { name: /^Critical/ }).check()
  await page.keyboard.press('Escape')
  await expect(page.getByText('Priority: Critical')).toBeVisible()
  const crit = await page.locator('.tb-card').count()
  expect(crit).toBeGreaterThan(0)
  await page.getByRole('tab', { name: /^List/ }).press('Enter')
  const rows = page.locator('.tb-list tbody tr')
  expect(await rows.count()).toBeGreaterThanOrEqual(crit) // list also includes collapsed Backlog/Cancelled
  for (const t of await rows.allInnerTexts()) expect(t.toLowerCase()).toContain('critical')
  await axe(page, 'list-filtered')
  await page.getByRole('button', { name: 'Remove filter Priority: Critical' }).click()
  await page.getByRole('button', { name: /^Needs triage: \d+/ }).click()
  await expect(page.locator('.filter-chip', { hasText: 'Needs triage' })).toBeVisible()
  expect(await page.locator('.tb-list tbody tr').count()).toBeGreaterThan(0)
  await page.getByRole('tab', { name: /^Projects/ }).click()
  await expect(page.locator('.tb-project').first()).toBeVisible()
  await axe(page, 'projects')
})

test('list: sortable headers expose aria-sort', async ({ page }) => {
  await page.getByRole('tab', { name: /^List/ }).press('Enter')
  const th = page.getByRole('columnheader', { name: /^Sort: ID/ })
  await th.getByRole('button').click()
  await expect(th).toHaveAttribute('aria-sort', 'ascending')
  await th.getByRole('button').click()
  await expect(th).toHaveAttribute('aria-sort', 'descending')
  // Items created by earlier tests (shared server across projects) may sit above the seed, so check order, not a fixed id.
  const ids = (await page.locator('.tb-list tbody tr td:first-child').allTextContents()).map((t) => Number(t.match(/TRK-(\d+)/)?.[1] ?? 0))
  expect(ids[0]).toBeGreaterThanOrEqual(9020)
  expect(ids[0]).toBe(Math.max(...ids))
})

test('suggestions inbox: real webhook → pending suggestion → accept', async ({ page, request, isMobile }) => {
  const body = JSON.stringify({ action: 'closed', issue: { number: isMobile ? 109 : 100 }, repository: { full_name: 'solorion-dev/sandbox' } })
  const sig = 'sha256=' + createHmac('sha256', FAKE_SECRET).update(body).digest('hex')
  const r = await request.post(`${API}/webhooks/github`, { data: body, headers: {
    'content-type': 'application/json', 'X-GitHub-Event': 'issues', 'X-GitHub-Delivery': `e2e-${Date.now()}-${Math.random()}`, 'X-Hub-Signature-256': sig } })
  expect(r.status()).toBe(202)
  const pending = (await (await request.get(`${API}/suggestions?state=pending`)).json()).suggestions
  expect(pending.length).toBeGreaterThan(0)
  await page.reload()
  await page.getByRole('button', { name: /Suggestions inbox, [1-9]/ }).click()
  const dlg = page.getByRole('dialog', { name: /Suggestions inbox/ })
  await expect(dlg).toBeVisible()
  await axe(page, 'inbox')
  const sid = pending[0].id
  // keyboard activation: under isMobile emulation the animating bottom sheet confuses pointer hit-testing
  await dlg.getByRole('button', { name: `Accept ${sid}` }).press('Enter')
  await expect(page.getByText(`${sid} accepted`)).toBeVisible()
  const after = (await (await request.get(`${API}/suggestions?state=pending`)).json()).suggestions
  expect(after.find((s: { id: string }) => s.id === sid)).toBeUndefined()
})

test('fixture fallback: ?source=fixture works offline, A2A grouping, reject with reason', async ({ page }) => {
  await page.goto('/?source=fixture#/board')
  await expect(page.getByText('Offline: fixture data')).toBeVisible()
  const toggle = page.getByRole('button', { name: /Show 1 automated \(A2A\) in Planned/ })
  await toggle.press('Enter') // column may sit off-screen in the phone scroll-snap row
  await expect(page.getByText('A2A task: nightly sync digest for harbor')).toBeVisible()
  await page.getByLabel('Automated (A2A)').selectOption('hide')
  await expect(page.getByText('A2A task: nightly sync digest for harbor')).toBeHidden()
  await page.getByRole('button', { name: /Suggestions inbox, 1 pending/ }).click()
  await page.getByRole('button', { name: 'Reject SUG-1' }).press('Enter')
  await page.getByLabel('Reason (optional)').fill('not yet')
  await page.getByRole('button', { name: 'Confirm reject' }).press('Enter')
  await expect(page.getByText('SUG-1 rejected')).toBeVisible()
  await expect(page.getByRole('button', { name: /Suggestions inbox, 0 pending/ })).toBeVisible()
})

test('600-item synthetic dataset stays bounded and responsive', async ({ page, isMobile }) => {
  test.skip(isMobile, 'perf budget measured at 1920x1080')
  const t0 = Date.now()
  await page.goto('/?source=fixture&synthetic=600#/board')
  await expect(page.locator('.tb-card').first()).toBeVisible()
  const loadMs = Date.now() - t0
  await expect(page.getByRole('tab', { name: /^Board · 6\d\d/ })).toBeVisible()
  const cards = await page.locator('.tb-card').count()
  expect(cards).toBeLessThanOrEqual(5 * 30 + 10) // paged at 30 per column
  await expect(page.getByRole('button', { name: /Show 30 more/ }).first()).toBeVisible()
  const t1 = Date.now()
  await page.getByRole('searchbox', { name: 'Search items' }).fill('Synthetic 59')
  await expect(page.locator('.tb-card').first()).toContainText('Synthetic 59')
  const filterMs = Date.now() - t1
  await page.getByRole('searchbox', { name: 'Search items' }).fill('')
  await page.getByRole('tab', { name: /^List/ }).press('Enter')
  await expect(page.locator('.tb-list tbody tr')).toHaveCount(101) // 100 rows + "show more" row
  const t2 = Date.now()
  await page.getByRole('button', { name: /^Show 100 more/ }).click()
  await expect(page.locator('.tb-list tbody tr')).toHaveCount(201)
  const moreMs = Date.now() - t2
  test.info().annotations.push({ type: 'perf', description: `load ${loadMs}ms, cards in DOM ${cards}, filter ${filterMs}ms, list +100 ${moreMs}ms` })
  expect(filterMs).toBeLessThan(1500)
  await axe(page, 'list-600')
})

test('create item: app-bar button and column "+" → POST /api/items → toast → opens new item', async ({ page, request, isMobile }) => {
  // Column "+" pre-fills that status.
  await page.getByRole('button', { name: 'New item in In review' }).press('Enter')
  const dlg = page.getByRole('dialog', { name: 'New item' })
  await expect(dlg).toBeVisible()
  await expect(dlg.getByLabel('Status')).toHaveValue('in_review')
  await expect(dlg.getByLabel('Title (required)')).toBeFocused()
  await axe(page, isMobile ? 'create-sheet' : 'create-modal')
  await dlg.getByRole('button', { name: 'Cancel' }).press('Enter')
  await expect(dlg).toBeHidden()

  await page.getByRole('button', { name: 'New item', exact: true }).press('Enter')
  await expect(dlg).toBeVisible()
  await dlg.getByRole('button', { name: 'Create item' }).press('Enter')
  await expect(dlg.getByText('Title is required')).toBeVisible()
  await expect(dlg.getByLabel('Title (required)')).toHaveAttribute('aria-invalid', 'true')
  const title = `E2E created ${isMobile ? 'phone' : 'desktop'} ${Date.now()}`
  await dlg.getByLabel('Title (required)').fill(title)
  await dlg.getByLabel('Status').selectOption('planned')
  await dlg.getByLabel('Priority').selectOption('high')
  await dlg.getByLabel('Assignee').selectOption('pixel')
  await dlg.getByRole('checkbox', { name: 'ui' }).press('Space')
  await expect(dlg.getByRole('checkbox', { name: 'ui' })).toBeChecked()
  await dlg.getByLabel('Parent').selectOption('TRK-9001')
  await dlg.getByLabel('Description').fill('Created by Playwright against the throwaway API.')
  const posted = page.waitForRequest((r) => r.method() === 'POST' && /\/api\/items$/.test(r.url()))
  await dlg.getByRole('button', { name: 'Create item' }).press('Enter')
  const req = await posted
  expect(req.headers()['x-actor']).toBe('pixel')
  expect(req.postDataJSON()).toMatchObject({ title, status: 'planned', priority: 'high', assigneeId: 'pixel', labels: ['ui'], parentId: 'TRK-9001' })
  await expect(page.getByText(/TRK-\d+ created/)).toBeVisible()
  const detail = page.getByRole('dialog').filter({ hasText: title })
  await expect(detail.getByRole('heading', { name: 'Relations' })).toBeVisible()
  const id = (await page.getByText(/TRK-\d+ created/).textContent())!.match(/TRK-\d+/)![0]
  const got = await (await request.get(`${API}/items/${id}`)).json()
  expect(got.item).toMatchObject({ title, status: 'planned', priority: 'high', assigneeId: 'pixel', parentId: 'TRK-9001', labels: ['ui'] })
})

test('forward-compatible fields: item.project groups, item.automated overrides heuristic', async ({ page }) => {
  await page.route(/\/api\/items(\?.*)?$/, async (route) => {
    const res = await route.fetch(); const j = await res.json()
    j.items = j.items.map((i: Record<string, unknown>, n: number) => ({ ...i, project: n < 3 ? { id: 'Alpha', title: 'Alpha project', derived: false } : null, automated: n === 3 }))
    await route.fulfill({ response: res, json: j })
  })
  await page.reload()
  await page.getByRole('tab', { name: /^Projects/ }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Alpha · Alpha project' })).toBeVisible()
  await page.getByRole('tab', { name: /^List/ }).press('Enter')
  await expect(page.getByRole('button', { name: 'Show 1 automated (A2A) items' })).toBeVisible()
})

// ---- Scout QA fixes (f93ba2a report): run in both projects (1920 and 390) ----
const SHOTS = '/workspace/tracker/ui/after/qa-fixes'

test('QA B1: create dialog actions visible and tappable, sheet not shifted', async ({ page, isMobile, request }, info) => {
  await page.getByRole('button', { name: 'New item', exact: true }).click()
  const dlg = page.getByRole('dialog', { name: 'New item' })
  await expect(dlg).toBeVisible()
  await page.waitForTimeout(400) // let the sheet animation settle before measuring
  const vp = page.viewportSize()!
  const box = (await dlg.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(vp.width + 0.5)
  const btn = dlg.getByRole('button', { name: 'Create item' })
  const b = (await btn.boundingBox())!
  expect(b.y + b.height).toBeLessThanOrEqual(vp.height)
  await page.screenshot({ path: `${SHOTS}/after-create-${info.project.name}.png` })
  const title = `QA B1 tap ${info.project.name} ${Date.now()}`
  await dlg.getByLabel('Title (required)').fill(title)
  // scroll the body to the end: the footer must stay pinned and visible
  await dlg.locator('.dialog__body').evaluate((el) => { el.scrollTop = el.scrollHeight })
  await expect(btn).toBeInViewport()
  if (isMobile) await btn.tap(); else await btn.click()
  await expect(page.getByText(/TRK-\d+ created/)).toBeVisible()
  const id = (await page.getByText(/TRK-\d+ created/).textContent())!.match(/TRK-\d+/)![0]
  expect((await (await request.get(`${API}/items/${id}`)).json()).item.title).toBe(title)
})

test('QA B3: hash-only filter changes and Back are re-read without reload', async ({ page }) => {
  const tab = page.getByRole('tab', { name: /^Board · / })
  const all = (await tab.textContent())!
  await page.evaluate(() => { (window as unknown as { __marker: number }).__marker = 1 })
  await page.evaluate(() => { location.hash = '#/board?priority=critical' })
  await expect(page.getByRole('button', { name: /Remove filter .*Critical/i })).toBeVisible()
  await expect(tab).not.toHaveText(all)
  await page.goBack()
  await expect(page.getByRole('button', { name: /Remove filter .*Critical/i })).toBeHidden()
  await expect(tab).toHaveText(all)
  await page.goForward()
  await expect(page.getByRole('button', { name: /Remove filter .*Critical/i })).toBeVisible()
  expect(await page.evaluate(() => (window as unknown as { __marker?: number }).__marker)).toBe(1) // no reload happened
})

test('QA B4: no page-level sideways scroll; summary strip shows Overdue or a scroll cue', async ({ page, isMobile }, info) => {
  for (const v of ['Board', 'List', 'Projects']) {
    await page.getByRole('tab', { name: new RegExp(`^${v}`) }).press('Enter')
    const w = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, iw: window.innerWidth }))
    expect(w.sw, `${v} scrollWidth`).toBeLessThanOrEqual(w.cw)
    expect(w.iw, `${v} layout viewport`).toBe(page.viewportSize()!.width)
  }
  await page.getByRole('tab', { name: /^Board/ }).press('Enter')
  const strip = page.getByRole('region', { name: 'Summary' })
  const overdue = strip.getByText('Overdue')
  if (isMobile) {
    const more = await strip.evaluate((el) => el.scrollWidth > el.clientWidth)
    if (more) {
      await expect(page.getByText('Swipe for more →')).toBeVisible()
      await expect(page.locator('.tb-summary-wrap')).toHaveAttribute('data-more-end', 'true')
    }
    await overdue.scrollIntoViewIfNeeded()
  }
  await expect(overdue).toBeInViewport({ ratio: 1 })
  await page.screenshot({ path: `${SHOTS}/after-board-${info.project.name}.png` })
  await axe(page, 'qa-b4-board')
})

test('QA B8: Tab and Shift+Tab never leave the create dialog (60 presses each)', async ({ page }) => {
  await page.getByRole('button', { name: 'New item', exact: true }).press('Enter')
  const dlg = page.getByRole('dialog', { name: 'New item' })
  await expect(dlg.getByLabel('Title (required)')).toBeFocused()
  for (const key of ['Tab', 'Shift+Tab']) {
    for (let n = 0; n < 60; n++) {
      await page.keyboard.press(key)
      const inside = await dlg.evaluate((d) => d.contains(document.activeElement) && document.activeElement !== d)
      expect(inside, `${key} press ${n + 1}`).toBe(true)
    }
  }
  await axe(page, 'qa-b8-create')
  await page.keyboard.press('Escape')
  await expect(dlg).toBeHidden()
})
