import type { Kind, Priority, Status, SyncState, TrackerItem } from '../types'

export const STATUSES: Status[] = ['backlog', 'planned', 'in_progress', 'in_review', 'blocked', 'done', 'cancelled']
export const PRIMARY_COLUMNS: Status[] = ['planned', 'in_progress', 'in_review', 'blocked', 'done']
export const COLLAPSED_COLUMNS: Status[] = ['backlog', 'cancelled']
export const PRIORITIES: Priority[] = ['critical', 'high', 'medium', 'low', 'none']
export const KINDS: Kind[] = ['goal', 'issue', 'task', 'decision', 'milestone', 'bug', 'note']

export const statusLabel: Record<Status, string> = {
  backlog: 'Backlog', planned: 'Planned', in_progress: 'In progress', in_review: 'In review',
  blocked: 'Blocked', done: 'Done', cancelled: 'Cancelled',
}
export const priorityLabel: Record<Priority, string> = {
  critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low', none: 'No priority',
}
export const priorityTone = { critical: 'err', high: 'warn', medium: 'info', low: 'slate', none: 'neutral' } as const
export const priorityRank: Record<Priority, number> = { critical: 0, high: 1, medium: 2, low: 3, none: 4 }
export const statusRank = Object.fromEntries(STATUSES.map((s, i) => [s, i])) as Record<Status, number>

export const syncLabel: Record<SyncState, string> = {
  unlinked: 'Not linked', pending: 'Sync pending', synced: 'Synced', suggested: 'Suggestion waiting', error: 'Sync error',
}

/** Read-only server flags (always present from tracker-api and the fixture). */
export const isStale = (i: TrackerItem) => i.stale
export const needsTriage = (i: TrackerItem) => i.needsTriage

/** A2A automated items: OPEN QUESTION for Volt — no flag yet; heuristic on label/title/kind. */
export function isAutomated(i: TrackerItem): boolean {
  return i.labels.some((l) => l === 'a2a' || l === 'automated') || /^A2A\b/i.test(i.title)
}

export function projectOf(i: TrackerItem, byId: Map<string, TrackerItem>): { id: string; title: string } | null {
  if (i.project) return { id: i.project, title: i.project }
  let cur = i
  const seen = new Set<string>()
  while (cur.parentId && byId.has(cur.parentId) && !seen.has(cur.parentId)) {
    seen.add(cur.parentId)
    cur = byId.get(cur.parentId)!
  }
  if (cur === i) return null
  return { id: cur.id, title: cur.title }
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—'
    : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
}
export function isOverdue(i: TrackerItem, now = Date.now()) {
  return !!i.dueAt && i.status !== 'done' && i.status !== 'cancelled' && Date.parse(i.dueAt) < now
}

// Label colours come from the tags table (optional). Rendered as a decorative swatch so text contrast never depends on them.
const labelColors = new Map<string, string>()
export function setLabelColors(labels: { name: string; color?: string | null }[]) {
  labelColors.clear(); for (const l of labels) if (l.color && /^#?[0-9a-f]{3,8}$/i.test(l.color)) labelColors.set(l.name, l.color.startsWith('#') ? l.color : `#${l.color}`)
}
export const labelColor = (name: string) => labelColors.get(name)
