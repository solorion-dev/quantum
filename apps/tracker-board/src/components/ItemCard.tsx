import { Avatar } from '@dsect/ui'
import { LabelChip } from './LabelChip'
import type { Person, TrackerItem } from '../types'
import { fmtDate, isOverdue } from '../lib/meta'
import { FlagBadges, GitHubBadge, PriorityBadge } from './Badges'

export function ItemCard({ item, person, onOpen, col, idx }: {
  item: TrackerItem; person?: Person; onOpen: (id: string) => void; col: number; idx: number
}) {
  const overdue = isOverdue(item)
  return (
    <li className="tb-card-li">
      <button type="button" className="card tb-card" data-col={col} data-idx={idx} data-id={item.id}
        draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', item.id)}
        onClick={() => onOpen(item.id)}
        aria-describedby="tb-board-help">
        <span className="tb-card-top">
          <span className="tb-id">{item.id}</span>
          <span className="tb-kind">{item.kind}</span>
          <PriorityBadge p={item.priority} />
        </span>
        <span className="tb-card-title">{item.title}</span>
        <span className="tb-card-meta">
          {item.labels.map((l) => <LabelChip key={l} name={l} />)}
          <FlagBadges item={item} />
        </span>
        <span className="tb-card-foot">
          <span className="tb-assignee">
            {person ? <><Avatar name={person.display} size="sm" /><span>{person.display}</span></> : <span className="tb-muted">Unassigned</span>}
          </span>
          {item.dueAt && <span className={overdue ? 'tb-due tb-due--over' : 'tb-due'}>{overdue ? 'Overdue ' : 'Due '}{fmtDate(item.dueAt)}</span>}
          <GitHubBadge github={item.github} sync={item.sync} compact />
        </span>
      </button>
    </li>
  )
}
