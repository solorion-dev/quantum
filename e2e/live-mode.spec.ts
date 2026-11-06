import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  STUB_MCP_KEY,
  installStubApi,
  seedLiveSettings,
  type StubApiOptions,
} from './fixtures/hub-api';

/**
 * Live-mode E2E for the Quantum everything app.
 *
 * The app-shell spec covers a clean profile: no service configured, and
 * every screen must show its honest demo / not-connected state. This
 * spec covers the other half of the contract: with hub + nebula base
 * URLs configured, the screens must render the data the API returned —
 * the fixture data from e2e/fixtures/hub-api.ts, served by route
 * interception, so the run is deterministic and needs no live Tritium,
 * no tailnet, and no keys.
 *
 * Covered:
 *  - Home renders the stubbed live estate (summary, services + probes,
 *    vitals, agents, docket) and shows no demo labelling anywhere.
 *  - The services search filters the stubbed registry client-side.
 *  - One failing endpoint (/api/agents → 500) degrades only its own
 *    section, per the client's Promise.allSettled design — the rest of
 *    the dashboard stays live.
 *  - Create → Jobs renders the stubbed Nebula queue (active + recent).
 *
 * Part 2 (2026-10-28, TRK-0483) — the MCP-backed screens, both of
 * which speak POST /mcp (JSON-RPC) to the same hub base URL:
 *  - More → Services & tools connects to the stub gateway, lists the
 *    fixture tools, and running `dsect_services_status` renders the
 *    pretty services result (2/4 up, 2 problems — the Part 1 estate).
 *  - A dead MCP gateway (HTTP 500 on every /mcp) degrades only that
 *    screen: it shows its honest Connection failed card while the
 *    /api-backed Home dashboard in the same boot stays live.
 *  - Mail renders the fixture inbox (dsect_mail_list over MCP), and
 *    opening a thread renders its fixture message (dsect_mail_read).
 *    The inbox test also guards row geometry at 390px (TRK-0484):
 *    no element of a message row may overflow the viewport.
 *
 * Part 3 (2026-10-31, TRK-0498) — Create → Gallery in list layout:
 *    the thumbnail+caption rows are native list-row buttons (migrated
 *    off QButton, the last complex-children usage the TRK-0492 guard
 *    allowlisted), guarded by the same 390px row-geometry contract as
 *    the inbox rows: no row element may overflow the viewport.
 *
 * Part 3 (2026-11-05, TRK-0609) — the last two tabs, completing the
 * every-tab live-mode coverage (Home/Create Parts 1-2, Services/Mail
 * in the Part 2 block above):
 *  - Chat rides the Sol gateway base URL (settings.sol), a different
 *    settings field than hub/nebula: the Chat pane renders the stub
 *    gateway's model list and streams a fixture reply through the
 *    SSE completions endpoint; Chat -> Agents renders the stub fleet
 *    snapshot (roster, shared desk, DM thread).
 *  - Collab rides the hub base URL like Part 1: goal cards render
 *    from /api/collab/goals, expanding one fetches its detail
 *    (sub-goals + tasks), and the Board view renders the stub kanban
 *    columns plus the Recent activity feed.
 *  - A dead Sol gateway (models + agents -> 500) degrades only Chat,
 *    and dead Collab endpoints degrade only Collab — in both cases
 *    the /api-backed Home dashboard in the same boot stays live.
 *    (TRK-0610, 2026-11-06: the dead-Collab case now also asserts the
 *    screen's error card on initial load, not only its empty states.)
 *
 * Screenshots continue the app-shell numbering under e2e/screenshots/.
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.join(__dirname, 'screenshots');

function shot(page: Page, name: string) {
  return page.screenshot({ path: path.join(SHOTS, name), fullPage: true });
}

function tabBar(page: Page) {
  return page.getByRole('navigation', { name: 'Primary' });
}

async function openTab(page: Page, label: string) {
  await tabBar(page).getByRole('button', { name: label, exact: true }).click();
}

/** Boot the app in live mode against the stub API. */
async function openLive(page: Page, opts: StubApiOptions = {}) {
  await installStubApi(page, opts);
  await seedLiveSettings(page);
  await page.goto('/');
  await expect(page.getByText('Quantum · DSECT')).toBeVisible();
  await expect(tabBar(page).getByRole('button', { name: 'Home', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
}

/**
 * Boot live AND MCP-configured: the stub worker key in settings is
 * what flips Services & tools and Mail from "not connected" to live
 * (mcpConfigured / mailConfigured both require base URL + key).
 */
async function openLiveMcp(page: Page, opts: StubApiOptions = {}) {
  await installStubApi(page, opts);
  await seedLiveSettings(page, { mcpKey: STUB_MCP_KEY });
  await page.goto('/');
  await expect(page.getByText('Quantum · DSECT')).toBeVisible();
  await expect(tabBar(page).getByRole('button', { name: 'Home', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
}

/**
 * Boot live AND Sol-configured: settings.sol.baseUrl is what flips
 * the Chat tab from "isn't connected" to live (ChatScreen reads the
 * sol field only — the hub URL does not configure Chat).
 */
async function openLiveSol(page: Page, opts: StubApiOptions = {}) {
  await installStubApi(page, opts);
  await seedLiveSettings(page, { solBase: true });
  await page.goto('/');
  await expect(page.getByText('Quantum · DSECT')).toBeVisible();
  await expect(tabBar(page).getByRole('button', { name: 'Home', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
}

/** More → Services & tools, landing on its heading. */
async function openServices(page: Page) {
  await openTab(page, 'More');
  await page.getByRole('button', { name: /Services & tools/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Services & tools', exact: true }),
  ).toBeVisible();
}

test('Home renders the stubbed live estate, not demo mode', async ({ page }) => {
  await openLive(page);

  // No demo labelling anywhere on the live dashboard.
  await expect(page.getByText('Demo mode')).toHaveCount(0);

  // Hero + glance come from /api/summary (2 of 4 services up).
  await expect(page.getByText(/4 services indexed/)).toBeVisible();
  await expect(page.getByText('2 SERVICES DOWN')).toBeVisible();
  await expect(page.getByText('Services online')).toBeVisible();
  await expect(page.getByText('50% reachable')).toBeVisible();

  // Services section: registry merged with probes. 2/4 up, and the
  // median probe the section computes from 12/34/58 ms is 34 ms.
  const summary = page.getByTestId('services-summary');
  await expect(summary).toContainText('2/4');
  await expect(summary).toContainText('34 ms');
  const list = page.getByTestId('services-list');
  for (const name of ['Hub API', 'Nebula', 'Eclipse (Jellyfin)', 'DSECT Mail']) {
    await expect(list.getByText(name)).toBeVisible();
  }

  // Vitals from /api/vitals.
  await expect(page.getByText('37%').first()).toBeVisible();

  // Roster from /api/agents, wishlist from /api/docket/items.
  await expect(page.getByText('Cooper', { exact: true })).toBeVisible();
  await expect(page.getByText('128 ledger entries')).toBeVisible();
  await expect(page.getByText('OVMS kit for Jinx')).toBeVisible();

  await shot(page, '12-home-live-mobile.png');
});

test('services search filters the stubbed registry', async ({ page }) => {
  await openLive(page);
  const list = page.getByTestId('services-list');
  await expect(list.getByText('Nebula')).toBeVisible();

  await page.getByLabel('Search services').fill('eclipse');
  await expect(list.getByText('Eclipse (Jellyfin)')).toBeVisible();
  await expect(list.getByText('Nebula')).toHaveCount(0);
  await expect(list.getByText('Hub API')).toHaveCount(0);

  await shot(page, '13-home-live-search-mobile.png');
});

test('a failing endpoint degrades only its own section', async ({ page }) => {
  await openLive(page, { fail: { '/api/agents': 500 } });

  // The rest of the dashboard is live and unaffected.
  await expect(page.getByTestId('services-summary')).toContainText('2/4');
  await expect(page.getByText('OVMS kit for Jinx')).toBeVisible();
  await expect(page.getByText('Demo mode')).toHaveCount(0);

  // Exactly one section — Agents — shows the honest error state,
  // naming the failing endpoint, with no roster data invented.
  await expect(page.getByText("Couldn't load this section")).toHaveCount(1);
  await expect(page.getByText(/HTTP 500 for \/api\/agents/)).toBeVisible();
  await expect(page.getByText('128 ledger entries')).toHaveCount(0);

  await shot(page, '14-home-partial-failure-mobile.png');
});

test('Create → Jobs renders the stubbed Nebula queue', async ({ page }) => {
  await openLive(page);

  await openTab(page, 'Create');
  await expect(page.getByText('Demo mode')).toHaveCount(0);
  await page.getByRole('tab', { name: 'Jobs' }).click();

  // Queue note from the stub: 1 waiting, 1 active.
  await expect(page.getByText(/waiting for a free backend/)).toBeVisible();
  await expect(page.getByText('Stub render — fox portrait')).toBeVisible();
  await expect(page.getByText('Stub render — harbour at dusk')).toBeVisible();

  await shot(page, '15-create-jobs-live-mobile.png');
});

test('More → Services & tools renders live MCP tools and a services_status result', async ({ page }) => {
  await openLiveMcp(page);
  await openServices(page);

  // Configured (base URL + stub worker key): no demo / not-connected state.
  await expect(page.getByText('Demo mode')).toHaveCount(0);
  await expect(page.getByText('Not connected', { exact: true })).toHaveCount(0);

  // The connect action runs the real client handshake against the stub:
  // initialize (session id via response header) → tools/list.
  await page.getByRole('button', { name: 'Connect to MCP gateway' }).click();
  await expect(page.getByText('Connected — 8 tools')).toBeVisible();
  await expect(page.getByText('dsect_services_status')).toBeVisible();
  await expect(page.getByText('dsect_mail_list')).toBeVisible();

  // Run the curated read-only runner: tools/call dsect_services_status
  // with { only_problems: false } renders the pretty result — the same
  // estate as Part 1 (2 of 4 up; Eclipse down, DSECT Mail degraded).
  await page.getByRole('button', { name: 'Run: Services status' }).click();
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.getByText('2/4 up')).toBeVisible();
  await expect(page.getByText('2 problems')).toBeVisible();
  for (const name of ['Hub API', 'Nebula', 'Eclipse (Jellyfin)', 'DSECT Mail']) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }
  await expect(page.getByText('Demo mode')).toHaveCount(0);

  await shot(page, '16-services-mcp-live-mobile.png');
});

test('a dead MCP gateway degrades only the Services screen', async ({ page }) => {
  await openLiveMcp(page, { mcp: { httpStatus: 500 } });
  await openServices(page);

  await page.getByRole('button', { name: 'Connect to MCP gateway' }).click();

  // The screen's own honest failure card — naming the HTTP failure,
  // offering a retry, and inventing no tool data.
  await expect(page.getByText('Connection failed')).toBeVisible();
  await expect(page.getByText('MCP gateway returned HTTP 500')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
  await expect(page.getByText(/Connected —/)).toHaveCount(0);
  await expect(page.getByText('dsect_services_status')).toHaveCount(0);

  await shot(page, '17-services-mcp-failure-mobile.png');

  // The rest of the app in the same boot is unaffected: Home is still
  // live off the (healthy) stub /api endpoints.
  await openTab(page, 'Home');
  await expect(page.getByTestId('services-summary')).toContainText('2/4');
  await expect(page.getByText('OVMS kit for Jinx')).toBeVisible();
  await expect(page.getByText('Demo mode')).toHaveCount(0);
});

test('Mail renders the fixture inbox over MCP', async ({ page }) => {
  await openLiveMcp(page);

  await openTab(page, 'Mail');
  const list = page.getByRole('list', { name: 'Inbox messages' });

  // dsect_mail_list rows: subjects, senders (the Part 1 roster) and
  // HERALD triage snippets, with the server-matched count up top.
  await expect(page.getByText('3 messages')).toBeVisible();
  for (const subject of [
    'Live-mode fixtures are green',
    'Nebula queue: stub render finished',
    'Docket: OVMS kit for Jinx',
  ]) {
    await expect(list.getByText(subject)).toBeVisible();
  }
  for (const sender of ['Cooper', 'Qubit', 'Helm']) {
    await expect(list.getByText(sender, { exact: true })).toBeVisible();
  }
  await expect(
    list.getByText('Fixture inbox: the live-mode E2E data set is ready.'),
  ).toBeVisible();
  await expect(page.getByText('Mail is not connected')).toHaveCount(0);
  await expect(page.getByText('Demo mode')).toHaveCount(0);

  // Regression guard (TRK-0484): at 390px the rows must not overflow
  // the viewport — the page gains no horizontal scrollbar and every
  // row element (avatar, sender, subject, snippet, date) keeps its
  // bounding box inside the viewport, truncating with ellipsis
  // instead of clipping at the edges.
  const geometry = await list.evaluate((root) => {
    const vw = document.documentElement.clientWidth;
    const outside: string[] = [];
    root.querySelectorAll('button, button *').forEach((n) => {
      const r = n.getBoundingClientRect();
      if (r.left < -1 || r.right > vw + 1) {
        outside.push(`${n.tagName}:${(n.textContent ?? '').slice(0, 32)}`);
      }
    });
    return { vw, scrollWidth: document.documentElement.scrollWidth, outside };
  });
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.vw);
  expect(geometry.outside).toEqual([]);

  await shot(page, '18-mail-inbox-live-mobile.png');
});

test('opening a Mail thread renders its fixture message', async ({ page }) => {
  await openLiveMcp(page);

  await openTab(page, 'Mail');
  await page.getByRole('button', { name: /Live-mode fixtures are green/ }).click();

  // ThreadView: a second connect on the shared client, then
  // dsect_mail_read — subject heading, From header, body, attachments
  // listed by name only.
  await expect(
    page.getByRole('heading', { name: 'Live-mode fixtures are green' }),
  ).toBeVisible();
  await expect(page.getByText('Cooper <cooper@dsect.net>')).toBeVisible();
  await expect(
    page.getByText(/Fixture body: the stub mailbox is rendering live threads/),
  ).toBeVisible();
  await expect(page.getByText('fixture-notes.txt')).toBeVisible();

  await shot(page, '19-mail-thread-live-mobile.png');

  // Back returns to the still-live inbox.
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(page.getByText('Nebula queue: stub render finished')).toBeVisible();
});

test('Create → Gallery list rows stay inside the 390px viewport (TRK-0498)', async ({ page }) => {
  await openLive(page);

  await openTab(page, 'Create');
  await page.getByRole('tab', { name: 'Gallery' }).click();

  // The stub gallery (2 outputs) renders with its loaded/total count.
  const list = page.getByRole('list', { name: 'Generated images' });
  await expect(page.getByText('2 of 2 images')).toBeVisible();

  // Switch to the list layout: one native list-row button per image,
  // thumbnail + basename caption + date/backend line.
  await page.getByRole('radio', { name: 'List view' }).click();
  await expect(list.getByText('stub_fox_portrait_0001.png')).toBeVisible();
  await expect(
    list.getByText(
      'a-very-long-stub-render-filename-that-must-truncate-inside-the-list-row.png',
    ),
  ).toBeVisible();

  // Regression guard (TRK-0498; same geometry contract as the TRK-0484
  // inbox guard): at 390px the rows must not overflow the viewport —
  // the page gains no horizontal scrollbar and every row element
  // (thumbnail, caption) keeps its bounding box inside the viewport,
  // the long basename truncating with ellipsis instead of pushing
  // the row out. Inside a QButton this failed: the vendored Button
  // wrapped the whole row in one nowrap label span.
  const geometry = await list.evaluate((root) => {
    const vw = document.documentElement.clientWidth;
    const outside: string[] = [];
    root.querySelectorAll('button, button *').forEach((n) => {
      const r = n.getBoundingClientRect();
      if (r.left < -1 || r.right > vw + 1) {
        outside.push(`${n.tagName}:${(n.textContent ?? '').slice(0, 32)}`);
      }
    });
    return { vw, scrollWidth: document.documentElement.scrollWidth, outside };
  });
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.vw);
  expect(geometry.outside).toEqual([]);

  await shot(page, '20-create-gallery-list-live-mobile.png');
});

test('Chat renders live Sol models and streams a fixture reply', async ({ page }) => {
  await openLiveSol(page);

  await openTab(page, 'Chat');

  // Live, not demo: the pane connected to the stub gateway.
  await expect(page.getByText("Chat isn't connected")).toHaveCount(0);
  await expect(page.getByText('Demo mode')).toHaveCount(0);

  // The model picker offers exactly the models the gateway reported
  // (GET /api/sol/v1/models -> { data: [{ id }] }).
  const modelSelect = page.getByLabel('Model');
  await expect(modelSelect).toBeVisible();
  await expect(modelSelect.locator('option')).toHaveText(['stub-sol-pro', 'stub-sol-lite']);
  await expect(modelSelect).toHaveValue('stub-sol-pro');

  // A full round trip: new thread, send, and the SSE-streamed fixture
  // reply (POST /api/sol/v1/chat/completions) lands in the thread.
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.getByText('Say hello to Sol')).toBeVisible();
  await page.getByPlaceholder('Message Sol…').fill('Hello from the fixture test');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  // The sent text shows twice by design: the thread title is derived
  // from the first user message, and the bubble renders it too.
  await expect(page.getByRole('heading', { name: 'Hello from the fixture test' })).toBeVisible();
  await expect(page.getByText('Fixture reply: Sol is rendering live tokens.')).toBeVisible();
  await expect(page.getByText('Demo mode')).toHaveCount(0);

  await shot(page, '21-chat-live-mobile.png');
});

test('Chat → Agents renders the live fleet snapshot and a DM thread', async ({ page }) => {
  await openLiveSol(page);

  await openTab(page, 'Chat');
  await page.getByRole('tab', { name: 'Agents' }).click();

  // GET /api/sol/agents -> { agents, desk }: the shared-desk card
  // renders the desk line for holder_kind 'human'.
  await expect(page.getByText('Shared desk')).toBeVisible();
  await expect(page.getByText('You have the desk.')).toBeVisible();
  await expect(page.getByText('Fleet not connected')).toHaveCount(0);
  await expect(page.getByText('Demo mode')).toHaveCount(0);

  // The Part 1 roster with gateway states and activity lines:
  // status.text wins for Cooper and Helm, last_action for Qubit.
  for (const name of ['Cooper', 'Qubit', 'Helm']) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }
  await expect(page.getByText('Working', { exact: true })).toBeVisible();
  await expect(page.getByText('Wiring the live-mode fixtures')).toBeVisible();
  await expect(page.getByText(/Triaged the fixture inbox · 5m ago/)).toBeVisible();
  await expect(page.getByText('Waiting on the OVMS docket review')).toBeVisible();

  // Opening Cooper's row polls GET /api/sol/dm/cooper and renders
  // the fixture DM history in the sheet.
  await page.getByRole('button', { name: /Cooper/ }).click();
  await expect(page.getByText('DM · Cooper')).toBeVisible();
  await expect(page.getByText('Fixture DM: the fleet view is live.')).toBeVisible();
  await expect(page.getByText('Fixture DM: looking good from the desk.')).toBeVisible();

  await shot(page, '22-chat-agents-live-mobile.png');
});

test('Collab renders live goals and expands fixture sub-goals and tasks', async ({ page }) => {
  await openLive(page);

  await openTab(page, 'Collab');

  // GET /api/collab/goals: both fixture goals as cards, with the
  // progress the payload reports — no not-connected state.
  await expect(page.getByText('Collaboration is not connected')).toHaveCount(0);
  await expect(page.getByText('Ship live-mode coverage')).toBeVisible();
  await expect(page.getByText('Fox portrait render')).toBeVisible();
  await expect(page.getByText('50%').first()).toBeVisible();
  await expect(page.getByText('25%').first()).toBeVisible();

  // Expanding a goal fetches GET /api/collab/goals/{id}: description,
  // the sub-goal block, and its task rows with assignee badges.
  await page.getByRole('button', { name: /Ship live-mode coverage/ }).click();
  await expect(page.getByText('Fixture goal: every tab renders live data.')).toBeVisible();
  await expect(page.getByText('Chat and Collab fixtures')).toBeVisible();
  await expect(page.getByText('Stub the Sol and Collab endpoints')).toBeVisible();
  await expect(page.getByText('Ship live-mode part 3')).toBeVisible();

  await shot(page, '23-collab-simple-live-mobile.png');
});

test('Collab → Board renders the fixture kanban and activity feed', async ({ page }) => {
  await openLive(page);

  await openTab(page, 'Collab');
  await page.getByRole('tab', { name: 'Board' }).click();

  // GET /api/collab/board: the three columns with the stub counts
  // (1 todo / 1 doing / 2 done, derived client-side from the columns).
  for (const column of ['To do', 'Doing', 'Done']) {
    await expect(
      page.getByRole('region', { name: `${column} column` }),
    ).toBeVisible();
  }
  const board = page.locator('section');
  await expect(board.getByText('Ship live-mode part 3')).toBeVisible();
  await expect(board.getByText('Stub the Sol and Collab endpoints')).toBeVisible();
  await expect(board.getByText('Ship live-mode part 2 fixtures')).toBeVisible();
  await expect(board.getByText('Finish the stub harbour render')).toBeVisible();
  // Board-enriched context line: goal title › sub-goal title.
  await expect(
    board.getByText('Ship live-mode coverage › Chat and Collab fixtures').first(),
  ).toBeVisible();

  // GET /api/collab/activity feeds the Recent activity card: the
  // newest event renders its kind label ("task move" from task.move).
  await expect(page.getByText('Recent activity')).toBeVisible();
  await expect(page.getByText('task move').first()).toBeVisible();
  await expect(page.getByText('task create').first()).toBeVisible();

  await shot(page, '24-collab-board-live-mobile.png');
});

test('a dead Sol gateway degrades only Chat', async ({ page }) => {
  await openLiveSol(page, {
    fail: { '/api/sol/v1/models': 500, '/api/sol/agents': 500 },
  });

  await openTab(page, 'Chat');

  // The pane's own honest failure state, naming the gateway's HTTP
  // 500 (sol.ts toHttpError) — no fake models, no demo labelling.
  await expect(page.getByText("Can't reach the Sol gateway")).toBeVisible();
  await expect(page.getByText(/The Sol gateway returned HTTP 500/)).toBeVisible();
  await expect(page.getByText("Chat isn't connected")).toHaveCount(0);

  await shot(page, '25-chat-sol-failure-mobile.png');

  // The rest of the app in the same boot is unaffected: Home is still
  // live off the (healthy) stub hub /api endpoints.
  await openTab(page, 'Home');
  await expect(page.getByTestId('services-summary')).toContainText('2/4');
  await expect(page.getByText('OVMS kit for Jinx')).toBeVisible();
  await expect(page.getByText('Demo mode')).toHaveCount(0);
});

test('dead Collab endpoints degrade only Collab', async ({ page }) => {
  await openLive(page, {
    fail: {
      '/api/collab/goals': 500,
      '/api/collab/board': 500,
      '/api/collab/tags': 500,
      '/api/collab/activity': 500,
    },
  });

  await openTab(page, 'Collab');

  // Every Collab call failed on the INITIAL load, so the screen's
  // error card engages immediately (TRK-0610: the initial load now
  // applies the same all-four-failed semantics as refresh()) — the
  // backend-unreachable message with a Retry, not just the empty
  // states. No fixture goal is invented anywhere.
  await expect(
    page.getByText(
      'Could not reach the collaboration backend. Check the tailnet connection.',
    ),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  await expect(page.getByText('Ship live-mode coverage')).toHaveCount(0);
  await page.getByRole('tab', { name: 'Board' }).click();
  // The error card stays up in Board view too, above its own
  // "Board unavailable" empty state.
  await expect(
    page.getByText(
      'Could not reach the collaboration backend. Check the tailnet connection.',
    ),
  ).toBeVisible();
  await expect(page.getByText('Board unavailable')).toBeVisible();
  await expect(page.getByText('Ship live-mode part 3')).toHaveCount(0);

  await shot(page, '26-collab-failure-mobile.png');

  // The rest of the app in the same boot is unaffected: Home is still
  // live off the (healthy) stub hub /api endpoints.
  await openTab(page, 'Home');
  await expect(page.getByTestId('services-summary')).toContainText('2/4');
  await expect(page.getByText('OVMS kit for Jinx')).toBeVisible();
  await expect(page.getByText('Demo mode')).toHaveCount(0);
});
