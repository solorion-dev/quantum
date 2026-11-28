import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'

interface Props {
  label: ReactNode
  shortcut?: string
  side?: 'top' | 'bottom'
  delay?: number
  className?: string
  children: ReactNode
}

export function Tooltip({ label, shortcut, side = 'top', delay = 380, className, children }: Props) {
  const ref = useRef<HTMLSpanElement>(null)
  const timer = useRef(0)
  const [pos, setPos] = useState<{ x: number; y: number; side: 'top' | 'bottom' } | null>(null)

  const hide = () => {
    window.clearTimeout(timer.current)
    setPos(null)
  }
  const show = (wait: number) => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      if (document.body.dataset.dragging || !ref.current) return
      const r = ref.current.getBoundingClientRect()
      let s = side
      if (s === 'top' && r.top < 56) s = 'bottom'
      if (s === 'bottom' && r.bottom > window.innerHeight - 56) s = 'top'
      const x = Math.min(Math.max(r.left + r.width / 2, 90), window.innerWidth - 90)
      setPos({ x, y: s === 'top' ? r.top - 8 : r.bottom + 8, side: s })
    }, wait)
  }

  useEffect(() => {
    if (!pos) return
    const close = () => setPos(null)
    window.addEventListener('scroll', close, true)
    window.addEventListener('pointerdown', close, true)
    window.addEventListener('contextmenu', close, true)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('pointerdown', close, true)
      window.removeEventListener('contextmenu', close, true)
    }
  }, [pos])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  return (
    <span
      ref={ref}
      className={className ?? 'inline-flex'}
      onMouseEnter={() => show(delay)}
      onMouseLeave={hide}
      onFocus={() => show(150)}
      onBlur={hide}
    >
      {children}
      {pos &&
        createPortal(
          <div
            className={`pointer-events-none fixed z-[100] -translate-x-1/2 ${pos.side === 'top' ? '-translate-y-full' : ''}`}
            style={{ left: pos.x, top: pos.y }}
          >
            <motion.div
              initial={{ opacity: 0, y: pos.side === 'top' ? 4 : -4, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.14, ease: 'easeOut' }}
              className="flex max-w-[260px] items-center gap-2 rounded-md bg-fg px-2 py-1 text-[11.5px] font-medium leading-snug text-bg shadow-lg"
            >
              <span>{label}</span>
              {shortcut && (
                <kbd className="rounded bg-bg/20 px-1 font-mono text-[10px] text-bg/80">{shortcut}</kbd>
              )}
            </motion.div>
          </div>,
          document.body,
        )}
    </span>
  )
}
