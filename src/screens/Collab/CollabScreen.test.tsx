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
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

const CREATE_ERROR_TEXT =
  'Could not create the goal. Check the connection and try again.';

const NEW_GOAL = {
  id: 'g2',
  title: 'Brand new goal',
  description: null,
  status: 'active',
  owner: null,
  tags: [],
  progress: 0,
};

function mockFetchWithMethod(
  handler: (url: string, method: string) => Response | Promise<Response>,
) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(String(input), init?.method ?? 'GET'),
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}


// jsdom does not implement the native <dialog> showModal()/close() that
// the @dsect/ui Dialog drives its open state through; stand-ins toggle
// the `open` property, which is what the creation tests assert on.
HTMLDialogElement.prototype.showModal = function showModal() {
  this.open = true;
};
HTMLDialogElement.prototype.close = function close() {
  this.open = false;
};

describe('CollabScreen goal creation (TRK-0616)', () => {
  it('shows an inline error in the dialog and preserves input when create fails', async () => {
    setHubUrl(BASE);
    mockFetchWithMethod((url, method) => {
      if (method === 'POST' && url.includes('/api/collab/goals'))
        return json({ error: 'boom' }, 500);
      return healthy(url);
    });
    render(<CollabScreen />);

    expect(await screen.findByText('Ship live-mode coverage')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Goal' }));
    const titleField = await screen.findByLabelText('Title');
    fireEvent.change(titleField, { target: { value: 'A goal that will fail' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create goal' }));

    expect(await screen.findByText(CREATE_ERROR_TEXT)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(CREATE_ERROR_TEXT);
    // Dialog stays open and the typed title is preserved for retry.
    expect(screen.getByLabelText('Title')).toHaveValue('A goal that will fail');
    expect(screen.getByLabelText('Title').closest('dialog')?.open).toBe(true);
    // The global initial-load error card must not appear as a duplicate.
    expect(screen.queryByText(ERROR_TEXT)).not.toBeInTheDocument();
  });

  it('closes the dialog and refreshes the list when create succeeds', async () => {
    setHubUrl(BASE);
    let created = false;
    let goalGets = 0;
    mockFetchWithMethod((url, method) => {
      if (method === 'POST' && url.includes('/api/collab/goals')) {
        created = true;
        return json(NEW_GOAL, 201);
      }
      if (url.includes('/api/collab/goals')) {
        goalGets += 1;
        return json(created ? [GOAL, NEW_GOAL] : [GOAL]);
      }
      return healthy(url);
    });
    render(<CollabScreen />);

    expect(await screen.findByText('Ship live-mode coverage')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Goal' }));
    const titleField = await screen.findByLabelText('Title');
    fireEvent.change(titleField, { target: { value: 'Brand new goal' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create goal' }));

    // Dialog closes (the native dialog's open flag drops; the closed
    // dialog is not presented) and no create error is shown.
    const dialog = titleField.closest('dialog');
    await waitFor(() => expect(dialog?.open).toBe(false));
    expect(screen.getByLabelText('Title')).toHaveValue('');
    expect(screen.queryByText(CREATE_ERROR_TEXT)).not.toBeInTheDocument();
    // Refresh re-fetched the list and the created goal now renders.
    expect(goalGets).toBeGreaterThanOrEqual(2);
    expect(await screen.findByText('Brand new goal')).toBeInTheDocument();
  });
});
