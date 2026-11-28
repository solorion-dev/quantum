import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { BoardService, NotFoundError, ValidationError } from './service.js';
import { COLUMNS } from './types.js';

const columnEnum = z.enum(COLUMNS);
const kindEnum = z.enum(['task', 'idea']);
const assigneeEnum = z.enum(['scotty', 'cooper']);

const createBoardSchema = z.object({
  name: z.string().min(1).max(120),
  origin: z.enum(['app', 'space', 'mcp', 'seed']).optional(),
  spaceId: z.string().max(120).nullable().optional(),
});

const createItemSchema = z.object({
  title: z.string().min(1).max(500),
  detail: z.string().max(20000).optional(),
  kind: kindEnum.optional(),
  boardId: z.string().nullable().optional(),
  column: columnEnum.optional(),
  priority: z.boolean().optional(),
  assignee: assigneeEnum.optional(),
  createdBy: z.string().max(60).optional(),
  origin: z.enum(['app', 'space', 'mcp', 'seed']).optional(),
  spaceId: z.string().max(120).nullable().optional(),
  trkId: z.string().max(40).nullable().optional(),
});

const updateItemSchema = z.object({
  title: z.string().min(1).max(500).optional(),
  detail: z.string().max(20000).optional(),
  kind: kindEnum.optional(),
  boardId: z.string().nullable().optional(),
  column: columnEnum.optional(),
  priority: z.boolean().optional(),
  assignee: assigneeEnum.optional(),
  checked: z.boolean().optional(),
  cooperStatus: z.string().max(500).nullable().optional(),
  trkId: z.string().max(40).nullable().optional(),
});

const cooperUpdateSchema = updateItemSchema.extend({
  comment: z.string().min(1).max(4000).optional(),
  activityText: z.string().max(300).optional(),
});

const commentSchema = z.object({
  author: z.string().min(1).max(60),
  body: z.string().min(1).max(4000),
  origin: z.enum(['app', 'space', 'mcp', 'seed']).optional(),
  spaceId: z.string().max(120).nullable().optional(),
});

const subtaskCreateSchema = z.object({ title: z.string().min(1).max(300) });
const subtaskUpdateSchema = z.object({
  title: z.string().min(1).max(300).optional(),
  checked: z.boolean().optional(),
});

// Sync push entity (SYNC.md): a Space-side row keyed by its Space id.
// Last-write-wins per entity by updatedAt; comments are append-only.
const syncEntitySchema = z.object({
  entity: z.enum(['board', 'item', 'comment']),
  spaceId: z.string().min(1).max(120),
  updatedAt: z.string().max(40),
  data: z.record(z.string(), z.unknown()),
});
const syncPushSchema = z.object({ entities: z.array(syncEntitySchema).max(500) });

function parse<T>(schema: z.ZodSchema<T>, body: unknown): T {
  const result = schema.safeParse(body ?? {});
  if (!result.success) {
    throw new ValidationError(result.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; '));
  }
  return result.data;
}

export function registerRestRoutes(app: FastifyInstance, service: BoardService): void {
  const wrap =
    (fn: (req: any, reply: any) => Promise<unknown> | unknown) =>
    async (req: any, reply: any) => {
      try {
        const out = await fn(req, reply);
        if (out !== undefined) return out;
        return reply;
      } catch (err) {
        if (err instanceof NotFoundError) return reply.status(404).send({ error: 'Not Found', message: err.message });
        if (err instanceof ValidationError) return reply.status(400).send({ error: 'Bad Request', message: err.message });
        throw err;
      }
    };

  // Full state — the same shape the Space's getstate action returns.
  app.get('/api/v1/state', wrap(async (req) => {
    const limit = req.query?.activityLimit ? Number(req.query.activityLimit) : 100;
    return service.getState(Number.isFinite(limit) ? limit : 100);
  }));

  // Boards
  app.get('/api/v1/boards', wrap(async () => service.listBoards()));
  app.post('/api/v1/boards', wrap(async (req, reply) => {
    const body = parse(createBoardSchema, req.body);
    const board = service.createBoard(body, body.origin === 'space' ? 'scotty' : 'scotty');
    return reply.status(201).send(board);
  }));
  app.delete('/api/v1/boards/:id', wrap(async (req, reply) => {
    service.deleteBoard(req.params.id);
    return reply.status(204).send();
  }));

  // Items
  app.get('/api/v1/items', wrap(async (req) => {
    const q = req.query ?? {};
    const filter: { boardId?: string | null; column?: any } = {};
    if (q.boardId === 'null') filter.boardId = null;
    else if (typeof q.boardId === 'string') filter.boardId = q.boardId;
    if (typeof q.column === 'string' && (COLUMNS as readonly string[]).includes(q.column)) filter.column = q.column;
    return service.listItems(filter);
  }));
  app.post('/api/v1/items', wrap(async (req, reply) => {
    const body = parse(createItemSchema, req.body);
    const item = service.createItem(body);
    return reply.status(201).send(item);
  }));
  app.get('/api/v1/items/:id', wrap(async (req) => service.getItem(req.params.id)));
  app.patch('/api/v1/items/:id', wrap(async (req) => {
    const body = parse(updateItemSchema, req.body);
    const actor = typeof req.headers['x-board-actor'] === 'string' ? req.headers['x-board-actor'] : 'cooper';
    return service.updateItem(req.params.id, body, actor);
  }));
  app.delete('/api/v1/items/:id', wrap(async (req, reply) => {
    service.deleteItem(req.params.id);
    return reply.status(204).send();
  }));

  // Cooper composite update (status line + optional comment + activity)
  app.post('/api/v1/items/:id/cooper-update', wrap(async (req) => {
    const body = parse(cooperUpdateSchema, req.body);
    return service.cooperUpdate(req.params.id, body);
  }));

  // Comments & subtasks
  app.post('/api/v1/items/:id/comments', wrap(async (req, reply) => {
    const body = parse(commentSchema, req.body);
    const comment = service.addComment(req.params.id, body);
    return reply.status(201).send(comment);
  }));
  app.post('/api/v1/items/:id/subtasks', wrap(async (req, reply) => {
    const body = parse(subtaskCreateSchema, req.body);
    const sub = service.addSubtask(req.params.id, body.title);
    return reply.status(201).send(sub);
  }));
  app.patch('/api/v1/subtasks/:id', wrap(async (req) => {
    const body = parse(subtaskUpdateSchema, req.body);
    return service.updateSubtask(req.params.id, body);
  }));
  app.delete('/api/v1/subtasks/:id', wrap(async (req, reply) => {
    service.deleteSubtask(req.params.id);
    return reply.status(204).send();
  }));

  // Activity
  app.get('/api/v1/activity', wrap(async (req) => {
    const limit = req.query?.limit ? Number(req.query.limit) : 100;
    return service.listActivity(Number.isFinite(limit) ? limit : 100);
  }));

  // ---- Sync (SYNC.md) ----
  // Pull: change log entries after `since`, each with its current snapshot.
  app.get('/api/v1/sync/changes', wrap(async (req) => {
    const since = req.query?.since ? Number(req.query.since) : 0;
    const { changes, cursor } = service.listChanges(Number.isFinite(since) ? since : 0);
    return {
      cursor,
      changes: changes.map((c) => ({ ...c, snapshot: c.op === 'delete' ? null : service.entitySnapshot(c.entity, c.entityId) })),
    };
  }));

  // Push: Space-side entities upserted by spaceId, last-write-wins by updatedAt.
  app.post('/api/v1/sync/push', wrap(async (req) => {
    const body = parse(syncPushSchema, req.body);
    const results: Array<{ spaceId: string; entity: string; applied: boolean; reason?: string; id?: string }> = [];
    for (const ent of body.entities) {
      const data = ent.data as Record<string, any>;
      if (ent.entity === 'board') {
        const existing = service.findBoardBySpaceId(ent.spaceId);
        if (!existing) {
          const board = service.createBoard({ name: String(data.name ?? 'Untitled board'), origin: 'space', spaceId: ent.spaceId }, 'scotty');
          results.push({ spaceId: ent.spaceId, entity: 'board', applied: true, id: board.id });
        } else if (ent.updatedAt > existing.updatedAt) {
          results.push({ spaceId: ent.spaceId, entity: 'board', applied: false, reason: 'name edits not synced in v1', id: existing.id });
        } else {
          results.push({ spaceId: ent.spaceId, entity: 'board', applied: false, reason: 'stale', id: existing.id });
        }
      } else if (ent.entity === 'item') {
        const existing = service.findItemBySpaceId(ent.spaceId);
        if (!existing) {
          let boardId: string | null = null;
          if (data.boardSpaceId) {
            const b = service.findBoardBySpaceId(String(data.boardSpaceId));
            boardId = b ? b.id : null;
          }
          const item = service.createItem(
            {
              title: String(data.title ?? 'Untitled'),
              detail: typeof data.detail === 'string' ? data.detail : '',
              kind: data.kind === 'idea' ? 'idea' : 'task',
              boardId,
              column: (COLUMNS as readonly string[]).includes(data.column) ? data.column : 'inbox',
              priority: data.priority === true,
              assignee: data.assignee === 'scotty' ? 'scotty' : 'cooper',
              createdBy: typeof data.createdBy === 'string' ? data.createdBy : 'scotty',
              origin: 'space',
              spaceId: ent.spaceId,
              trkId: typeof data.trkId === 'string' ? data.trkId : null,
            },
            'scotty'
          );
          results.push({ spaceId: ent.spaceId, entity: 'item', applied: true, id: item.id });
        } else if (ent.updatedAt > existing.updatedAt) {
          const patch: Record<string, unknown> = {};
          for (const key of ['title', 'detail', 'kind', 'column', 'priority', 'assignee', 'checked', 'cooperStatus', 'trkId']) {
            if (data[key] !== undefined) patch[key] = data[key];
          }
          if (data.boardSpaceId !== undefined) {
            const b = data.boardSpaceId ? service.findBoardBySpaceId(String(data.boardSpaceId)) : null;
            patch.boardId = b ? b.id : null;
          }
          service.updateItem(existing.id, patch as any, 'scotty', 'space');
          results.push({ spaceId: ent.spaceId, entity: 'item', applied: true, id: existing.id });
        } else {
          results.push({ spaceId: ent.spaceId, entity: 'item', applied: false, reason: 'stale', id: existing.id });
        }
      } else {
        // comment: append-only, dedupe by spaceId
        const itemSpaceId = String(data.itemSpaceId ?? '');
        const item = itemSpaceId ? service.findItemBySpaceId(itemSpaceId) : null;
        if (!item) {
          results.push({ spaceId: ent.spaceId, entity: 'comment', applied: false, reason: 'parent item not synced yet' });
        } else {
          const dupe = item.comments.find((c) => c.spaceId === ent.spaceId);
          if (dupe) {
            results.push({ spaceId: ent.spaceId, entity: 'comment', applied: false, reason: 'duplicate', id: dupe.id });
          } else {
            const comment = service.addComment(item.id, {
              author: String(data.author ?? 'scotty'),
              body: String(data.body ?? ''),
              origin: 'space',
              spaceId: ent.spaceId,
            });
            results.push({ spaceId: ent.spaceId, entity: 'comment', applied: true, id: comment.id });
          }
        }
      }
    }
    return { results };
  }));
}
