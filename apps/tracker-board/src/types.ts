// Volt's canonical item model — docs/tracker-overhaul/tracker-overhaul-design-20261104.md §6.
// `stale` / `needsTriage` are read-only server flags Volt is adding (answer 3, 2026-11-04).

export type Status = 'backlog' | 'planned' | 'in_progress' | 'in_review' | 'blocked' | 'done' | 'cancelled'
export type Priority = 'critical' | 'high' | 'medium' | 'low' | 'none'
export type Kind = 'goal' | 'issue' | 'task' | 'decision' | 'milestone' | 'bug' | 'note'
export type SyncState = 'unlinked' | 'pending' | 'synced' | 'suggested' | 'error'

export interface GitHubLink {
  repo: string
  number: number
  type: 'issue' | 'pull_request'
  projectItemId?: string | null
  url: string
  etag?: string | null
  remoteUpdatedAt?: string | null
}

export interface SyncInfo {
  state: SyncState
  lastSyncedAt?: string | null
  pendingSuggestionId?: string | null
  error?: string | null
}

export interface TrackerItem {
  id: string
  kind: Kind
  title: string
  body?: string
  status: Status
  priority: Priority
  assigneeId: string | null
  labels: string[]
  parentId: string | null
  dueAt: string | null
  points: number | null
  createdAt: string
  updatedAt: string
  github: GitHubLink | null
  sync: SyncInfo
  /** Server flag: no update in 14 days and not done/cancelled. Read-only. */
  stale: boolean
  /** Server flag: no assignee, or priority none, or backlog with no labels. Read-only. */
  needsTriage: boolean
  /** Volt API: `{ id, title, derived }` (derived = root-ancestor fallback computed server-side); string tolerated. */
  project?: { id: string; title?: string | null; derived?: boolean } | string | null
  /** Coming from Volt: explicit A2A/automated flag. Until then UI guesses from labels/title. */
  automated?: boolean | null
}

// Shapes below match apps/tracker-api @ 946dcb8 (GET /api/items/:id).
export interface Comment { id: number | string; actor: string | null; body: string; at: string }
export interface StatusChange { fromStatus: Status | null; toStatus: Status; actor: string | null; source: string | null; at: string }
export interface ChangeEvent { actor: string | null; body: string; at: string }
export interface Relation { rel: string; itemId: string; direction: 'out' | 'in' }
export interface ExternalLink { kind: string; target: string; label: string | null }

/** GET /api/items/:id — item + comments, history, relations, links, githubLink in one payload. */
export interface ItemDetail {
  item: TrackerItem
  comments: Comment[]
  statusHistory: StatusChange[]
  changes: ChangeEvent[]
  relations: Relation[]
  links: ExternalLink[]
  githubLink: GitHubLink | null
}

export interface Person { id: string; display: string; kind?: 'human' | 'agent' | string; githubLogin?: string | null; active?: boolean }
export interface Label { name: string; color?: string }

export interface Suggestion {
  id: string
  itemId: string
  field: string
  currentValue: unknown
  proposedValue: unknown
  remoteActor: string | null
  reason: string | null
  state: 'pending' | 'accepted' | 'rejected'
  createdAt: string
}
