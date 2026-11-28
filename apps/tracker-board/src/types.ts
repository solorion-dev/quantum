export type ColumnId =
  | 'review'
  | 'progress'
  | 'blocked'
  | 'planned'
  | 'done'
  | 'backlog'
  | 'cancelled'

// 'none' is a real priority in the tracker backend (an item with no priority
// set). It renders with 0 bars and ranks last — it is NOT folded into 'medium'.
export type Priority = 'critical' | 'high' | 'medium' | 'low' | 'none'

export type Kind = 'task' | 'bug' | 'issue' | 'goal' | 'milestone' | 'decision'

export interface Card {
  id: string
  title: string
  description: string
  kind: Kind
  column: ColumnId
  priority: Priority
  assignee: string | null
  points: number | null
  due: string | null
  project: string
  stale: boolean
  createdAt: number
  updatedAt: number
}

export interface ColumnDef {
  id: ColumnId
  label: string
  defaultCollapsed?: boolean
}

export const COLUMNS: ColumnDef[] = [
  { id: 'review', label: 'In review' },
  { id: 'progress', label: 'In progress' },
  { id: 'blocked', label: 'Blocked' },
  { id: 'planned', label: 'Planned' },
  { id: 'done', label: 'Done · recent' },
  { id: 'backlog', label: 'Backlog', defaultCollapsed: true },
  { id: 'cancelled', label: 'Cancelled', defaultCollapsed: true },
]

export const COLUMN_LABEL: Record<ColumnId, string> = Object.fromEntries(
  COLUMNS.map((c) => [c.id, c.label]),
) as Record<ColumnId, string>

export const PRIORITIES: { id: Priority; label: string; bars: number }[] = [
  { id: 'critical', label: 'Critical', bars: 4 },
  { id: 'high', label: 'High', bars: 3 },
  { id: 'medium', label: 'Medium', bars: 2 },
  { id: 'low', label: 'Low', bars: 1 },
  { id: 'none', label: 'None', bars: 0 },
]

export const KINDS: Kind[] = ['task', 'bug', 'issue', 'goal', 'milestone', 'decision']

export const POINT_OPTIONS = [1, 2, 3, 5, 8, 13]
