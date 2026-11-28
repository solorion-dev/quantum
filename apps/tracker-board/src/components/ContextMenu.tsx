import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { Check, ChevronRight } from 'lucide-react'
import { cn } from '../lib/cn'

export type MenuItem =
  | {
      kind: 'item'
      label: string
      icon?: ReactNode
      hint?: string
      danger?: boolean
      checked?: boolean
      disabled?: boolean
      onSelect?: () => void
      children?: MenuItem[]
    }
  | { kind: 'sep' }
  | { kind: 'label'; label: string }

interface PanelProps {
  items: MenuItem[]
  onClose: () => void
  style?: CSSProperties
  className?: string
  panelRef?: React.Ref<HTMLDivElement>
}

function Panel({ items, onClose, style, className, panelRef }: PanelProps) {
  const [openIdx, setOpenIdx] = useState<number | null>(null)

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const root = e.currentTarget
    const nodes = Array.from(
      root.querySelectorAll<HTMLElement>(':scope > [role="menuitem"]:not([disabled]), :scope > div > [role="menuitem"]:not([disabled])'),
    )
    if (!nodes.length) return
    const i = nodes.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      nodes[(i + 1) % nodes.length].focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      nodes[(i - 1 + nodes.length) % nodes.length].focus()
    } else if (e.key === 'ArrowRight' && i >= 0 && nodes[i].dataset.sub) {
      e.preventDefault()
      setOpenIdx(Number(nodes[i].dataset.sub))
    } else if (e.key === 'ArrowLeft') {
      setOpenIdx(null)
    }
  }

  return (
    <div
      ref={panelRef}
      role="menu"
      onKeyDown={onKeyDown}
      style={style}
      className={cn(
        'min-w-[208px] rounded-xl border border-line bg-surface p-1 text-[13px] text-fg shadow-[0_12px_40px_-8px_rgba(0,0,0,0.25)]',
        className,
      )}
    >
      {items.map((it, i) => {
        if (it.kind === 'sep') return <div key={i} className="my-1 h-px bg-line" />
        if (it.kind === 'label')
          return (
            <div key={i} className="px-2.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-fg-faint">
              {it.label}
            </div>
          )
        const hasSub = !!it.children?.length
        return (
          <div key={i} className="relative" onMouseEnter={() => setOpenIdx(hasSub ? i : null)}>
            <button
              role="menuitem"
              data-sub={hasSub ? i : undefined}
              disabled={it.disabled}
              onClick={() => {
                if (hasSub) {
                  setOpenIdx(i)
                  return
                }
                it.onSelect?.()
                onClose()
              }}
              className={cn(
                'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left outline-none transition-colors',
                'hover:bg-subtle focus:bg-subtle disabled:opacity-40',
                openIdx === i && 'bg-subtle',
                it.danger && 'text-fg',
              )}
            >
              <span className="flex h-4 w-4 shrink-0 items-center justify-center text-fg-muted">
                {it.checked ? <Check size={14} strokeWidth={2.5} className="text-fg" /> : it.icon}
              </span>
              <span className={cn('flex-1 truncate', it.danger && 'font-medium')}>{it.label}</span>
              {it.hint && <span className="font-mono text-[10.5px] text-fg-faint">{it.hint}</span>}
              {hasSub && <ChevronRight size={14} className="text-fg-faint" />}
            </button>
            {hasSub && openIdx === i && <SubPanel items={it.children!} onClose={onClose} />}
          </div>
        )
      })}
    </div>
  )
}

function SubPanel({ items, onClose }: { items: MenuItem[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [place, setPlace] = useState({ flip: false, shift: 0 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPlace({
      flip: r.right > window.innerWidth - 8,
      shift: Math.max(0, r.bottom - window.innerHeight + 8),
    })
  }, [])
  return (
    <motion.div
      initial={{ opacity: 0, x: place.flip ? 4 : -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.12 }}
      className={cn('absolute z-10', place.flip ? 'right-full pr-1' : 'left-full pl-1')}
      style={{ top: -5 - place.shift }}
    >
      <Panel items={items} onClose={onClose} panelRef={ref} />
    </motion.div>
  )
}

interface Props {
  x: number
  y: number
  items: MenuItem[]
  onClose: () => void
}

export function ContextMenu({ x, y, items, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ x, y })

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPos({
      x: Math.max(8, Math.min(x, window.innerWidth - r.width - 8)),
      y: Math.max(8, Math.min(y, window.innerHeight - r.height - 8)),
    })
  }, [x, y])

  useEffect(() => {
    const down = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    const close = () => onClose()
    window.addEventListener('pointerdown', down, true)
    window.addEventListener('keydown', key, true)
    window.addEventListener('resize', close)
    window.addEventListener('blur', close)
    window.addEventListener('wheel', close, { passive: true })
    return () => {
      window.removeEventListener('pointerdown', down, true)
      window.removeEventListener('keydown', key, true)
      window.removeEventListener('resize', close)
      window.removeEventListener('blur', close)
      window.removeEventListener('wheel', close)
    }
  }, [onClose])

  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus({ preventScroll: true })
  }, [])

  return createPortal(
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: -4 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.13, ease: 'easeOut' }}
      className="fixed z-[90] origin-top-left"
      style={{ left: pos.x, top: pos.y }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <Panel items={items} onClose={onClose} panelRef={ref} />
    </motion.div>,
    document.body,
  )
}
