import { useMemo, useState } from 'react'
import { LabelChip } from './LabelChip'
import { Table, Th, Td } from '@dsect/ui'
import type { Person, TrackerItem } from '../types'
import { fmtDate, isAutomated, isOverdue, priorityRank, statusLabel, statusRank } from '../lib/meta'
import type { A2AMode } from '../lib/filters'
import { FlagBadges, GitHubBadge, PriorityBadge } from './Badges'

const LIST_PAGE = 100
type Key = 'id' | 'title' | 'status' | 'priority' | 'assignee' | 'dueAt' | 'updatedAt'
export function ListView({ items, people, a2a, onOpen, projectName }: {
  items: TrackerItem[]; people: Map<string, Person>; a2a: A2AMode; onOpen: (id: string) => void
  projectName: (i: TrackerItem) => string
}) {
  const [sort, setSort] = useState<{ key: Key; dir: 'asc' | 'desc' }>({ key: 'priority', dir: 'asc' })
  const [showAuto, setShowAuto] = useState(false)
  const name = (i: TrackerItem) => (i.assigneeId ? people.get(i.assigneeId)?.display ?? i.assigneeId : '')
  const rows = useMemo(() => {
    const cmp: Record<Key, (a: TrackerItem, b: TrackerItem) => number> = {
      id: (a, b) => a.id.localeCompare(b.id), title: (a, b) => a.title.localeCompare(b.title),
      status: (a, b) => statusRank[a.status] - statusRank[b.status], priority: (a, b) => priorityRank[a.priority] - priorityRank[b.priority],
      assignee: (a, b) => (name(a) || '~').localeCompare(name(b) || '~'),
      dueAt: (a, b) => (a.dueAt ?? '9999').localeCompare(b.dueAt ?? '9999'), updatedAt: (a, b) => a.updatedAt.localeCompare(b.updatedAt),
    }
    const s = [...items].sort((a, b) => (sort.dir === 'asc' ? 1 : -1) * cmp[sort.key](a, b) || a.id.localeCompare(b.id))
    return s
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, sort, people])
  const [limit, setLimit] = useState(LIST_PAGE)
  const human = a2a === 'group' ? rows.filter((i) => !isAutomated(i)) : rows
  const auto = a2a === 'group' ? rows.filter(isAutomated) : []
  const th = (key: Key, label: string) => (
    <Th sortable sortDir={sort.key === key ? sort.dir : undefined}
      onSort={() => setSort((s) => ({ key, dir: s.key === key && s.dir === 'asc' ? 'desc' : 'asc' }))}>{label}</Th>
  )
  const row = (i: TrackerItem) => (
    <tr key={i.id} className={isAutomated(i) ? 'tb-row-auto' : undefined}>
      <Td><span className="tb-id">{i.id}</span></Td>
      <Td><button type="button" className="tb-linkbtn" onClick={() => onOpen(i.id)}>{i.title}</button>
        <div className="tb-row-meta">{i.labels.map((l) => <LabelChip key={l} name={l} />)}<FlagBadges item={i} /></div></Td>
      <Td>{statusLabel[i.status]}</Td>
      <Td><PriorityBadge p={i.priority} /></Td>
      <Td>{name(i) || <span className="tb-muted">Unassigned</span>}</Td>
      <Td>{projectName(i)}</Td>
      <Td><span className={isOverdue(i) ? 'tb-due tb-due--over' : undefined}>{fmtDate(i.dueAt)}</span></Td>
      <Td>{i.github ? <GitHubBadge github={i.github} sync={i.sync} /> : <span className="tb-muted">—</span>}</Td>
      <Td>{fmtDate(i.updatedAt)}</Td>
    </tr>
  )
  return (
    <Table title="Items" count={`${items.length}`} size="sm" className="tb-list"
      footer={auto.length > 0 ? (
        <button type="button" className="btn btn-small ghost" aria-expanded={showAuto} onClick={() => setShowAuto((v) => !v)}>
          {showAuto ? 'Hide' : 'Show'} {auto.length} automated (A2A) items
        </button>) : undefined}>
      <thead><tr>
        {th('id', 'ID')}{th('title', 'Title')}{th('status', 'Status')}{th('priority', 'Priority')}{th('assignee', 'Assignee')}
        <Th>Project</Th>{th('dueAt', 'Due')}<Th>GitHub</Th>{th('updatedAt', 'Updated')}
      </tr></thead>
      <tbody>
        {human.slice(0, limit).map(row)}
        {showAuto && auto.map(row)}
        {human.length > limit && <tr><td colSpan={9} className="tb-more-row">
          <span role="status">Showing {limit} of {human.length}</span>{' '}
          <button type="button" className="btn btn-small" onClick={() => setLimit((n) => n + LIST_PAGE)}>Show {Math.min(LIST_PAGE, human.length - limit)} more</button>
        </td></tr>}
        {items.length === 0 && <tr><td colSpan={9}>No items match these filters.</td></tr>}
      </tbody>
    </Table>
  )
}
