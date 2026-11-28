import type { Card, ColumnId, Kind, Priority } from '../types'
import { KINDS } from '../types'

// ---------------------------------------------------------------------------
// Tracker backend contract (board_server.py on Tritium, port 7654):
//
//   Board list — there is NO list endpoint. The board loads from
//   /board-data.json, a snapshot of the live Tracker DB produced by
//   scripts/snapshot-board.py: { generated_at, items[], projects[] }.
//
//   Detail — GET /api/item/<id> -> { item, comments, history }
//   Edit   — POST /api/item/<id>/update -> { ok, item }
//            JSON body with a strict whitelist: title, body, status,
//            priority, assignee, due_at, points. There is NO create, NO
//            delete and NO PUT on this backend.
//
// /api is proxied to the service by vite (see vite.config.ts, TRACKER_API).
// ---------------------------------------------------------------------------

export type SyncStatus = 'syncing' | 'live' | 'offline'

export const STATUS_TO_COLUMN: Record<string, ColumnId> = {
  backlog: 'backlog',
  planned: 'planned',
  in_progress: 'progress',
  in_review: 'review',
  blocked: 'blocked',
  done: 'done',
  cancelled: 'cancelled',
}

export const COLUMN_TO_STATUS: Record<ColumnId, string> = {
  review: 'in_review',
  progress: 'in_progress',
  blocked: 'blocked',
  planned: 'planned',
  done: 'done',
  backlog: 'backlog',
  cancelled: 'cancelled',
}

const KNOWN_PRIORITIES = new Set<string>(['critical', 'high', 'medium', 'low', 'none'])
export const PRIORITY_RANK: Record<Priority, number> = { critical: 0, high: 1, medium: 2, low: 3, none: 4 }

// The backend has no stale flag; Arena's design has a stale chip. It is
// derived here, honestly: an open item untouched for 21+ days is stale.
const STALE_MS = 21 * 24 * 3600 * 1000

export const isStale = (column: ColumnId, updatedAt: number) =>
  column !== 'done' && column !== 'cancelled' && Date.now() - updatedAt > STALE_MS

// --- snapshot ---------------------------------------------------------------

interface SnapshotItem {
  id: string
  kind: string
  title: string
  status: string
  priority: string
  assignee: string
  due_at: string | null
  points: number | null
  updated_at: string
}

interface SnapshotProject {
  id: string
  title: string
  slug: string
  member_ids: string[]
}

export interface Snapshot {
  cards: Card[]
  generatedAt: string
  projects: string[]
}

const parseTs = (iso: string | null | undefined): number => {
  const t = iso ? Date.parse(iso) : NaN
  return Number.isNaN(t) ? Date.now() : t
}

function adapt(item: SnapshotItem, projectOf: Map<string, string>): Card {
  const column = STATUS_TO_COLUMN[item.status] ?? 'planned'
  const updatedAt = parseTs(item.updated_at)
  return {
    id: item.id,
    title: item.title ?? '',
    // Snapshot rows carry no body; the drawer loads it via GET /api/item/<id>.
    description: '',
    kind: (KINDS as string[]).includes(item.kind) ? (item.kind as Kind) : 'task',
    column,
    priority: (KNOWN_PRIORITIES.has(item.priority) ? item.priority : 'none') as Priority,
    assignee: item.assignee ? item.assignee : null,
    points: typeof item.points === 'number' ? item.points : null,
    due: item.due_at ? String(item.due_at).slice(0, 10) : null,
    // Project hub membership comes from projects[] in the snapshot.
    project: projectOf.get(item.id) ?? 'General',
    stale: isStale(column, updatedAt),
    // The snapshot has no created_at column; the drawer's detail fetch
    // supplies the real one. updatedAt is exact.
    createdAt: updatedAt,
    updatedAt,
  }
}

export async function loadSnapshot(): Promise<Snapshot> {
  const res = await fetch(`/board-data.json?t=${Date.now()}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`Snapshot request failed (${res.status})`)
  const data = (await res.json()) as { generated_at: string; items: SnapshotItem[]; projects: SnapshotProject[] }

  const projectOf = new Map<string, string>()
  for (const p of data.projects ?? []) {
    for (const id of p.member_ids ?? []) {
      if (!projectOf.has(id)) projectOf.set(id, p.title)
    }
  }

  const cards = (data.items ?? []).map((i) => adapt(i, projectOf))
  // Column order matches the stopgap board: priority (critical first, none
  // last), then most recently updated. Drag order is local-only afterwards —
  // the backend persists no position.
  cards.sort((a, b) =>
    a.column === b.column ? PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || b.updatedAt - a.updatedAt : 0,
  )
  return { cards, generatedAt: data.generated_at, projects: (data.projects ?? []).map((p) => p.title) }
}

// --- item detail --------------------------------------------------------------

export interface ItemEvent {
  ts: string
  actor: string
  kind: string
  text: string
}

export interface ItemDetail {
  item: Record<string, unknown>
  comments: ItemEvent[]
  history: ItemEvent[]
}

export async function fetchItemDetail(id: string): Promise<ItemDetail> {
  const res = await fetch(`/api/item/${encodeURIComponent(id)}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`Server responded ${res.status}`)
  const data = (await res.json()) as Partial<ItemDetail>
  return { item: data.item ?? {}, comments: data.comments ?? [], history: data.history ?? [] }
}

// --- edits --------------------------------------------------------------------

/** The POST /update whitelist, in backend field names. */
export interface ItemUpdate {
  title?: string
  body?: string
  status?: string
  priority?: string
  assignee?: string
  due_at?: string
  points?: number | null
}

/**
 * Map a Card patch onto the backend whitelist. Fields the backend cannot
 * store (kind, project, stale) are dropped — the UI shows them read-only.
 * Note the backend's due_at must be a string: null clears via ''.
 */
export function patchToUpdate(patch: Partial<Card>): ItemUpdate {
  const u: ItemUpdate = {}
  if (patch.title !== undefined) u.title = patch.title
  if (patch.description !== undefined) u.body = patch.description
  if (patch.column !== undefined) u.status = COLUMN_TO_STATUS[patch.column]
  if (patch.priority !== undefined) u.priority = patch.priority
  if (patch.assignee !== undefined) u.assignee = patch.assignee ?? ''
  if (patch.due !== undefined) u.due_at = patch.due ?? ''
  if (patch.points !== undefined) u.points = patch.points
  return u
}

/** The backend fields a Card patch would change, for undo diffs. */
export function backendFieldsOf(card: Card): ItemUpdate {
  return {
    title: card.title,
    body: card.description,
    status: COLUMN_TO_STATUS[card.column],
    priority: card.priority,
    assignee: card.assignee ?? '',
    due_at: card.due ?? '',
    points: card.points,
  }
}

export async function updateItem(id: string, fields: ItemUpdate): Promise<Record<string, unknown>> {
  const res = await fetch(`/api/item/${encodeURIComponent(id)}/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
  const data = (await res.json().catch(() => null)) as { ok?: boolean; item?: Record<string, unknown>; error?: string } | null
  if (!res.ok || !data?.ok) throw new Error(data?.error ?? `Server responded ${res.status}`)
  return data.item ?? {}
}
