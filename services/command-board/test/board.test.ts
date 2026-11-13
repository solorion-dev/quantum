import { describe, it, expect, beforeEach } from 'vitest';
import { openDatabase } from '../src/db.js';
import { BoardService } from '../src/service.js';
import { seedIfEmpty } from '../src/seed.js';
import { createServer } from '../src/server.js';

function freshService(): BoardService {
  const db = openDatabase(':memory:');
  return new BoardService(db);
}

describe('BoardService', () => {
  let svc: BoardService;
  beforeEach(() => {
    svc = freshService();
  });

  it('creates boards and captures items into the inbox by default', () => {
    const board = svc.createBoard({ name: 'Main' });
    expect(board.name).toBe('Main');
    const item = svc.createItem({ title: 'Quick capture test' });
    expect(item.column).toBe('inbox');
    expect(item.boardId).toBeNull();
    expect(item.assignee).toBe('cooper');
    expect(item.checked).toBe(false);
    expect(item.rev).toBe(1);
  });

  it('files an item onto a board/column and bumps rev', () => {
    const board = svc.createBoard({ name: 'Money' });
    const item = svc.createItem({ title: 'Pay thing' });
    const moved = svc.updateItem(item.id, { boardId: board.id, column: 'now' });
    expect(moved.boardId).toBe(board.id);
    expect(moved.column).toBe('now');
    expect(moved.rev).toBe(2);
  });

  it('rejects empty titles and unknown boards', () => {
    expect(() => svc.createItem({ title: '  ' })).toThrowError(/title is required/);
    expect(() => svc.createItem({ title: 'x', boardId: 'nope' })).toThrowError(/not found/);
  });

  it('supports comments, subtasks and the cooper composite update', () => {
    const item = svc.createItem({ title: 'Work me' });
    const sub = svc.addSubtask(item.id, 'step one');
    expect(sub.checked).toBe(false);
    const done = svc.updateSubtask(sub.id, { checked: true });
    expect(done.checked).toBe(true);

    const updated = svc.cooperUpdate(item.id, {
      cooperStatus: 'Picked up',
      trkId: 'TRK-0001',
      comment: 'On it.',
    });
    expect(updated.cooperStatus).toBe('Picked up');
    expect(updated.trkId).toBe('TRK-0001');
    expect(updated.comments).toHaveLength(1);
    expect(updated.comments[0].author).toBe('cooper');
    expect(updated.subtasks).toHaveLength(1);
  });

  it('deleting a board returns its items to the inbox', () => {
    const board = svc.createBoard({ name: 'Temp' });
    const item = svc.createItem({ title: 'Orphan', boardId: board.id, column: 'next' });
    svc.deleteBoard(board.id);
    const after = svc.getItem(item.id);
    expect(after.boardId).toBeNull();
    expect(after.column).toBe('inbox');
  });

  it('records changes for sync and resolves snapshots', () => {
    const item = svc.createItem({ title: 'Sync me' });
    const { changes, cursor } = svc.listChanges(0);
    expect(cursor).toBeGreaterThan(0);
    const itemChange = changes.find((c) => c.entity === 'item' && c.entityId === item.id);
    expect(itemChange).toBeTruthy();
    const snap = svc.entitySnapshot('item', item.id) as { title: string };
    expect(snap.title).toBe('Sync me');
  });

  it('seeds the real backlog exactly once', () => {
    const db = openDatabase(':memory:');
    expect(seedIfEmpty(db)).toBe(true);
    expect(seedIfEmpty(db)).toBe(false);
    const seeded = new BoardService(db);
    const state = seeded.getState();
    expect(state.boards.map((b) => b.name)).toEqual([
      'Main',
      'Minecraft',
      'Quantum / Fleet',
      'Money',
      'Leave & Paperwork',
      'Creative',
      'Home',
    ]);
    expect(state.items.length).toBe(9);
    expect(state.items.find((i) => i.trkId === 'TRK-0686')).toBeTruthy();
  });
});

describe('REST API', () => {
  it('serves state, captures items and accepts sync pushes', async () => {
    const server = await createServer({ dbPath: ':memory:', port: 0 });
    const base = 'http://127.0.0.1:8798'; // placeholder; use inject instead
    void base;
    try {
      const stateRes = await server.app.inject({ method: 'GET', url: '/api/v1/state' });
      expect(stateRes.statusCode).toBe(200);
      const state = stateRes.json();
      expect(state.boards).toHaveLength(7);
      expect(state.items).toHaveLength(9);

      const createRes = await server.app.inject({
        method: 'POST',
        url: '/api/v1/items',
        payload: { title: 'From REST', kind: 'idea' },
      });
      expect(createRes.statusCode).toBe(201);
      const created = createRes.json();
      expect(created.kind).toBe('idea');
      expect(created.column).toBe('inbox');

      const commentRes = await server.app.inject({
        method: 'POST',
        url: `/api/v1/items/${created.id}/cooper-update`,
        payload: { cooperStatus: 'Filed', comment: 'Filed to Main.', column: 'next' },
      });
      expect(commentRes.statusCode).toBe(200);
      expect(commentRes.json().cooperStatus).toBe('Filed');

      const pushRes = await server.app.inject({
        method: 'POST',
        url: '/api/v1/sync/push',
        payload: {
          entities: [
            {
              entity: 'item',
              spaceId: 'space-item-1',
              updatedAt: new Date().toISOString(),
              data: { title: 'Pushed from Space', column: 'inbox', createdBy: 'scotty' },
            },
          ],
        },
      });
      expect(pushRes.statusCode).toBe(200);
      const results = pushRes.json().results;
      expect(results[0].applied).toBe(true);

      const changesRes = await server.app.inject({ method: 'GET', url: '/api/v1/sync/changes?since=0' });
      expect(changesRes.statusCode).toBe(200);
      expect(changesRes.json().cursor).toBeGreaterThan(0);

      const missingRes = await server.app.inject({ method: 'GET', url: '/api/v1/items/nope' });
      expect(missingRes.statusCode).toBe(404);
    } finally {
      await server.close();
    }
  });

  it('enforces the bearer token when one is configured', async () => {
    const server = await createServer({ dbPath: ':memory:', port: 0, token: 'test-token' });
    try {
      const denied = await server.app.inject({ method: 'GET', url: '/api/v1/state' });
      expect(denied.statusCode).toBe(401);
      const allowed = await server.app.inject({
        method: 'GET',
        url: '/api/v1/state',
        headers: { authorization: 'Bearer test-token' },
      });
      expect(allowed.statusCode).toBe(200);
    } finally {
      await server.close();
    }
  });
});
