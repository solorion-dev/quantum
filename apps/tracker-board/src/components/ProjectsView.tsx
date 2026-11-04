import { ProgressBar } from '@dsect/ui'
import type { TrackerItem } from '../types'
import { PRIMARY_COLUMNS, isStale, needsTriage, statusLabel } from '../lib/meta'
import { PriorityBadge } from './Badges'

export interface ProjectGroup { id: string; title: string; items: TrackerItem[] }
export function ProjectsView({ groups, onOpen, onFilter }: {
  groups: ProjectGroup[]; onOpen: (id: string) => void; onFilter: (projectId: string) => void
}) {
  if (!groups.length) return <p className="tb-empty">No items match these filters.</p>
  return (
    <div className="tb-projects">
      {groups.map((g) => {
        const live = g.items.filter((i) => i.status !== 'cancelled')
        const done = live.filter((i) => i.status === 'done').length
        const pct = live.length ? Math.round((done / live.length) * 100) : 0
        const hid = `proj-${g.id}`
        return (
          <section key={g.id} className="panel tb-project" aria-labelledby={hid}>
            <div className="panel-head tb-project-head">
              <h2 id={hid} className="tb-project-title">{g.title}</h2>
              <button type="button" className="btn btn-small btn-outline" onClick={() => onFilter(g.id)}>Filter to this project</button>
            </div>
            <div className="panel-body">
              <div className="tb-project-progress">
                <ProgressBar value={pct} label={`${g.title}: ${done} of ${live.length} done`} />
                <span>{done}/{live.length} done · {pct}%</span>
              </div>
              <ul className="tb-project-counts" aria-label="Items by status">
                {PRIMARY_COLUMNS.map((s) => <li key={s}><span>{statusLabel[s]}</span><strong>{g.items.filter((i) => i.status === s).length}</strong></li>)}
                <li><span>Stale</span><strong>{g.items.filter((i) => isStale(i)).length}</strong></li>
                <li><span>Needs triage</span><strong>{g.items.filter(needsTriage).length}</strong></li>
              </ul>
              <ul className="tb-project-items">
                {g.items.slice(0, 8).map((i) => (
                  <li key={i.id}><button type="button" className="tb-linkbtn" onClick={() => onOpen(i.id)}>
                    <span className="tb-id">{i.id}</span> {i.title}</button> <PriorityBadge p={i.priority} /> <span className="tb-muted">{statusLabel[i.status]}</span></li>
                ))}
                {g.items.length > 8 && <li className="tb-muted">+{g.items.length - 8} more</li>}
              </ul>
            </div>
          </section>
        )
      })}
    </div>
  )
}
