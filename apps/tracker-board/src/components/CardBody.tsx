import { Tooltip } from './Tooltip'
import { cn } from '../lib/cn'
import { dueInfo, initials } from '../lib/format'
import { KINDS, PRIORITIES } from '../types'
import type { Card, Priority } from '../types'

export function PriorityGlyph({ priority, className }: { priority: Priority; className?: string }) {
  const bars = PRIORITIES.find((p) => p.id === priority)?.bars ?? 1
  return (
    <span className={cn('inline-flex h-[11px] items-end gap-[2px]', className)} aria-hidden>
      {[0, 1, 2, 3].map((i) => (
        <span
          key={i}
          className={cn('w-[3px] rounded-[1px] transition-colors', i < bars ? 'bg-fg' : 'bg-line-strong')}
          style={{ height: 4 + i * 2.4 }}
        />
      ))}
    </span>
  )
}

export function priorityLabel(p: Priority) {
  return PRIORITIES.find((x) => x.id === p)?.label ?? p
}

export function kindLabel(k: string) {
  return (KINDS as string[]).includes(k) ? k : 'task'
}

interface Props {
  card: Card
  ghost?: boolean
  onCopyId?: (id: string) => void
}

export function CardBody({ card, ghost, onCopyId }: Props) {
  const due = dueInfo(card)
  const critical = card.priority === 'critical'
  return (
    <div
      className={cn(
        'card-surface relative rounded-xl border bg-surface px-3.5 pb-3 pt-2.5 text-left',
        ghost
          ? 'border-fg/50 shadow-[0_24px_48px_-12px_rgba(0,0,0,0.35)]'
          : 'border-line transition-[border-color,box-shadow,background-color] duration-150 hover:border-line-strong hover:shadow-[0_2px_12px_-4px_rgba(0,0,0,0.12)]',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <Tooltip label="Copy ID" side="top">
          <button
            data-nodrag
            tabIndex={-1}
            onClick={(e) => {
              e.stopPropagation()
              onCopyId?.(card.id)
            }}
            className="-mx-1 cursor-pointer rounded px-1 font-mono text-[11px] tracking-tight text-fg-muted transition-colors hover:bg-subtle hover:text-fg"
          >
            {card.id}
          </button>
        </Tooltip>
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-fg-faint">
          {kindLabel(card.kind)}
        </span>
      </div>

      <p className="mt-1 line-clamp-4 text-[13.5px] font-medium leading-[1.35] tracking-[-0.005em] text-fg">
        {card.title || <span className="text-fg-faint">Untitled</span>}
      </p>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[11.5px] text-fg-muted">
        <Tooltip label={`Priority: ${priorityLabel(card.priority)}`}>
          <span className="inline-flex items-center gap-1.5">
            <PriorityGlyph priority={card.priority} />
            <span className={cn(critical && 'font-semibold text-fg')}>{card.priority}</span>
          </span>
        </Tooltip>

        {card.points != null && (
          <Tooltip label={`${card.points} story point${card.points === 1 ? '' : 's'}`}>
            <span className="font-mono text-[11px]">{card.points} pts</span>
          </Tooltip>
        )}

        {card.assignee && (
          <Tooltip label={`Assigned to ${card.assignee}`}>
            <span className="inline-flex items-center gap-1.5">
              <span className="flex h-4 w-4 items-center justify-center rounded-full border border-line-strong text-[9px] font-semibold text-fg">
                {initials(card.assignee)}
              </span>
              {card.assignee}
            </span>
          </Tooltip>
        )}

        {card.stale && (
          <Tooltip label="No activity for a while">
            <span className="rounded-full border border-dashed border-fg-faint px-1.5 text-[10px] font-medium uppercase tracking-wider text-fg-muted">
              stale
            </span>
          </Tooltip>
        )}

        {due && (
          <Tooltip label={due.tip} className="ml-auto inline-flex">
            <span
              className={cn(
                'rounded-md px-1.5 py-px font-mono text-[10.5px]',
                due.overdue ? 'bg-fg font-semibold text-bg' : due.soon ? 'border border-fg text-fg' : 'text-fg-muted',
              )}
            >
              {due.overdue ? '! ' : ''}
              {due.label}
            </span>
          </Tooltip>
        )}
      </div>
    </div>
  )
}
