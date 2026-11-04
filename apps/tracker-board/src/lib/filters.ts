import type { Priority, Status, TrackerItem } from '../types'
import { isAutomated, isStale, needsTriage, priorityLabel, projectOf, statusLabel } from './meta'

export type A2AMode = 'show' | 'group' | 'hide'
export interface Filters {
  q: string
  status: Status[]
  priority: Priority[]
  assignee: string[] // '__none' = unassigned
  labels: string[]
  project: string[] // '__none' = no project
  flags: ('stale' | 'needs_triage')[]
  a2a: A2AMode
}
export const emptyFilters: Filters = { q: '', status: [], priority: [], assignee: [], labels: [], project: [], flags: [], a2a: 'group' }

export function applyFilters(items: TrackerItem[], f: Filters, byId: Map<string, TrackerItem>): TrackerItem[] {
  const q = f.q.trim().toLowerCase()
  return items.filter((i) => {
    if (f.a2a === 'hide' && isAutomated(i)) return false
    if (q && !`${i.id} ${i.title} ${i.body ?? ''} ${i.labels.join(' ')}`.toLowerCase().includes(q)) return false
    if (f.status.length && !f.status.includes(i.status)) return false
    if (f.priority.length && !f.priority.includes(i.priority)) return false
    if (f.assignee.length && !f.assignee.includes(i.assigneeId ?? '__none')) return false
    if (f.labels.length && !f.labels.some((l) => i.labels.includes(l))) return false
    if (f.project.length && !f.project.includes(projectOf(i, byId)?.id ?? '__none')) return false
    if (f.flags.includes('stale') && !isStale(i)) return false
    if (f.flags.includes('needs_triage') && !needsTriage(i)) return false
    return true
  })
}

export interface Chip { id: string; label: string }
export function chipsFor(f: Filters, names: (k: 'assignee' | 'project', v: string) => string): Chip[] {
  const c: Chip[] = []
  if (f.q) c.push({ id: 'q', label: `Search: “${f.q}”` })
  f.status.forEach((v) => c.push({ id: `status:${v}`, label: `Status: ${statusLabel[v]}` }))
  f.priority.forEach((v) => c.push({ id: `priority:${v}`, label: `Priority: ${priorityLabel[v]}` }))
  f.assignee.forEach((v) => c.push({ id: `assignee:${v}`, label: `Assignee: ${names('assignee', v)}` }))
  f.labels.forEach((v) => c.push({ id: `labels:${v}`, label: `Label: ${v}` }))
  f.project.forEach((v) => c.push({ id: `project:${v}`, label: `Project: ${names('project', v)}` }))
  f.flags.forEach((v) => c.push({ id: `flags:${v}`, label: v === 'stale' ? 'Stale' : 'Needs triage' }))
  return c
}
export function removeChip(f: Filters, id: string): Filters {
  if (id === 'q') return { ...f, q: '' }
  const [k, v] = id.split(':') as [keyof Filters, string]
  return { ...f, [k]: (f[k] as string[]).filter((x) => x !== v) }
}

// Shareable URL state (hash), e.g. #/board?priority=high&a2a=hide
export function toQuery(f: Filters): string {
  const p = new URLSearchParams()
  if (f.q) p.set('q', f.q)
  for (const k of ['status', 'priority', 'assignee', 'labels', 'project', 'flags'] as const) if (f[k].length) p.set(k, f[k].join(','))
  if (f.a2a !== 'group') p.set('a2a', f.a2a)
  return p.toString()
}
export function fromQuery(s: string): Filters {
  const p = new URLSearchParams(s)
  const list = (k: string) => (p.get(k) ? p.get(k)!.split(',').filter(Boolean) : [])
  const a2a = p.get('a2a')
  return {
    q: p.get('q') ?? '', status: list('status') as Status[], priority: list('priority') as Priority[],
    assignee: list('assignee'), labels: list('labels'), project: list('project'),
    flags: list('flags') as Filters['flags'], a2a: a2a === 'show' || a2a === 'hide' ? a2a : 'group',
  }
}
