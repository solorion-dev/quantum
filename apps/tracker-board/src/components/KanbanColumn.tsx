// Local kanban column built from kit Panel classes. Drop target for pointer drag; keyboard moves live on Board.
import { Children, useState, type ReactNode } from 'react'

const COL_PAGE = 30
import type { Status } from '../types'
import { statusLabel } from '../lib/meta'

export function KanbanColumn({ status, count, children, collapsed, onToggle, onDropItem, automated }: {
  status: Status; count: number; children: ReactNode; collapsed?: boolean; onToggle?: () => void
  onDropItem: (id: string, to: Status) => void; automated?: ReactNode
}) {
  const [over, setOver] = useState(false)
  const [limit, setLimit] = useState(COL_PAGE)
  const all = Children.toArray(children)
  const hidden = all.length - limit
  const head = `tb-col-${status}`
  const drop = {
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setOver(true) },
    onDragLeave: () => setOver(false),
    onDrop: (e: React.DragEvent) => { e.preventDefault(); setOver(false); const id = e.dataTransfer.getData('text/plain'); if (id) onDropItem(id, status) },
  }
  if (collapsed) {
    return (
      <section className={`panel tb-col tb-col--collapsed${over ? ' tb-col--over' : ''}`} aria-labelledby={head} {...drop}>
        <h2 id={head} className="tb-col-head">
          <button type="button" className="tb-col-toggle" aria-expanded="false" onClick={onToggle}>
            <span>{statusLabel[status]}</span><span className="tb-count">{count}</span>
          </button>
        </h2>
      </section>
    )
  }
  return (
    <section className={`panel tb-col tb-col--${status}${over ? ' tb-col--over' : ''}`} aria-labelledby={head} {...drop}>
      <div className="panel-head tb-col-headrow">
        <h2 id={head} className="tb-col-head">
          {onToggle ? (
            <button type="button" className="tb-col-toggle" aria-expanded="true" onClick={onToggle}>
              <span>{statusLabel[status]}</span><span className="tb-count">{count}</span>
            </button>
          ) : (<><span>{statusLabel[status]}</span><span className="tb-count" aria-label={`${count} items`}>{count}</span></>)}
        </h2>
      </div>
      <div className="panel-body tb-col-body">
        {count === 0 ? <p className="tb-empty">Nothing here</p> : <ul className="tb-cards" role="list">{all.slice(0, limit)}</ul>}
        {hidden > 0 && <button type="button" className="btn btn-small ghost tb-more" onClick={() => setLimit((n) => n + COL_PAGE)}>Show {Math.min(COL_PAGE, hidden)} more ({hidden} hidden)</button>}
        {automated}
      </div>
    </section>
  )
}
