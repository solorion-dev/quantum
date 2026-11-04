import type { TrackerItem } from '../types'
import { isOverdue, isStale, needsTriage } from '../lib/meta'

export function SummaryStrip({ items, onFlag }: { items: TrackerItem[]; onFlag: (f: 'stale' | 'needs_triage' | 'blocked' | 'sync') => void }) {
  const open = items.filter((i) => i.status !== 'done' && i.status !== 'cancelled')
  const stat = [
    { k: 'open', label: 'Open', v: open.length },
    { k: 'in_progress', label: 'In progress', v: items.filter((i) => i.status === 'in_progress').length },
    { k: 'blocked', label: 'Blocked', v: items.filter((i) => i.status === 'blocked').length, act: 'blocked' as const },
    { k: 'overdue', label: 'Overdue', v: open.filter((i) => isOverdue(i)).length },
    { k: 'stale', label: 'Stale', v: items.filter((i) => isStale(i)).length, act: 'stale' as const },
    { k: 'triage', label: 'Needs triage', v: items.filter(needsTriage).length, act: 'needs_triage' as const },
    { k: 'sync', label: 'Sync issues', v: items.filter((i) => i.sync.state === 'error' || i.sync.state === 'suggested').length, act: 'sync' as const },
  ]
  return (
    <section className="tb-summary" aria-label="Summary">
      {stat.map((s) => s.act ? (
        <button key={s.k} type="button" className="metric tb-metric tb-metric--btn" onClick={() => onFlag(s.act!)}
          aria-label={`${s.label}: ${s.v}. Filter to these`}>
          <span className="metric__label">{s.label}</span><span className="metric__value">{s.v}</span>
        </button>
      ) : (
        <div key={s.k} className="metric tb-metric"><span className="metric__label">{s.label}</span><span className="metric__value">{s.v}</span></div>
      ))}
    </section>
  )
}
