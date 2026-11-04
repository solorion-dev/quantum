import type { Card } from '../types'

const pad = (n: number) => String(n).padStart(2, '0')

export function todayISO(): string {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export interface DueInfo {
  label: string
  tip: string
  overdue: boolean
  soon: boolean
}

export function dueInfo(card: Card): DueInfo | null {
  if (!card.due) return null
  const closed = card.column === 'done' || card.column === 'cancelled'
  const d = new Date(card.due + 'T00:00:00')
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  const t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diff = Math.round((d.getTime() - t0.getTime()) / 86400000)
  const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const full = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
  let tip: string
  if (closed) tip = `Was due ${full}`
  else if (diff < 0) tip = `${full} · ${-diff} day${diff === -1 ? '' : 's'} overdue`
  else if (diff === 0) tip = `${full} · due today`
  else if (diff === 1) tip = `${full} · due tomorrow`
  else tip = `${full} · in ${diff} days`
  return { label, tip, overdue: !closed && diff < 0, soon: !closed && diff >= 0 && diff <= 2 }
}

export function timeLabel(ts: number): string {
  return new Date(ts).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

export function dateTimeLabel(ts: number): string {
  return new Date(ts).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function initials(name: string): string {
  return name.slice(0, 1).toUpperCase()
}

export function nextId(cards: Card[]): string {
  let max = 0
  for (const c of cards) {
    const n = parseInt(c.id.replace(/\D/g, ''), 10)
    if (!Number.isNaN(n) && n > max) max = n
  }
  return `TRK-${String(max + 1).padStart(4, '0')}`
}
