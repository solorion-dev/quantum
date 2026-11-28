import { motion } from 'framer-motion'
import { PriorityGlyph, kindLabel, priorityLabel } from './CardBody'
import { Tooltip } from './Tooltip'
import { cn } from '../lib/cn'
import { dueInfo } from '../lib/format'
import { COLUMNS } from '../types'
import type { Card, ColumnId } from '../types'

interface Props {
  cards: Card[]
  selectedId: string | null
  onOpen: (card: Card) => void
  onCardMenu: (e: React.MouseEvent, card: Card) => void
  onColumnMenu: (e: React.MouseEvent, col: ColumnId) => void
  onBoardMenu: (e: React.MouseEvent) => void
}

export function ListView({ cards, selectedId, onOpen, onCardMenu, onColumnMenu, onBoardMenu }: Props) {
  return (
    <div
      className="thin-scroll h-full overflow-y-auto px-4 pb-16 sm:px-6"
      onContextMenu={(e) => {
        e.preventDefault()
        if (!(e.target as HTMLElement).closest('[data-row],[data-group]')) onBoardMenu(e)
      }}
    >
      <div className="mx-auto max-w-5xl">
        {COLUMNS.map((col) => {
          const rows = cards.filter((c) => c.column === col.id)
          if (!rows.length) return null
          return (
            <section key={col.id} className="mb-6">
              <div
                data-group
                onContextMenu={(e) => {
                  e.preventDefault()
                  onColumnMenu(e, col.id)
                }}
                className="sticky top-0 z-10 flex items-center gap-2 bg-bg/90 py-2 backdrop-blur"
              >
                <span className="text-[11px] font-semibold uppercase tracking-[0.14em]">{col.label}</span>
                <span className="rounded-full border border-line-strong px-1.5 font-mono text-[10.5px] leading-[18px] text-fg-muted">
                  {rows.length}
                </span>
              </div>
              <div className="overflow-hidden rounded-xl border border-line">
                {rows.map((c, i) => {
                  const due = dueInfo(c)
                  return (
                    <motion.div
                      key={c.id}
                      data-row
                      layout="position"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.18, delay: Math.min(i, 8) * 0.015 }}
                      role="button"
                      tabIndex={0}
                      onClick={() => onOpen(c)}
                      onKeyDown={(e) => e.key === 'Enter' && onOpen(c)}
                      onContextMenu={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        onCardMenu(e, c)
                      }}
                      className={cn(
                        'grid cursor-pointer grid-cols-[72px_1fr_auto] items-center gap-3 px-3.5 py-2.5 text-[13px] outline-none transition-colors hover:bg-muted focus-visible:bg-muted sm:grid-cols-[80px_1fr_110px_96px_84px]',
                        i > 0 && 'border-t border-line',
                        selectedId === c.id && 'bg-muted',
                      )}
                    >
                      <span className="font-mono text-[11px] text-fg-muted">{c.id}</span>
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{c.title || 'Untitled'}</span>
                        <span className="text-[11px] uppercase tracking-wider text-fg-faint">
                          {kindLabel(c.kind)} · {c.project}
                        </span>
                      </span>
                      <Tooltip label={`Priority: ${priorityLabel(c.priority)}`} className="hidden sm:inline-flex">
                        <span className="flex items-center gap-2 text-fg-muted">
                          <PriorityGlyph priority={c.priority} />
                          {c.priority}
                        </span>
                      </Tooltip>
                      <span className="hidden text-fg-muted sm:block">{c.assignee ?? '—'}</span>
                      <span className="text-right font-mono text-[11px]">
                        {due ? (
                          <Tooltip label={due.tip} className="inline-flex">
                            <span className={cn('rounded px-1.5 py-px', due.overdue ? 'bg-fg font-semibold text-bg' : 'text-fg-muted')}>
                              {due.label}
                            </span>
                          </Tooltip>
                        ) : (
                          <span className="text-fg-faint">—</span>
                        )}
                      </span>
                    </motion.div>
                  )
                })}
              </div>
            </section>
          )
        })}
        {cards.length === 0 && (
          <div className="mt-20 text-center text-sm text-fg-muted">No cards match your filters.</div>
        )}
      </div>
    </div>
  )
}
