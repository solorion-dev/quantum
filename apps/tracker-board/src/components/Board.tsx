import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import { CardBody } from './CardBody'
import { Tooltip } from './Tooltip'
import { cn } from '../lib/cn'
import { COLUMNS } from '../types'
import type { Card, ColumnDef, ColumnId } from '../types'

interface Target {
  col: ColumnId
  beforeId: string | null
}

interface DragState {
  card: Card
  x: number
  y: number
  dx: number
  dy: number
  w: number
  h: number
  drop?: { x: number; y: number }
}

interface Pending {
  card: Card
  sx: number
  sy: number
  pointerType: string
  active: boolean
  timer: number
  dx: number
  dy: number
  w: number
  h: number
}

interface BoardProps {
  cards: Card[]
  allCounts: Record<ColumnId, number>
  filtering: boolean
  collapsed: Record<ColumnId, boolean>
  onToggle: (col: ColumnId) => void
  onOpen: (card: Card) => void
  onMove: (id: string, col: ColumnId, beforeId: string | null) => void
  onCardMenu: (e: React.MouseEvent, card: Card) => void
  onColumnMenu: (e: React.MouseEvent, col: ColumnId) => void
  onBoardMenu: (e: React.MouseEvent) => void
  onCopyId: (id: string) => void
  selectedId: string | null
}

const PAGE = 40

export function Board(props: BoardProps) {
  const { cards, collapsed } = props
  const propsRef = useRef(props)
  useEffect(() => {
    propsRef.current = props
  })

  const boardRef = useRef<HTMLDivElement>(null)
  const pending = useRef<Pending | null>(null)
  const pointer = useRef({ x: 0, y: 0 })
  const targetRef = useRef<Target | null>(null)
  const dropInfo = useRef<{ card: Card; t: Target } | null>(null)
  const droppedId = useRef<string | null>(null)
  const raf = useRef(0)
  const [drag, setDrag] = useState<DragState | null>(null)
  const [target, setTarget] = useState<Target | null>(null)
  const [limits, setLimits] = useState<Partial<Record<ColumnId, number>>>({})

  const dragId = drag?.card.id ?? null
  const dragIdRef = useRef<string | null>(null)
  useEffect(() => {
    dragIdRef.current = dragId
  }, [dragId])

  const findColEl = (x: number, y: number): HTMLElement | undefined =>
    document.elementsFromPoint(x, y).find((el): el is HTMLElement => el instanceof HTMLElement && !!el.dataset.col)

  const updateTarget = useCallback(() => {
    const { x, y } = pointer.current
    const colEl = findColEl(x, y)
    if (!colEl) return
    const col = colEl.dataset.col as ColumnId
    let beforeId: string | null = null
    const list = colEl.querySelector<HTMLElement>('[data-list]')
    if (list && colEl.dataset.collapsed !== '1') {
      const ph = list.querySelector<HTMLElement>('[data-placeholder]')
      const items = Array.from(list.querySelectorAll<HTMLElement>('[data-card-id]'))
      const yy = y - list.getBoundingClientRect().top + list.scrollTop
      for (const it of items) {
        const id = it.dataset.cardId
        if (id === dragIdRef.current) continue
        let top = it.offsetTop
        if (ph && ph.compareDocumentPosition(it) & Node.DOCUMENT_POSITION_FOLLOWING) top -= ph.offsetHeight
        if (yy < top + it.offsetHeight / 2) {
          beforeId = id ?? null
          break
        }
      }
    }
    const prev = targetRef.current
    if (!prev || prev.col !== col || prev.beforeId !== beforeId) {
      const next = { col, beforeId }
      targetRef.current = next
      setTarget(next)
    }
  }, [])

  const endDrag = useCallback(() => {
    cancelAnimationFrame(raf.current)
    delete document.body.dataset.dragging
    targetRef.current = null
    dropInfo.current = null
    setDrag(null)
    setTarget(null)
  }, [])

  const commitDrop = useCallback(() => {
    const info = dropInfo.current
    if (!info) return
    dropInfo.current = null
    droppedId.current = info.card.id
    propsRef.current.onMove(info.card.id, info.t.col, info.t.beforeId)
    endDrag()
  }, [endDrag])

  const loop = useCallback(() => {
    const p = pending.current
    if (!p?.active) return
    const { x, y } = pointer.current
    const b = boardRef.current
    if (b) {
      const r = b.getBoundingClientRect()
      const edge = 72
      if (x < r.left + edge) b.scrollLeft -= 6 + ((r.left + edge - x) / edge) * 16
      else if (x > r.right - edge) b.scrollLeft += 6 + ((x - (r.right - edge)) / edge) * 16
    }
    const colEl = findColEl(x, y)
    const list = colEl?.querySelector<HTMLElement>('[data-list]')
    if (list) {
      const r = list.getBoundingClientRect()
      if (y < r.top + 64) list.scrollTop -= 6 + ((r.top + 64 - y) / 64) * 12
      else if (y > r.bottom - 64) list.scrollTop += 6 + ((y - (r.bottom - 64)) / 64) * 12
    }
    updateTarget()
    raf.current = requestAnimationFrame(loop)
  }, [updateTarget])

  const preventTouch = useCallback((e: TouchEvent) => {
    if (pending.current?.active && e.cancelable) e.preventDefault()
  }, [])

  const activate = useCallback(() => {
    const p = pending.current
    if (!p || p.active) return
    p.active = true
    window.clearTimeout(p.timer)
    document.body.dataset.dragging = '1'
    window.getSelection()?.removeAllRanges()
    targetRef.current = null
    setDrag({ card: p.card, x: pointer.current.x, y: pointer.current.y, dx: p.dx, dy: p.dy, w: p.w, h: p.h })
    dragIdRef.current = p.card.id
    updateTarget()
    if (p.pointerType !== 'mouse') navigator.vibrate?.(8)
    raf.current = requestAnimationFrame(loop)
  }, [loop, updateTarget])

  useEffect(() => {
    const onMoveEv = (e: PointerEvent) => {
      const p = pending.current
      if (!p) return
      pointer.current = { x: e.clientX, y: e.clientY }
      const dist = Math.hypot(e.clientX - p.sx, e.clientY - p.sy)
      if (!p.active) {
        if (p.pointerType === 'mouse') {
          if (dist > 5) activate()
        } else if (dist > 9) {
          window.clearTimeout(p.timer)
          pending.current = null
        }
        return
      }
      setDrag((d) => (d && !d.drop ? { ...d, x: e.clientX, y: e.clientY } : d))
    }
    const onUpEv = () => {
      const p = pending.current
      if (!p) return
      window.clearTimeout(p.timer)
      pending.current = null
      if (!p.active) {
        propsRef.current.onOpen(p.card)
        return
      }
      cancelAnimationFrame(raf.current)
      const t = targetRef.current
      const ph = document.querySelector<HTMLElement>('[data-placeholder]')
      if (!t || !ph) {
        endDrag()
        return
      }
      const r = ph.getBoundingClientRect()
      dropInfo.current = { card: p.card, t }
      setDrag((d) => (d ? { ...d, drop: { x: r.left, y: r.top } } : d))
      window.setTimeout(commitDrop, 420)
    }
    const onCancelEv = () => {
      const p = pending.current
      if (!p) return
      window.clearTimeout(p.timer)
      pending.current = null
      if (p.active) endDrag()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && pending.current?.active) {
        e.stopPropagation()
        onCancelEv()
      }
    }
    window.addEventListener('pointermove', onMoveEv)
    window.addEventListener('pointerup', onUpEv)
    window.addEventListener('pointercancel', onCancelEv)
    window.addEventListener('keydown', onKey, true)
    window.addEventListener('touchmove', preventTouch, { passive: false })
    return () => {
      window.removeEventListener('pointermove', onMoveEv)
      window.removeEventListener('pointerup', onUpEv)
      window.removeEventListener('pointercancel', onCancelEv)
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener('touchmove', preventTouch)
    }
  }, [activate, commitDrop, endDrag, preventTouch])

  const startPointer = (e: React.PointerEvent<HTMLElement>, card: Card) => {
    if (e.button !== 0) return
    window.clearTimeout(pending.current?.timer)
    if ((e.target as HTMLElement).closest('[data-nodrag]')) return
    const r = e.currentTarget.getBoundingClientRect()
    pointer.current = { x: e.clientX, y: e.clientY }
    const p: Pending = {
      card,
      sx: e.clientX,
      sy: e.clientY,
      pointerType: e.pointerType,
      active: false,
      timer: 0,
      dx: e.clientX - r.left,
      dy: e.clientY - r.top,
      w: r.width,
      h: r.height,
    }
    pending.current = p
    if (e.pointerType !== 'mouse') p.timer = window.setTimeout(activate, 260)
  }

  const boardContext = (e: React.MouseEvent) => {
    e.preventDefault()
    if (drag) return
    const el = e.target as HTMLElement
    if (el.closest('[data-card-id]') || el.closest('[data-col-header]')) return
    props.onBoardMenu(e)
  }

  return (
    <>
      <div
        ref={boardRef}
        onContextMenu={boardContext}
        className="thin-scroll flex h-full gap-3 overflow-x-auto overflow-y-hidden px-4 pb-4 pt-1 sm:px-6 max-sm:snap-x max-sm:snap-mandatory"
      >
        {COLUMNS.map((col) => {
          const colCards = cards.filter((c) => c.column === col.id)
          const isCollapsed = collapsed[col.id]
          return isCollapsed ? (
            <CollapsedColumn
              key={col.id}
              col={col}
              count={colCards.length}
              total={props.allCounts[col.id]}
              filtering={props.filtering}
              active={!!drag && target?.col === col.id}
              onToggle={() => props.onToggle(col.id)}
              onContextMenu={(e) => {
                e.preventDefault()
                if (!drag) props.onColumnMenu(e, col.id)
              }}
            />
          ) : (
            <Column
              key={col.id}
              col={col}
              cards={colCards}
              total={props.allCounts[col.id]}
              filtering={props.filtering}
              limit={limits[col.id] ?? PAGE}
              onMore={() => setLimits((l) => ({ ...l, [col.id]: (l[col.id] ?? PAGE) + PAGE }))}
              drag={drag}
              target={target}
              droppedId={droppedId}
              selectedId={props.selectedId}
              startPointer={startPointer}
              onToggle={() => props.onToggle(col.id)}
              onCopyId={props.onCopyId}
              onKeyOpen={props.onOpen}
              onCardMenu={(e, card) => {
                e.preventDefault()
                e.stopPropagation()
                if (!drag) props.onCardMenu(e, card)
              }}
              onColumnMenu={(e) => {
                e.preventDefault()
                e.stopPropagation()
                if (!drag) props.onColumnMenu(e, col.id)
              }}
            />
          )
        })}
      </div>

      {drag &&
        createPortal(
          <motion.div
            className="pointer-events-none fixed left-0 top-0 z-[80]"
            style={{ width: drag.w }}
            initial={{ x: drag.x - drag.dx, y: drag.y - drag.dy, scale: 1, rotate: 0 }}
            animate={
              drag.drop
                ? { x: drag.drop.x, y: drag.drop.y, scale: 1, rotate: 0 }
                : { x: drag.x - drag.dx, y: drag.y - drag.dy, scale: 1.025, rotate: 1.4 }
            }
            transition={
              drag.drop
                ? { type: 'spring', stiffness: 520, damping: 38 }
                : { x: { duration: 0 }, y: { duration: 0 }, scale: { duration: 0.15 }, rotate: { duration: 0.2 } }
            }
            onAnimationComplete={() => {
              if (drag.drop) commitDrop()
            }}
          >
            <CardBody card={drag.card} ghost />
          </motion.div>,
          document.body,
        )}
    </>
  )
}

interface ColumnProps {
  col: ColumnDef
  cards: Card[]
  total: number
  filtering: boolean
  limit: number
  onMore: () => void
  drag: DragState | null
  target: Target | null
  droppedId: React.RefObject<string | null>
  selectedId: string | null
  startPointer: (e: React.PointerEvent<HTMLElement>, card: Card) => void
  onToggle: () => void
  onCopyId: (id: string) => void
  onKeyOpen: (card: Card) => void
  onCardMenu: (e: React.MouseEvent, card: Card) => void
  onColumnMenu: (e: React.MouseEvent) => void
}

function Column(p: ColumnProps) {
  const { col, drag, target } = p
  const isTarget = !!drag && target?.col === col.id
  const visible = p.cards.filter((c) => c.id !== drag?.card.id)
  const shown = visible.slice(0, p.limit)
  const hidden = visible.length - shown.length
  const count = p.filtering ? `${p.cards.length}/${p.total}` : String(p.cards.length)

  const placeholder = drag && (
    <motion.div
      key="__placeholder"
      data-placeholder
      layout="position"
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: drag.h + 8, opacity: 1 }}
      exit={{ height: 0, opacity: 0, transition: { duration: 0 } }}
      transition={{ duration: 0.16, ease: 'easeOut' }}
      className="overflow-hidden"
    >
      <div className="rounded-xl border border-dashed border-fg/40 bg-subtle/60" style={{ height: drag.h }} />
    </motion.div>
  )

  return (
    <section
      data-col={col.id}
      className={cn(
        'flex h-full min-h-0 w-[min(82vw,320px)] min-w-[272px] flex-1 flex-col rounded-2xl transition-colors duration-200 max-sm:snap-center',
        isTarget && 'bg-muted',
      )}
    >
      <header
        data-col-header
        onContextMenu={p.onColumnMenu}
        className="group/h flex items-center justify-between px-2.5 pb-2 pt-2"
      >
        <Tooltip label="Collapse column" side="bottom" delay={600}>
          <button onClick={p.onToggle} className="flex items-center gap-2 rounded-md py-0.5 pr-1 text-left">
            <ChevronDown size={14} className="text-fg-faint transition-colors group-hover/h:text-fg" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-fg">{col.label}</span>
            <span className="rounded-full border border-line-strong px-1.5 font-mono text-[10.5px] leading-[18px] text-fg-muted">
              {count}
            </span>
          </button>
        </Tooltip>
        {/* No add-card button: the tracker backend has no create endpoint
            yet, so creation is hidden until it does (see README). */}
      </header>

      <motion.div data-list layoutScroll className="thin-scroll relative min-h-0 flex-1 overflow-y-auto px-1.5 pb-16">
        <AnimatePresence initial={false}>
          {shown.flatMap((c) => {
            const out = []
            if (isTarget && target.beforeId === c.id) out.push(placeholder)
            out.push(
              <BoardCard
                key={c.id}
                card={c}
                selected={p.selectedId === c.id}
                instant={p.droppedId.current === c.id}
                startPointer={p.startPointer}
                onCopyId={p.onCopyId}
                onKeyOpen={p.onKeyOpen}
                onContextMenu={p.onCardMenu}
              />,
            )
            return out
          })}
          {isTarget && (target.beforeId === null || !shown.some((c) => c.id === target.beforeId)) && placeholder}
        </AnimatePresence>

        {hidden > 0 && (
          <button
            onClick={p.onMore}
            className="mb-2 w-full rounded-xl border border-dashed border-line-strong py-2 text-xs text-fg-muted transition-colors hover:border-fg hover:text-fg"
          >
            Show {Math.min(hidden, PAGE)} more · {hidden} hidden
          </button>
        )}

        {visible.length === 0 && !isTarget && (
          <div className="mx-1 mt-1 flex h-24 items-center justify-center rounded-xl border border-dashed border-line text-xs text-fg-faint">
            {p.filtering ? 'No matching cards' : 'Nothing here yet'}
          </div>
        )}
      </motion.div>
    </section>
  )
}

interface BoardCardProps {
  card: Card
  selected: boolean
  instant: boolean
  startPointer: (e: React.PointerEvent<HTMLElement>, card: Card) => void
  onCopyId: (id: string) => void
  onKeyOpen: (card: Card) => void
  onContextMenu: (e: React.MouseEvent, card: Card) => void
}

function BoardCard({ card, selected, instant, startPointer, onCopyId, onKeyOpen, onContextMenu }: BoardCardProps) {
  return (
    <motion.div
      layout="position"
      data-card-id={card.id}
      initial={instant ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
      transition={{ duration: 0.2, ease: 'easeOut', layout: { type: 'spring', stiffness: 520, damping: 42 } }}
      tabIndex={0}
      role="button"
      aria-label={`${card.id} ${card.title}`}
      onPointerDown={(e) => startPointer(e, card)}
      onContextMenu={(e) => onContextMenu(e, card)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onKeyOpen(card)
        }
      }}
      className={cn(
        'cursor-grab pb-2 outline-none active:cursor-grabbing focus-visible:[&>div]:border-fg',
        selected && '[&>div]:border-fg',
      )}
    >
      <CardBody card={card} onCopyId={onCopyId} />
    </motion.div>
  )
}

interface CollapsedProps {
  col: ColumnDef
  count: number
  total: number
  filtering: boolean
  active: boolean
  onToggle: () => void
  onContextMenu: (e: React.MouseEvent) => void
}

function CollapsedColumn({ col, count, total, filtering, active, onToggle, onContextMenu }: CollapsedProps) {
  return (
    <Tooltip label={`Expand ${col.label}`} className="inline-flex h-full shrink-0 max-sm:snap-center">
      <section
        data-col={col.id}
        data-collapsed="1"
        onContextMenu={onContextMenu}
        className={cn(
          'flex h-full w-11 shrink-0 flex-col items-center rounded-2xl border border-dashed transition-colors duration-200',
          active ? 'border-fg bg-muted' : 'border-line hover:border-line-strong hover:bg-muted',
        )}
      >
        <button onClick={onToggle} className="flex h-full w-full flex-col items-center gap-3 py-3">
          <span className="rounded-full border border-line-strong px-1.5 font-mono text-[10.5px] leading-[18px] text-fg-muted">
            {filtering ? `${count}/${total}` : count}
          </span>
          <span
            className="text-[11px] font-semibold uppercase tracking-[0.14em] text-fg-muted"
            style={{ writingMode: 'vertical-rl' }}
          >
            {col.label}
          </span>
        </button>
      </section>
    </Tooltip>
  )
}
