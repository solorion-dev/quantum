import { describe, it, expect, vi, afterEach } from 'vitest';
import { BoardApiClient } from './client.js';

describe('BoardApiClient', () => {
  afterEach(() => vi.restoreAllMocks());

  it('defaults to same-origin (empty base URL)', () => {
    const client = new BoardApiClient();
    expect(client.getBaseUrl()).toBe('');
  });

  it('requests state from /api/v1/state', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ boards: [], items: [], activity: [] }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    const client = new BoardApiClient();
    const state = await client.getState();
    expect(state.boards).toEqual([]);
    const [url] = fetchMock.mock.calls[0] as any[];
    expect(url).toBe('/api/v1/state?activityLimit=100');
  });

  it('surfaces API error messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ message: 'item title is required' }),
      }))
    );
    const client = new BoardApiClient();
    await expect(client.createItem({ title: '' })).rejects.toThrow('item title is required');
  });
});
