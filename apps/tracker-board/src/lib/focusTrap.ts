// Robust Tab trap for native <dialog>/popover containers. showModal() alone lets Tab wrap out to the
// browser chrome / document once per cycle (Scout B8); this keeps focus cycling inside `root`.
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'

const SEL = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function focusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(SEL)].filter((el) => !el.closest('[inert]') && el.getClientRects().length > 0)
}

export function trapTab(e: ReactKeyboardEvent<HTMLElement> | KeyboardEvent, root: HTMLElement | null) {
  if (e.key !== 'Tab' || !root) return
  const els = focusables(root)
  if (els.length === 0) { e.preventDefault(); return }
  const first = els[0], last = els[els.length - 1]
  const active = document.activeElement as HTMLElement | null
  const inside = !!active && root.contains(active)
  if (e.shiftKey) {
    if (!inside || active === first) { e.preventDefault(); last.focus() }
  } else if (!inside || active === last) { e.preventDefault(); first.focus() }
}
