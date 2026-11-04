// Local popover built from kit parts (btn + panel classes). Candidate to upstream to @dsect/ui.
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'

export function Popover({ label, trigger, children, align = 'start', className = '' }: {
  label: string; trigger: ReactNode; children: ReactNode | ((close: () => void) => ReactNode); align?: 'start' | 'end'; className?: string
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const root = useRef<HTMLDivElement>(null)
  const btn = useRef<HTMLButtonElement>(null)
  const close = () => { setOpen(false); btn.current?.focus() }
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); close() } }
    document.addEventListener('mousedown', onDown)
    root.current?.addEventListener('keydown', onKey)
    const r = root.current
    queueMicrotask(() => r?.querySelector<HTMLElement>('.tb-popover input, .tb-popover button')?.focus())
    return () => { document.removeEventListener('mousedown', onDown); r?.removeEventListener('keydown', onKey) }
  }, [open])
  return (
    <div className={`tb-popover-root ${className}`} ref={root}>
      <button ref={btn} type="button" className="btn btn-outline btn-small tb-popover-trigger"
        aria-haspopup="dialog" aria-expanded={open} aria-controls={id} aria-label={label} onClick={() => setOpen((o) => !o)}>
        {trigger}
      </button>
      {open && (
        <div id={id} role="dialog" aria-label={label} className={`panel tb-popover tb-popover--${align}`}>
          {/* eslint-disable-next-line react-hooks/refs -- close() only touches the ref when invoked from an event handler */}
          {typeof children === 'function' ? children(close) : children}
        </div>
      )}
    </div>
  )
}
