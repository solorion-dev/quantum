/**
 * CollabScreen tests — the initial-load error contract (TRK-0610):
 *  - total backend failure on the INITIAL load sets the error card
 *    (previously only refresh() did; a dead backend painted the
 *    "No goals yet" / "Board unavailable" empty states instead)
 *  - partial failure still degrades independently with NO error card
 *    (the Promise.allSettled design refresh() already had)
 *  - a healthy backend renders goals with no error card
 *
 * Fetch is mocked at the CollabClient boundary, following the
 * HomeScreen.test.tsx pattern: real payloads in, rendered states out.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CollabScreen } from './CollabScreen';
import { SETTINGS_KEY } from '../../lib/settings';

const BASE = 'https://tritium-linux.fairy-chinstrap.ts.net';
const ERROR_TEXT =
  'Could not reach the collaboration backend. Check the tailnet connection.';

function setHubUrl(url: string) {
  window.localStorage.setItem(
    SETTINGS_KEY,
    JSON.stringify({
      hub: { baseUrl: url },
      nebula: { baseUrl: '' },
      relay: { baseUrl: '' },
      sol: { baseUrl: '' },
      mcpKey: '',
      nebulaPassphrase: '',
    }),
  );
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function mockFetch(handler: (url: string) => Response | Promise<Response>) {
  const fn = vi.fn(async (input: RequestInfo | URL) => handler(String(input)));
  vi.stubGlobal('fetch', fn);
  return fn;
}

const GOAL = {
  id: 'g1',
  title: 'Ship live-mode coverage',
  description: null,
  status: 'active',
  owner: null,
  tags: [],
  progress: 0.5,
};

function healthy(url: string): Response {
  if (url.includes('/api/collab/goals')) return json([GOAL]);
  if (url.includes('/api/collab/board'))
    return json({ goalId: null, columns: { todo: [], doing: [], done: [] } });
  if (url.includes('/api/collab/tags')) return json([]);
  if (url.includes('/api/collab/activity')) return json([]);
  throw new Error(`unexpected ${url}`);
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('CollabScreen initial load', () => {
  it('shows the error card when all four collab calls fail on initial load', async () => {
    setHubUrl(BASE);
    mockFetch(() => json({ error: 'down' }, 500));
    render(<CollabScreen />);

    expect(await screen.findByText(ERROR_TEXT)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.queryByText('Ship live-mode coverage')).not.toBeInTheDocument();
  });

  it('shows no error card when only some collab calls fail', async () => {
    setHubUrl(BASE);
    mockFetch((url) =>
      url.includes('/api/collab/goals') ? json([GOAL]) : json({ error: 'down' }, 500),
    );
    render(<CollabScreen />);

    // The fulfilled section renders live; partial failure degrades
    // per section and must not raise the total-failure card.
    expect(await screen.findByText('Ship live-mode coverage')).toBeInTheDocument();
    expect(screen.queryByText(ERROR_TEXT)).not.toBeInTheDocument();
  });

  it('renders goals with no error card when the backend is healthy', async () => {
    setHubUrl(BASE);
    mockFetch(healthy);
    render(<CollabScreen />);

    expect(await screen.findByText('Ship live-mode coverage')).toBeInTheDocument();
    expect(screen.queryByText(ERROR_TEXT)).not.toBeInTheDocument();
    expect(screen.queryByText('Collaboration is not connected')).not.toBeInTheDocument();
  });
});
