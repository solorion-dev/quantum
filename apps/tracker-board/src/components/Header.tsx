import { useRef } from 'react'
import type { RefObject } from 'react'
import { motion } from 'framer-motion'
import { ChevronDown, Columns3, Flag, FolderKanban, List, Moon, Search, Settings, Sun, User, X } from 'lucide-react'
import { Tooltip } from './Tooltip'
import type { MenuItem } from './ContextMenu'
import { cn } from '../lib/cn'
import { timeLabel } from '../lib/format'
import type { SyncStatus } from '../lib/api'
import { PRIORITIES } from '../types'
import type { Priority } from '../types'

export interface Filters {
  project: string | null
  assignee: string | null
  priority: Priority | null
}

interface Props {
  stats: { open: number; done: number; cancelled: number }
  query: string
  setQuery: (q: string) => void
  searchRef: RefObject<HTMLInputElement | null>
  filters: Filters
  setFilters: (f: Filters) => void
  projects: string[]
  assignees: string[]
  view: 'board' | 'list'
  setView: (v: 'board' | 'list') => void
  theme: 'light' | 'dark'
  toggleTheme: () => void
  onSettings: () => void
  status: SyncStatus
  syncedAt: number
  onRefresh: () => void
  openMenu: (x: number, y: number, items: MenuItem[]) => void
}

function IconButton({
  label,
  shortcut,
  onClick,
  children,
}: {
  label: string
  shortcut?: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <Tooltip label={label} shortcut={shortcut} side="bottom">
      <button
        onClick={onClick}
        aria-label={label}
        className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-subtle hover:text-fg active:scale-95"
      >
        {children}
      </button>
    </Tooltip>
  )
}

function FilterButton({
  icon,
  label,
  value,
  onOpen,
}: {
  icon: React.ReactNode
  label: string
  value: string | null
  onOpen: (rect: DOMRect) => void
}) {
  const ref = useRef<HTMLButtonElement>(null)
  return (
    <button
      ref={ref}
      onClick={() => ref.current && onOpen(ref.current.getBoundingClientRect())}
      className={cn(
        'flex h-8 shrink-0 items-center gap-1.5 rounded-lg border px-2.5 text-[12.5px] transition-colors active:scale-[0.98]',
        value ? 'border-fg bg-fg text-bg' : 'border-line text-fg-muted hover:border-line-strong hover:text-fg',
      )}
    >
      {icon}
      <span className="capitalize">{value ?? label}</span>
      <ChevronDown size={13} className="opacity-60" />
    </button>
  )
}

export function Header(p: Props) {
  const active = p.filters.project || p.filters.assignee || p.filters.priority
  const f = p.filters

  const statusText = p.status === 'live' ? 'Live' : p.status === 'syncing' ? 'Syncing' : 'Offline'
  const statusTip =
    p.status === 'offline'
      ? 'Backend unreachable — click to retry'
      : `Synced ${timeLabel(p.syncedAt)} — click to refresh`

  return (
    <header className="shrink-0 px-4 pb-3 pt-4 sm:px-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-fg text-bg">
              <Columns3 size={15} strokeWidth={2.2} />
            </span>
            <h1 className="text-[22px] font-semibold leading-none tracking-[-0.03em]">Tracker</h1>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-fg-muted">
            <Tooltip label={statusTip} side="bottom">
              <button
                onClick={() => p.onRefresh()}
                className="flex items-center gap-1.5 rounded-md font-medium text-fg"
              >
                <span
                  className={cn(
                    'h-1.5 w-1.5 rounded-full',
                    p.status === 'offline' ? 'bg-transparent ring-1 ring-fg' : 'bg-fg',
                    (p.status === 'live' || p.status === 'syncing') && 'pulse-dot',
                  )}
                />
                {statusText}
              </button>
            </Tooltip>
            <span className="text-fg-faint">·</span>
            <span><b className="font-semibold text-fg">{p.stats.open}</b> open</span>
            <span className="text-fg-faint">·</span>
            <span><b className="font-semibold text-fg">{p.stats.done}</b> done</span>
            <span className="text-fg-faint">·</span>
            <span><b className="font-semibold text-fg">{p.stats.cancelled}</b> cancelled</span>
            <span className="hidden text-fg-faint md:inline">·</span>
            <span className="hidden md:inline">click a card for details · drag to move · right-click for actions</span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <div className="relative mr-1 hidden rounded-lg bg-subtle p-0.5 sm:flex">
            {(['board', 'list'] as const).map((v) => (
              <Tooltip key={v} label={v === 'board' ? 'Board view' : 'List view'} shortcut="V" side="bottom">
                <button
                  onClick={() => p.setView(v)}
                  aria-label={v}
                  className={cn(
                    'relative z-10 flex h-7 w-8 items-center justify-center rounded-md transition-colors',
                    p.view === v ? 'text-fg' : 'text-fg-faint hover:text-fg',
                  )}
                >
                  {p.view === v && (
                    <motion.span
                      layoutId="view-pill"
                      className="absolute inset-0 -z-10 rounded-md bg-surface shadow-sm ring-1 ring-line"
                      transition={{ type: 'spring', stiffness: 500, damping: 36 }}
                    />
                  )}
                  {v === 'board' ? <Columns3 size={15} /> : <List size={15} />}
                </button>
              </Tooltip>
            ))}
          </div>
          <IconButton
            label={p.theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            shortcut="D"
            onClick={p.toggleTheme}
          >
            <motion.span key={p.theme} initial={{ rotate: -60, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} transition={{ duration: 0.25 }}>
              {p.theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </motion.span>
          </IconButton>
          <IconButton label="Server & data settings" onClick={p.onSettings}>
            <Settings size={16} />
          </IconButton>
          {/* No "New" button: the tracker backend has no create endpoint yet,
              so card creation is hidden until it does (see README). */}
        </div>
      </div>

      <div className="thin-scroll mt-3.5 flex items-center gap-2 overflow-x-auto pb-1">
        <label className="group relative flex h-8 w-full min-w-[200px] max-w-[340px] shrink items-center">
          <Search size={14} className="absolute left-2.5 text-fg-faint transition-colors group-focus-within:text-fg" />
          <input
            ref={p.searchRef}
            value={p.query}
            onChange={(e) => p.setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                p.setQuery('')
                e.currentTarget.blur()
              }
            }}
            placeholder="Filter by text or TRK id…"
            className="h-full w-full rounded-lg border border-line bg-transparent pl-8 pr-8 text-[13px] outline-none transition-[border-color,box-shadow] placeholder:text-fg-faint hover:border-line-strong focus:border-fg focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--fg)_8%,transparent)]"
          />
          {p.query ? (
            <button
              onClick={() => {
                p.setQuery('')
                p.searchRef.current?.focus()
              }}
              aria-label="Clear search"
              className="absolute right-2 text-fg-faint hover:text-fg"
            >
              <X size={14} />
            </button>
          ) : (
            <kbd className="absolute right-2 rounded border border-line px-1 font-mono text-[10px] text-fg-faint">/</kbd>
          )}
        </label>

        <FilterButton
          icon={<FolderKanban size={13} />}
          label="Project"
          value={f.project}
          onOpen={(r) =>
            p.openMenu(r.left, r.bottom + 6, [
              { kind: 'item', label: 'All projects', checked: !f.project, onSelect: () => p.setFilters({ ...f, project: null }) },
              { kind: 'sep' },
              ...p.projects.map<MenuItem>((x) => ({
                kind: 'item',
                label: x,
                checked: f.project === x,
                onSelect: () => p.setFilters({ ...f, project: x }),
              })),
            ])
          }
        />
        <FilterButton
          icon={<User size={13} />}
          label="Assignee"
          value={f.assignee}
          onOpen={(r) =>
            p.openMenu(r.left, r.bottom + 6, [
              { kind: 'item', label: 'Anyone', checked: !f.assignee, onSelect: () => p.setFilters({ ...f, assignee: null }) },
              { kind: 'sep' },
              ...p.assignees.map<MenuItem>((x) => ({
                kind: 'item',
                label: x,
                checked: f.assignee === x,
                onSelect: () => p.setFilters({ ...f, assignee: x }),
              })),
            ])
          }
        />
        <FilterButton
          icon={<Flag size={13} />}
          label="Priority"
          value={f.priority}
          onOpen={(r) =>
            p.openMenu(r.left, r.bottom + 6, [
              { kind: 'item', label: 'Any priority', checked: !f.priority, onSelect: () => p.setFilters({ ...f, priority: null }) },
              { kind: 'sep' },
              ...PRIORITIES.map<MenuItem>((x) => ({
                kind: 'item',
                label: x.label,
                checked: f.priority === x.id,
                onSelect: () => p.setFilters({ ...f, priority: x.id }),
              })),
            ])
          }
        />
        {(active || p.query) && (
          <button
            onClick={() => {
              p.setFilters({ project: null, assignee: null, priority: null })
              p.setQuery('')
            }}
            className="h-8 shrink-0 rounded-lg px-2 text-[12.5px] text-fg-muted underline-offset-4 hover:text-fg hover:underline"
          >
            Clear all
          </button>
        )}
      </div>
    </header>
  )
}
