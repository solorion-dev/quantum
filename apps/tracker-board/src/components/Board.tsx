import { useRef, useState, type KeyboardEvent } from 'react'
import type { Person, Status, TrackerItem } from '../types'
import { COLLAPSED_COLUMNS, PRIMARY_COLUMNS, isAutomated, priorityRank, statusLabel } from '../lib/meta'
import type { A2AMode } from '../lib/filters'
import { ItemCard } from './ItemCard'
import { KanbanColumn } from './KanbanColumn'

export function Board({ items, people, a2a, onOpen, onMove, onAdd }: { onAdd?: (s: Status) => void;
  items: TrackerItem[]; people: Map<string, Person>; a2a: A2AMode
  onOpen: (id: string) => void; onMove: (id: string, to: Status) => void
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [openA2A, setOpenA2A] = useState<Record<string, boolean>>({})
  const root = useRef<HTMLDivElement>(null)
  const order: Status[] = ['backlog', ...PRIMARY_COLUMNS, 'cancelled']
  const sorted = (s: Status) => items.filter((i) => i.status === s).sort((a, b) => priorityRank[a.priority] - priorityRank[b.priority] || b.updatedAt.localeCompare(a.updatedAt))

  const focusCard = (col: number, idx: number) => {
    const cards = [...(root.current?.querySelectorAll<HTMLButtonElement>(`.tb-card[data-col="${col}"]`) ?? [])]
    if (!cards.length) return false
    cards[Math.max(0, Math.min(idx, cards.length - 1))].focus()
    return true
  }
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const t = e.target as HTMLElement
    if (!t.classList.contains('tb-card')) return
    const col = Number(t.dataset.col), idx = Number(t.dataset.idx), id = t.dataset.id!
    if (e.shiftKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
      e.preventDefault()
      const next = order[col + (e.key === 'ArrowLeft' ? -1 : 1)]
      if (next) { onMove(id, next); requestAnimationFrame(() => root.current?.querySelector<HTMLElement>(`.tb-card[data-id="${id}"]`)?.focus()) }
      return
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); focusCard(col, idx + (e.key === 'ArrowDown' ? 1 : -1)) }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault()
      const step = e.key === 'ArrowLeft' ? -1 : 1
      for (let c = col + step; c >= 0 && c < order.length; c += step) if (focusCard(c, idx)) break
    }
  }

  return (
    <div className="tb-board-wrap">
      <p id="tb-board-help" className="sr-only">Arrow keys move between cards. Shift plus Left or Right arrow moves the card to the previous or next column. Enter opens details.</p>
      <div className="tb-board" ref={root} onKeyDown={onKey}>
        {order.map((s, col) => {
          const all = sorted(s)
          const isSide = COLLAPSED_COLUMNS.includes(s)
          const collapsed = isSide && !expanded[s]
          const auto = a2a === 'group' ? all.filter(isAutomated) : []
          const human = a2a === 'group' ? all.filter((i) => !isAutomated(i)) : all
          const shown = openA2A[s] ? [...human, ...auto] : human
          return (
            <KanbanColumn key={s} status={s} count={all.length} collapsed={collapsed}
              onToggle={isSide ? () => setExpanded((x) => ({ ...x, [s]: !x[s] })) : undefined}
              onDropItem={onMove} onAdd={onAdd ? () => onAdd(s) : undefined}
              automated={auto.length > 0 && (
                <button type="button" className="btn btn-small ghost tb-a2a-toggle" aria-expanded={!!openA2A[s]}
                  onClick={() => setOpenA2A((x) => ({ ...x, [s]: !x[s] }))}>
                  {openA2A[s] ? 'Hide' : 'Show'} {auto.length} automated (A2A) in {statusLabel[s]}
                </button>
              )}>
              {shown.map((i, idx) => (
                <ItemCard key={i.id} item={i} person={i.assigneeId ? people.get(i.assigneeId) : undefined} onOpen={onOpen} col={col} idx={idx} />
              ))}
            </KanbanColumn>
          )
        })}
      </div>
    </div>
  )
}
