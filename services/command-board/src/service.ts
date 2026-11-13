import { randomUUID } from 'node:crypto';
import type Database from 'better-sqlite3';
import { getCurrentSchemaVersion } from './db.js';
import {
  ActivityEntry,
  Board,
  BoardComment,
  BoardItem,
  BoardState,
  ChangeRow,
  ColumnId,
  Origin,
  Subtask,
} from './types.js';

const nowIso = () => new Date().toISOString();

export class NotFoundError extends Error {
  status = 404;
  constructor(message: string) {
    super(message);
    this.name = 'NotFoundError';
  }
}

export class ValidationError extends Error {
  status = 400;
  constructor(message: string) {
    super(message);
    this.name = 'ValidationError';
  }
}

interface BoardRow {
  id: string;
  name: string;
  sort_order: number;
  origin: Origin;
  space_id: string | null;
  created_at: string;
  updated_at: string;
}

interface ItemRow {
  id: string;
  board_id: string | null;
  column_id: ColumnId;
  kind: 'task' | 'idea';
  title: string;
  detail: string;
  priority: number;
  assignee: 'scotty' | 'cooper';
  checked: number;
  cooper_status: string | null;
  trk_id: string | null;
  created_by: string;
  origin: Origin;
  space_id: string | null;
  rev: number;
  created_at: string;
  updated_at: string;
}

interface SubtaskRow {
  id: string;
  item_id: string;
  title: string;
  checked: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

interface CommentRow {
  id: string;
  item_id: string;
  author: string;
  body: string;
  origin: Origin;
  space_id: string | null;
  created_at: string;
}

const mapBoard = (r: BoardRow): Board => ({
  id: r.id,
  name: r.name,
  sortOrder: r.sort_order,
  origin: r.origin,
  spaceId: r.space_id,
  createdAt: r.created_at,
  updatedAt: r.updated_at,
});

const mapSubtask = (r: SubtaskRow): Subtask => ({
  id: r.id,
  itemId: r.item_id,
  title: r.title,
  checked: r.checked === 1,
  sortOrder: r.sort_order,
  createdAt: r.created_at,
  updatedAt: r.updated_at,
});

const mapComment = (r: CommentRow): BoardComment => ({
  id: r.id,
  itemId: r.item_id,
  author: r.author,
  body: r.body,
  origin: r.origin,
  spaceId: r.space_id,
  createdAt: r.created_at,
});

export interface CreateItemInput {
  title: string;
  detail?: string;
  kind?: 'task' | 'idea';
  boardId?: string | null;
  column?: ColumnId;
  priority?: boolean;
  assignee?: 'scotty' | 'cooper';
  createdBy?: string;
  origin?: Origin;
  spaceId?: string | null;
  trkId?: string | null;
}

export interface UpdateItemPatch {
  title?: string;
  detail?: string;
  kind?: 'task' | 'idea';
  boardId?: string | null;
  column?: ColumnId;
  priority?: boolean;
  assignee?: 'scotty' | 'cooper';
  checked?: boolean;
  cooperStatus?: string | null;
  trkId?: string | null;
}

export class BoardService {
  constructor(private db: Database.Database) {}

  getSchemaVersion(): number {
    return getCurrentSchemaVersion(this.db);
  }

  // ---------- internal helpers ----------

  private logChange(entity: ChangeRow['entity'], entityId: string, op: 'upsert' | 'delete', origin: Origin): void {
    this.db
      .prepare('INSERT INTO changes (entity, entity_id, op, origin, at) VALUES (?, ?, ?, ?, ?)')
      .run(entity, entityId, op, origin, nowIso());
  }

  private logActivity(itemId: string | null, actor: string, text: string): ActivityEntry {
    const info = this.db
      .prepare('INSERT INTO activity (item_id, actor, text, created_at) VALUES (?, ?, ?, ?)')
      .run(itemId, actor, text, nowIso());
    const row = this.db.prepare('SELECT * FROM activity WHERE id = ?').get(info.lastInsertRowid) as any;
    return { id: row.id, itemId: row.item_id, actor: row.actor, text: row.text, createdAt: row.created_at };
  }

  private boardRow(id: string): BoardRow {
    const row = this.db.prepare('SELECT * FROM boards WHERE id = ?').get(id) as BoardRow | undefined;
    if (!row) throw new NotFoundError(`board ${id} not found`);
    return row;
  }

  private itemRow(id: string): ItemRow {
    const row = this.db.prepare('SELECT * FROM items WHERE id = ?').get(id) as ItemRow | undefined;
    if (!row) throw new NotFoundError(`item ${id} not found`);
    return row;
  }

  private hydrateItem(row: ItemRow): BoardItem {
    const subtasks = (
      this.db.prepare('SELECT * FROM subtasks WHERE item_id = ? ORDER BY sort_order, created_at').all(row.id) as SubtaskRow[]
    ).map(mapSubtask);
    const comments = (
      this.db.prepare('SELECT * FROM comments WHERE item_id = ? ORDER BY created_at').all(row.id) as CommentRow[]
    ).map(mapComment);
    return {
      id: row.id,
      boardId: row.board_id,
      column: row.column_id,
      kind: row.kind,
      title: row.title,
      detail: row.detail,
      priority: row.priority === 1,
      assignee: row.assignee,
      checked: row.checked === 1,
      cooperStatus: row.cooper_status,
      trkId: row.trk_id,
      createdBy: row.created_by,
      origin: row.origin,
      spaceId: row.space_id,
      rev: row.rev,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      subtasks,
      comments,
    };
  }

  // ---------- boards ----------

  listBoards(): Board[] {
    return (this.db.prepare('SELECT * FROM boards ORDER BY sort_order, created_at').all() as BoardRow[]).map(mapBoard);
  }

  getBoard(id: string): Board {
    return mapBoard(this.boardRow(id));
  }

  createBoard(input: { name: string; origin?: Origin; spaceId?: string | null }, actor = 'scotty'): Board {
    const name = (input.name || '').trim();
    if (!name) throw new ValidationError('board name is required');
    const ts = nowIso();
    const maxSort = this.db.prepare('SELECT MAX(sort_order) as m FROM boards').get() as { m: number | null };
    const board: Board = {
      id: randomUUID(),
      name,
      sortOrder: (maxSort.m ?? -1) + 1,
      origin: input.origin ?? 'app',
      spaceId: input.spaceId ?? null,
      createdAt: ts,
      updatedAt: ts,
    };
    this.db
      .prepare(
        'INSERT INTO boards (id, name, sort_order, origin, space_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
      )
      .run(board.id, board.name, board.sortOrder, board.origin, board.spaceId, board.createdAt, board.updatedAt);
    this.logChange('board', board.id, 'upsert', board.origin);
    this.logActivity(null, actor, `${actor === 'cooper' ? 'Cooper' : 'Scotty'} created board "${board.name}"`);
    return board;
  }

  deleteBoard(id: string, actor = 'scotty'): void {
    const board = this.boardRow(id);
    const ts = nowIso();
    // Mirror the Space: deleting a board returns its items to the Inbox unfiled.
    const items = this.db.prepare('SELECT id FROM items WHERE board_id = ?').all(id) as Array<{ id: string }>;
    const unfile = this.db.prepare(
      "UPDATE items SET board_id = NULL, column_id = 'inbox', updated_at = ?, rev = rev + 1 WHERE id = ?"
    );
    for (const it of items) {
      unfile.run(ts, it.id);
      this.logChange('item', it.id, 'upsert', 'app');
    }
    this.db.prepare('DELETE FROM boards WHERE id = ?').run(id);
    this.logChange('board', id, 'delete', 'app');
    this.logActivity(null, actor, `Board "${board.name}" deleted; its items returned to the Inbox`);
  }

  // ---------- items ----------

  listItems(filter: { boardId?: string | null; column?: ColumnId } = {}): BoardItem[] {
    let sql = 'SELECT * FROM items';
    const clauses: string[] = [];
    const params: unknown[] = [];
    if (filter.boardId !== undefined) {
      if (filter.boardId === null) clauses.push('board_id IS NULL');
      else {
        clauses.push('board_id = ?');
        params.push(filter.boardId);
      }
    }
    if (filter.column) {
      clauses.push('column_id = ?');
      params.push(filter.column);
    }
    if (clauses.length) sql += ' WHERE ' + clauses.join(' AND ');
    sql += ' ORDER BY created_at';
    return (this.db.prepare(sql).all(...params) as ItemRow[]).map((r) => this.hydrateItem(r));
  }

  getItem(id: string): BoardItem {
    return this.hydrateItem(this.itemRow(id));
  }

  createItem(input: CreateItemInput, actor?: string): BoardItem {
    const title = (input.title || '').trim();
    if (!title) throw new ValidationError('item title is required');
    if (input.boardId) this.boardRow(input.boardId);
    const ts = nowIso();
    const origin = input.origin ?? 'app';
    const createdBy = input.createdBy ?? 'scotty';
    const id = randomUUID();
    this.db
      .prepare(
        `INSERT INTO items (id, board_id, column_id, kind, title, detail, priority, assignee, checked,
                            cooper_status, trk_id, created_by, origin, space_id, rev, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, ?, 1, ?, ?)`
      )
      .run(
        id,
        input.boardId ?? null,
        input.column ?? 'inbox',
        input.kind ?? 'task',
        title,
        input.detail ?? '',
        input.priority ? 1 : 0,
        input.assignee ?? 'cooper',
        input.trkId ?? null,
        createdBy,
        origin,
        input.spaceId ?? null,
        ts,
        ts
      );
    this.logChange('item', id, 'upsert', origin);
    const who = actor ?? createdBy;
    this.logActivity(id, who, `${who === 'cooper' ? 'Cooper' : 'Scotty'} captured: ${title}`);
    return this.getItem(id);
  }

  updateItem(id: string, patch: UpdateItemPatch, actor = 'cooper', origin: Origin = 'app'): BoardItem {
    const row = this.itemRow(id);
    if (patch.boardId) this.boardRow(patch.boardId);
    const next: ItemRow = {
      ...row,
      title: patch.title !== undefined ? patch.title.trim() : row.title,
      detail: patch.detail !== undefined ? patch.detail : row.detail,
      kind: patch.kind ?? row.kind,
      board_id: patch.boardId !== undefined ? patch.boardId : row.board_id,
      column_id: patch.column ?? row.column_id,
      priority: patch.priority !== undefined ? (patch.priority ? 1 : 0) : row.priority,
      assignee: patch.assignee ?? row.assignee,
      checked: patch.checked !== undefined ? (patch.checked ? 1 : 0) : row.checked,
      cooper_status: patch.cooperStatus !== undefined ? patch.cooperStatus : row.cooper_status,
      trk_id: patch.trkId !== undefined ? patch.trkId : row.trk_id,
    };
    if (!next.title) throw new ValidationError('item title cannot be empty');
    const ts = nowIso();
    this.db
      .prepare(
        `UPDATE items SET board_id = ?, column_id = ?, kind = ?, title = ?, detail = ?, priority = ?,
                          assignee = ?, checked = ?, cooper_status = ?, trk_id = ?, rev = rev + 1, updated_at = ?
         WHERE id = ?`
      )
      .run(
        next.board_id,
        next.column_id,
        next.kind,
        next.title,
        next.detail,
        next.priority,
        next.assignee,
        next.checked,
        next.cooper_status,
        next.trk_id,
        ts,
        id
      );
    this.logChange('item', id, 'upsert', origin);
    if (patch.column && patch.column !== row.column_id) {
      this.logActivity(id, actor, `Moved "${next.title}" to ${patch.column}`);
    } else if (patch.checked !== undefined && (patch.checked ? 1 : 0) !== row.checked) {
      this.logActivity(id, actor, `${patch.checked ? 'Checked off' : 'Reopened'}: ${next.title}`);
    }
    return this.getItem(id);
  }

  deleteItem(id: string, actor = 'scotty'): void {
    const row = this.itemRow(id);
    this.db.prepare('DELETE FROM items WHERE id = ?').run(id);
    this.logChange('item', id, 'delete', 'app');
    this.logActivity(id, actor, `Deleted item: ${row.title}`);
  }

  // ---------- comments & subtasks ----------

  addComment(
    itemId: string,
    input: { author: string; body: string; origin?: Origin; spaceId?: string | null }
  ): BoardComment {
    this.itemRow(itemId);
    const body = (input.body || '').trim();
    if (!body) throw new ValidationError('comment body is required');
    const comment: BoardComment = {
      id: randomUUID(),
      itemId,
      author: input.author || 'scotty',
      body,
      origin: input.origin ?? 'app',
      spaceId: input.spaceId ?? null,
      createdAt: nowIso(),
    };
    this.db
      .prepare('INSERT INTO comments (id, item_id, author, body, origin, space_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)')
      .run(comment.id, comment.itemId, comment.author, comment.body, comment.origin, comment.spaceId, comment.createdAt);
    this.logChange('comment', comment.id, 'upsert', comment.origin);
    return comment;
  }

  addSubtask(itemId: string, title: string): Subtask {
    this.itemRow(itemId);
    const clean = (title || '').trim();
    if (!clean) throw new ValidationError('subtask title is required');
    const ts = nowIso();
    const maxSort = this.db
      .prepare('SELECT MAX(sort_order) as m FROM subtasks WHERE item_id = ?')
      .get(itemId) as { m: number | null };
    const sub: Subtask = {
      id: randomUUID(),
      itemId,
      title: clean,
      checked: false,
      sortOrder: (maxSort.m ?? -1) + 1,
      createdAt: ts,
      updatedAt: ts,
    };
    this.db
      .prepare('INSERT INTO subtasks (id, item_id, title, checked, sort_order, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?, ?)')
      .run(sub.id, sub.itemId, sub.title, sub.sortOrder, sub.createdAt, sub.updatedAt);
    this.logChange('subtask', sub.id, 'upsert', 'app');
    return sub;
  }

  updateSubtask(subtaskId: string, patch: { title?: string; checked?: boolean }): Subtask {
    const row = this.db.prepare('SELECT * FROM subtasks WHERE id = ?').get(subtaskId) as SubtaskRow | undefined;
    if (!row) throw new NotFoundError(`subtask ${subtaskId} not found`);
    const title = patch.title !== undefined ? patch.title.trim() : row.title;
    if (!title) throw new ValidationError('subtask title cannot be empty');
    const checked = patch.checked !== undefined ? (patch.checked ? 1 : 0) : row.checked;
    const ts = nowIso();
    this.db.prepare('UPDATE subtasks SET title = ?, checked = ?, updated_at = ? WHERE id = ?').run(title, checked, ts, subtaskId);
    this.logChange('subtask', subtaskId, 'upsert', 'app');
    return mapSubtask({ ...row, title, checked, updated_at: ts });
  }

  deleteSubtask(subtaskId: string): void {
    const info = this.db.prepare('DELETE FROM subtasks WHERE id = ?').run(subtaskId);
    if (info.changes === 0) throw new NotFoundError(`subtask ${subtaskId} not found`);
    this.logChange('subtask', subtaskId, 'delete', 'app');
  }

  // ---------- Cooper composite (mirrors the Space cooperupdate action) ----------

  cooperUpdate(
    itemId: string,
    input: UpdateItemPatch & { comment?: string; activityText?: string },
    actor = 'cooper'
  ): BoardItem {
    let item = this.updateItem(itemId, input, actor, 'mcp');
    if (input.comment) {
      this.addComment(itemId, { author: 'cooper', body: input.comment, origin: 'mcp' });
      item = this.getItem(itemId);
    }
    if (input.activityText) {
      this.logActivity(itemId, actor, input.activityText);
    } else if (input.comment || input.cooperStatus) {
      this.logActivity(itemId, actor, `Cooper updated: ${item.title}`);
    }
    return item;
  }

  // ---------- state & activity ----------

  getState(activityLimit = 100): BoardState {
    const boards = this.listBoards();
    const items = (this.db.prepare('SELECT * FROM items ORDER BY created_at').all() as ItemRow[]).map((r) =>
      this.hydrateItem(r)
    );
    const activity = this.listActivity(activityLimit);
    return { boards, items, activity };
  }

  listActivity(limit = 100): ActivityEntry[] {
    const rows = this.db
      .prepare('SELECT * FROM activity ORDER BY id DESC LIMIT ?')
      .all(Math.max(1, Math.min(limit, 500))) as any[];
    return rows.map((r) => ({ id: r.id, itemId: r.item_id, actor: r.actor, text: r.text, createdAt: r.created_at }));
  }

  getCounts(): { boards: number; items: number } {
    const b = this.db.prepare('SELECT COUNT(*) as c FROM boards').get() as { c: number };
    const i = this.db.prepare('SELECT COUNT(*) as c FROM items').get() as { c: number };
    return { boards: b.c, items: i.c };
  }

  // ---------- sync (see SYNC.md) ----------

  listChanges(since = 0, limit = 1000): { changes: ChangeRow[]; cursor: number } {
    const rows = this.db
      .prepare('SELECT * FROM changes WHERE seq > ? ORDER BY seq ASC LIMIT ?')
      .all(since, Math.max(1, Math.min(limit, 5000))) as any[];
    const changes: ChangeRow[] = rows.map((r) => ({
      seq: r.seq,
      entity: r.entity,
      entityId: r.entity_id,
      op: r.op,
      origin: r.origin,
      at: r.at,
    }));
    const cursor = changes.length ? changes[changes.length - 1].seq : since;
    return { changes, cursor };
  }

  /** Resolve the current full row for a change entry (sync payload fetch). */
  entitySnapshot(entity: ChangeRow['entity'], entityId: string): unknown | null {
    switch (entity) {
      case 'board': {
        const row = this.db.prepare('SELECT * FROM boards WHERE id = ?').get(entityId) as BoardRow | undefined;
        return row ? mapBoard(row) : null;
      }
      case 'item': {
        const row = this.db.prepare('SELECT * FROM items WHERE id = ?').get(entityId) as ItemRow | undefined;
        return row ? this.hydrateItem(row) : null;
      }
      case 'comment': {
        const row = this.db.prepare('SELECT * FROM comments WHERE id = ?').get(entityId) as CommentRow | undefined;
        return row ? mapComment(row) : null;
      }
      case 'subtask': {
        const row = this.db.prepare('SELECT * FROM subtasks WHERE id = ?').get(entityId) as SubtaskRow | undefined;
        return row ? mapSubtask(row) : null;
      }
      default:
        return null;
    }
  }

  findItemBySpaceId(spaceId: string): BoardItem | null {
    const row = this.db.prepare('SELECT * FROM items WHERE space_id = ?').get(spaceId) as ItemRow | undefined;
    return row ? this.hydrateItem(row) : null;
  }

  findBoardBySpaceId(spaceId: string): Board | null {
    const row = this.db.prepare('SELECT * FROM boards WHERE space_id = ?').get(spaceId) as BoardRow | undefined;
    return row ? mapBoard(row) : null;
  }
}
