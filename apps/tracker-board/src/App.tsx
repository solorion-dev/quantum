import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import {
  ArrowDownUp,
  ArrowRight,
  Check,
  ChevronsLeftRight,
  Copy,
  Flag,
  Link2,
  Moon,
  PanelRight,
  Sun,
  Trash2,
  Undo2,
  User,
  Columns3,
  List,
} from 'lucide-react'
import { Board } from './components/Board'
import { ContextMenu } from './components/ContextMenu'
import type { MenuItem } from './components/ContextMenu'
import { Drawer } from './components/Drawer'
import { Header } from './components/Header'
import type { Filters } from './components/Header'
import { ListView } from './components/ListView'
import { Settings } from './components/Settings'
import { Toast } from './components/Toast'
import type { ToastData } from './components/Toast'
import { useBoard } from './lib/store'
import { COLUMNS, COLUMN_LABEL, PRIORITIES } from './types'
import type { Card, ColumnId } from './types'

type Theme = 'light' | 'dark'

function initialTheme(): Theme {
  try {
    const s = localStorage.getItem('tracker.theme')
    if (s === 'light' || s === 'dark') return s
  } catch {
    /* ignore */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const defaultCollapsed = () =>
  Object.fromEntries(COLUMNS.map((c) => [c.id, !!c.defaultCollapsed])) as Record<ColumnId, boolean>

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [view, setView] = useState<'board' | 'list'>(() => (localStorage.getItem('tracker.view') === 'list' ? 'list' : 'board'))
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<Filters>({ project: null, assignee: null, priority: null })
  const [collapsed, setCollapsed] = useState<Record<ColumnId, boolean>>(defaultCollapsed)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [toast, setToast] = useState<ToastData | null>(null)
  const toastTimer = useRef(0)
  const toastId = useRef(0)
  const searchRef = useRef<HTMLInputElement>(null)

  const notify = useCallback((message: string, undoable = false) => {
    window.clearTimeout(toastTimer.current)
    setToast({ id: ++toastId.current, message, undoable })
    toastTimer.current = window.setTimeout(() => setToast(null), 4500)
  }, [])

  const board = useBoard(notify)
  const { cards } = board

  // theme
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem('tracker.theme', theme)
    } catch {
      /* ignore */
    }
  }, [theme])
  useEffect(() => {
    try {
      localStorage.setItem('tracker.view', view)
    } catch {
      /* ignore */
    }
  }, [view])

  const toggleTheme = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), [])

  const projects = useMemo(() => Array.from(new Set(cards.map((c) => c.project))).sort(), [cards])
  const assignees = useMemo(() => {
    const s = new Set<string>(['cooper', 'scotty'])
    cards.forEach((c) => c.assignee && s.add(c.assignee))
    return Array.from(s).sort()
  }, [cards])

  const filtering = !!(query.trim() || filters.project || filters.assignee || filters.priority)
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return cards.filter((c) => {
      if (filters.project && c.project !== filters.project) return false
      if (filters.assignee && c.assignee !== filters.assignee) return false
      if (filters.priority && c.priority !== filters.priority) return false
      if (!q) return true
      return (
        c.title.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        (c.assignee ?? '').toLowerCase().includes(q) ||
        c.project.toLowerCase().includes(q)
      )
    })
  }, [cards, query, filters])

  const allCounts = useMemo(() => {
    const m = Object.fromEntries(COLUMNS.map((c) => [c.id, 0])) as Record<ColumnId, number>
    cards.forEach((c) => (m[c.column] += 1))
    return m
  }, [cards])

  const stats = useMemo(
    () => ({
      open: cards.filter((c) => c.column !== 'done' && c.column !== 'cancelled').length,
      done: allCounts.done,
      cancelled: allCounts.cancelled,
    }),
    [cards, allCounts],
  )

  const selected = useMemo(() => cards.find((c) => c.id === selectedId) ?? null, [cards, selectedId])

  const openCard = useCallback((id: string | null) => {
    setSelectedId(id)
    history.replaceState(null, '', id ? `#${id}` : location.pathname + location.search)
  }, [])

  useEffect(() => {
    const id = location.hash.slice(1)
    if (id) setSelectedId(id)
  }, [])

  const copy = useCallback(
    async (text: string, label: string) => {
      try {
        await navigator.clipboard.writeText(text)
        notify(`${label} copied to clipboard`)
      } catch {
        notify('Clipboard unavailable')
      }
    },
    [notify],
  )

  const openMenu = useCallback((x: number, y: number, items: MenuItem[]) => setMenu({ x, y, items }), [])
  const closeMenu = useCallback(() => setMenu(null), [])

  // No create flow: the tracker backend has no create endpoint yet, so the
  // New/Add/Duplicate affordances are hidden until it does (see README).

  const cardMenu = useCallback(
    (e: React.MouseEvent, card: Card) => {
      openMenu(e.clientX, e.clientY, [
        { kind: 'label', label: card.id },
        { kind: 'item', label: 'Open details', icon: <PanelRight size={14} />, hint: '\u21b5', onSelect: () => openCard(card.id) },
        {
          kind: 'item',
          label: 'Move to',
          icon: <ArrowRight size={14} />,
          children: COLUMNS.map<MenuItem>((c) => ({
            kind: 'item',
            label: c.label,
            checked: card.column === c.id,
            onSelect: () => card.column !== c.id && board.updateCard(card.id, { column: c.id }, `${card.id} moved to ${c.label}`),
          })),
        },
        {
          kind: 'item',
          label: 'Priority',
          icon: <Flag size={14} />,
          children: PRIORITIES.map<MenuItem>((p) => ({
            kind: 'item',
            label: p.label,
            checked: card.priority === p.id,
            onSelect: () => board.updateCard(card.id, { priority: p.id }, `${card.id} priority set to ${p.label.toLowerCase()}`),
          })),
        },
        {
          kind: 'item',
          label: 'Assign to',
          icon: <User size={14} />,
          children: [
            { kind: 'item', label: 'Unassigned', checked: !card.assignee, onSelect: () => board.updateCard(card.id, { assignee: null }, `${card.id} unassigned`) },
            ...assignees.map<MenuItem>((a) => ({
              kind: 'item',
              label: a,
              checked: card.assignee === a,
              onSelect: () => board.updateCard(card.id, { assignee: a }, `${card.id} assigned to ${a}`),
            })),
          ],
        },
        { kind: 'sep' },
        ...(card.column !== 'done'
          ? [{ kind: 'item', label: 'Mark as done', icon: <Check size={14} />, onSelect: () => board.updateCard(card.id, { column: 'done' }, `${card.id} marked as done`) } as MenuItem]
          : []),
        { kind: 'item', label: 'Copy ID', icon: <Copy size={14} />, onSelect: () => copy(card.id, card.id) },
        {
          kind: 'item',
          label: 'Copy link',
          icon: <Link2 size={14} />,
          onSelect: () => copy(`${location.origin}${location.pathname}#${card.id}`, 'Link'),
        },
        { kind: 'sep' },
        {
          // The backend has no DELETE: "delete" cancels the item instead.
          kind: 'item',
          label: 'Cancel item',
          icon: <Trash2 size={14} />,
          danger: true,
          onSelect: () => {
            if (selectedId === card.id) openCard(null)
            board.deleteCard(card.id)
          },
        },
      ])
    },
    [assignees, board, copy, openCard, openMenu, selectedId],
  )

  const columnMenu = useCallback(
    (e: React.MouseEvent, col: ColumnId) => {
      openMenu(e.clientX, e.clientY, [
        { kind: 'label', label: COLUMN_LABEL[col] },
        { kind: 'item', label: 'Sort by priority', icon: <ArrowDownUp size={14} />, onSelect: () => board.sortColumn(col) },
        {
          kind: 'item',
          label: collapsed[col] ? 'Expand column' : 'Collapse column',
          icon: <ChevronsLeftRight size={14} />,
          onSelect: () => setCollapsed((c) => ({ ...c, [col]: !c[col] })),
        },
      ])
    },
    [board, collapsed, openMenu],
  )

  const boardMenu = useCallback(
    (e: React.MouseEvent) => {
      openMenu(e.clientX, e.clientY, [
        { kind: 'item', label: 'Undo', icon: <Undo2 size={14} />, hint: '\u2318Z', disabled: !board.canUndo, onSelect: board.undo },
        { kind: 'sep' },
        {
          kind: 'item',
          label: view === 'board' ? 'Switch to list view' : 'Switch to board view',
          icon: view === 'board' ? <List size={14} /> : <Columns3 size={14} />,
          hint: 'V',
          onSelect: () => setView((v) => (v === 'board' ? 'list' : 'board')),
        },
        {
          kind: 'item',
          label: theme === 'dark' ? 'Light mode' : 'Dark mode',
          icon: theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />,
          hint: 'D',
          onSelect: toggleTheme,
        },
        ...(view === 'board'
          ? [
              { kind: 'sep' } as MenuItem,
              {
                kind: 'item',
                label: 'Expand all columns',
                icon: <ChevronsLeftRight size={14} />,
                onSelect: () => setCollapsed(Object.fromEntries(COLUMNS.map((c) => [c.id, false])) as Record<ColumnId, boolean>),
              } as MenuItem,
            ]
          : []),
      ])
    },
    [board.canUndo, board.undo, openMenu, theme, toggleTheme, view],
  )

  // keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      const typing = el.matches?.('input, textarea, select') || el.isContentEditable
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        if (typing) return
        e.preventDefault()
        board.undo()
        return
      }
      if (e.key === 'Escape') {
        if (settingsOpen) setSettingsOpen(false)
        else if (selectedId) openCard(null)
        return
      }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === '/') {
        e.preventDefault()
        searchRef.current?.focus()
      } else if (e.key === 'd') toggleTheme()
      else if (e.key === 'v') setView((v) => (v === 'board' ? 'list' : 'board'))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [board, openCard, selectedId, settingsOpen, toggleTheme])

  return (
    <div className="flex h-full flex-col">
      <Header
        stats={stats}
        query={query}
        setQuery={setQuery}
        searchRef={searchRef}
        filters={filters}
        setFilters={setFilters}
        projects={projects}
        assignees={assignees}
        view={view}
        setView={setView}
        theme={theme}
        toggleTheme={toggleTheme}
        onSettings={() => setSettingsOpen(true)}
        status={board.status}
        syncedAt={board.syncedAt}
        onRefresh={() => board.refresh()}
        openMenu={openMenu}
      />

      <main className="min-h-0 flex-1 border-t border-line pt-3">
        {view === 'board' ? (
          <Board
            cards={filtered}
            allCounts={allCounts}
            filtering={filtering}
            collapsed={collapsed}
            onToggle={(col) => setCollapsed((c) => ({ ...c, [col]: !c[col] }))}
            onOpen={(card) => openCard(card.id)}
            onMove={board.moveCard}
            onCardMenu={cardMenu}
            onColumnMenu={columnMenu}
            onBoardMenu={boardMenu}
            onCopyId={(id) => copy(id, id)}
            selectedId={selectedId}
          />
        ) : (
          <ListView
            cards={filtered}
            selectedId={selectedId}
            onOpen={(card) => openCard(card.id)}
            onCardMenu={cardMenu}
            onColumnMenu={columnMenu}
            onBoardMenu={boardMenu}
          />
        )}
      </main>

      <AnimatePresence>
        {selected && (
          <Drawer
            key={selected.id}
            card={selected}
            assignees={assignees}
            onClose={() => openCard(null)}
            onUpdate={(patch, message) => board.updateCard(selected.id, patch, message)}
            onDelete={() => {
              openCard(null)
              board.deleteCard(selected.id)
            }}
            onCopy={copy}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {settingsOpen && (
          <Settings
            status={board.status}
            error={board.error}
            generatedAt={board.generatedAt}
            cards={cards}
            onClose={() => setSettingsOpen(false)}
            onRefresh={() => board.refresh()}
          />
        )}
      </AnimatePresence>

      {menu && <ContextMenu key={`${menu.x}-${menu.y}`} x={menu.x} y={menu.y} items={menu.items} onClose={closeMenu} />}

      <Toast
        toast={toast}
        onUndo={() => {
          board.undo()
          setToast(null)
        }}
      />
    </div>
  )
}
