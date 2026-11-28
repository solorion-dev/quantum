import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Copy, Link2, Trash2, X } from 'lucide-react'
import { Tooltip } from './Tooltip'
import { PriorityGlyph } from './CardBody'
import { cn } from '../lib/cn'
import { dateTimeLabel } from '../lib/format'
import { fetchItemDetail } from '../lib/api'
import type { ItemDetail } from '../lib/api'
import { COLUMNS, POINT_OPTIONS, PRIORITIES } from '../types'
import type { Card } from '../types'

interface Props {
  card: Card
  assignees: string[]
  onClose: () => void
  onUpdate: (patch: Partial<Card>, message?: string) => void
  onDelete: () => void
  onCopy: (text: string, label: string) => void
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[84px_1fr] items-start gap-3 py-2.5">
      <span className="pt-1 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-fg-faint">{label}</span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  )
}

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[12px] capitalize transition-all active:scale-95',
        active
          ? 'border-fg bg-fg font-medium text-bg'
          : 'border-line text-fg-muted hover:border-line-strong hover:text-fg',
      )}
    >
      {children}
    </button>
  )
}

/** A value the backend cannot store (kind, project, stale) — shown, not edited. */
function ReadOnlyChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex h-7 items-center gap-1.5 rounded-full border border-dashed border-line-strong px-2.5 text-[12px] capitalize text-fg-muted">
      {children}
    </span>
  )
}

const eventTime = (ts: string) => {
  const t = Date.parse(ts)
  return Number.isNaN(t) ? ts : dateTimeLabel(t)
}

export function Drawer({ card, assignees, onClose, onUpdate, onDelete, onCopy }: Props) {
  const [title, setTitle] = useState(card.title)
  const [desc, setDesc] = useState(card.description)
  const [loadedDesc, setLoadedDesc] = useState(card.description)
  const descDirty = useRef(false)
  const [detail, setDetail] = useState<ItemDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const titleRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = titleRef.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = el.scrollHeight + 'px'
  }, [title])

  // The board snapshot carries no body/comments/history — load the real
  // record from the tracker service whenever the drawer opens.
  useEffect(() => {
    let live = true
    fetchItemDetail(card.id)
      .then((d) => {
        if (!live) return
        setDetail(d)
        const body = typeof d.item.body === 'string' ? d.item.body : ''
        if (!descDirty.current) {
          setDesc(body)
          setLoadedDesc(body)
        }
      })
      .catch((e: Error) => {
        if (live) setDetailError(e.message)
      })
    return () => {
      live = false
    }
  }, [card.id])

  const commitTitle = () => {
    if (title !== card.title) onUpdate({ title: title.trim() })
  }
  const commitDesc = () => {
    if (desc !== loadedDesc) {
      onUpdate({ description: desc })
      setLoadedDesc(desc)
    }
  }

  const createdAt = detail && typeof detail.item.created_at === 'string' ? Date.parse(detail.item.created_at) : card.createdAt
  const updatedAt = detail && typeof detail.item.updated_at === 'string' ? Date.parse(detail.item.updated_at) : card.updatedAt

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        onClick={onClose}
        className="fixed inset-0 z-40 bg-fg/10 backdrop-blur-[2px]"
      />
      <motion.aside
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', stiffness: 380, damping: 40 }}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[460px] flex-col border-l border-line bg-bg shadow-[-24px_0_48px_-24px_rgba(0,0,0,0.25)]"
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-[12px] text-fg-muted">{card.id}</span>
            <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-fg-faint">{card.kind}</span>
          </div>
          <div className="flex items-center gap-0.5">
            {[
              { label: 'Copy ID', icon: <Copy size={15} />, run: () => onCopy(card.id, card.id) },
              {
                label: 'Copy link',
                icon: <Link2 size={15} />,
                run: () => onCopy(`${location.origin}${location.pathname}#${card.id}`, 'Link'),
              },
              // No Duplicate: duplicating is a create, and the backend has no
              // create endpoint yet (see README).
              { label: 'Cancel card', icon: <Trash2 size={15} />, run: onDelete },
            ].map((b) => (
              <Tooltip key={b.label} label={b.label} side="bottom">
                <button
                  onClick={b.run}
                  aria-label={b.label}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-subtle hover:text-fg active:scale-95"
                >
                  {b.icon}
                </button>
              </Tooltip>
            ))}
            <Tooltip label="Close" shortcut="Esc" side="bottom">
              <button
                onClick={onClose}
                aria-label="Close"
                className="ml-1 flex h-8 w-8 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-subtle hover:text-fg active:scale-95"
              >
                <X size={16} />
              </button>
            </Tooltip>
          </div>
        </div>

        <div className="thin-scroll flex-1 overflow-y-auto px-5 pb-8 pt-5">
          <textarea
            ref={titleRef}
            rows={1}
            value={title}
            placeholder="Untitled"
            onChange={(e) => setTitle(e.target.value.replace(/\n/g, ' '))}
            onBlur={commitTitle}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                e.currentTarget.blur()
              }
            }}
            className="w-full resize-none overflow-hidden bg-transparent text-[22px] font-semibold leading-[1.2] tracking-[-0.02em] outline-none placeholder:text-fg-faint"
          />

          <div className="mt-4 divide-y divide-line border-y border-line">
            <Row label="Status">
              {COLUMNS.map((c) => (
                <Pill
                  key={c.id}
                  active={card.column === c.id}
                  onClick={() => card.column !== c.id && onUpdate({ column: c.id }, `${card.id} moved to ${c.label}`)}
                >
                  {c.label}
                </Pill>
              ))}
            </Row>
            <Row label="Priority">
              {PRIORITIES.map((p) => (
                <Pill key={p.id} active={card.priority === p.id} onClick={() => onUpdate({ priority: p.id })}>
                  <span className={cn('flex', card.priority === p.id && 'invert')}>
                    <PriorityGlyph priority={p.id} />
                  </span>
                  {p.label}
                </Pill>
              ))}
            </Row>
            <Row label="Type">
              {/* Kind is not in the backend's update whitelist — read-only. */}
              <ReadOnlyChip>{card.kind}</ReadOnlyChip>
            </Row>
            <Row label="Assignee">
              <Pill active={!card.assignee} onClick={() => onUpdate({ assignee: null })}>
                none
              </Pill>
              {assignees.map((a) => (
                <Pill key={a} active={card.assignee === a} onClick={() => onUpdate({ assignee: a })}>
                  {a}
                </Pill>
              ))}
            </Row>
            <Row label="Points">
              <Pill active={card.points == null} onClick={() => onUpdate({ points: null })}>
                none
              </Pill>
              {POINT_OPTIONS.map((n) => (
                <Pill key={n} active={card.points === n} onClick={() => onUpdate({ points: n })}>
                  {n}
                </Pill>
              ))}
            </Row>
            <Row label="Due">
              <input
                type="date"
                value={card.due ?? ''}
                onChange={(e) => onUpdate({ due: e.target.value || null })}
                className="h-7 rounded-lg border border-line bg-transparent px-2 font-mono text-[12px] outline-none transition-colors hover:border-line-strong focus:border-fg"
              />
              {card.due && (
                <Tooltip label="Clear due date">
                  <button
                    onClick={() => onUpdate({ due: null })}
                    aria-label="Clear due date"
                    className="flex h-7 w-7 items-center justify-center rounded-lg text-fg-muted hover:bg-subtle hover:text-fg"
                  >
                    <X size={14} />
                  </button>
                </Tooltip>
              )}
            </Row>
            <Row label="Project">
              {/* Project membership lives in backend relations, not in the
                  update whitelist — read-only. */}
              <ReadOnlyChip>{card.project}</ReadOnlyChip>
            </Row>
            <Row label="Flags">
              {/* Stale is derived from updated_at in the data layer. */}
              {card.stale ? <ReadOnlyChip>stale</ReadOnlyChip> : <span className="pt-1 text-[12px] text-fg-faint">—</span>}
            </Row>
          </div>

          <label className="mt-5 block text-[10.5px] font-semibold uppercase tracking-[0.14em] text-fg-faint">
            Description
            <textarea
              value={desc}
              onChange={(e) => {
                descDirty.current = true
                setDesc(e.target.value)
              }}
              onBlur={commitDesc}
              placeholder={detail ? 'Add notes, links, context…' : 'Loading…'}
              className="mt-2 min-h-[150px] w-full resize-y rounded-xl border border-line bg-transparent p-3 text-[13.5px] font-normal normal-case leading-relaxed tracking-normal text-fg outline-none transition-colors placeholder:text-fg-faint hover:border-line-strong focus:border-fg"
            />
          </label>

          {detailError && <p className="mt-3 text-[12px] text-fg-muted">Couldn’t load the live record — {detailError}</p>}

          {detail && detail.comments.length > 0 && (
            <div className="mt-6">
              <h3 className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-fg-faint">Comments</h3>
              <div className="mt-2 space-y-3">
                {detail.comments.map((c, i) => (
                  <div key={i} className="rounded-xl border border-line p-3">
                    <p className="text-[11px] text-fg-faint">
                      <span className="font-medium text-fg-muted">{c.actor}</span> · {eventTime(c.ts)}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed">{c.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {detail && detail.history.length > 0 && (
            <div className="mt-6">
              <h3 className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-fg-faint">Activity</h3>
              <ul className="mt-2 space-y-1.5">
                {[...detail.history].reverse().map((h, i) => (
                  <li key={i} className="font-mono text-[11px] leading-relaxed text-fg-muted">
                    {eventTime(h.ts)} · {h.actor} · {h.text}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="mt-4 font-mono text-[11px] text-fg-faint">
            Created {dateTimeLabel(createdAt)} · Updated {dateTimeLabel(updatedAt)}
          </p>
        </div>
      </motion.aside>
    </>
  )
}
