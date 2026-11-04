import { useCallback, useEffect, useMemo, useState } from 'react'
import { AppBar, Button, FilterBar, FilterBarActions, FilterSelect, SearchInput, Tabs, Toaster, getTheme, setTheme, type ToastData } from '@dsect/ui'
import type { Label, Person, Status, Suggestion, TrackerItem } from './types'
import { createClient, type ItemPatch, type TrackerClient } from './lib/api'
import { PRIORITIES, STATUSES, priorityLabel, projectOf, statusLabel, setLabelColors } from './lib/meta'
import { applyFilters, chipsFor, emptyFilters, fromQuery, removeChip, toQuery, type A2AMode, type Filters } from './lib/filters'
import { MultiSelect } from './components/MultiSelect'
import { SummaryStrip } from './components/SummaryStrip'
import { Board } from './components/Board'
import { ListView } from './components/ListView'
import { ProjectsView, type ProjectGroup } from './components/ProjectsView'
import { DetailPanel } from './components/DetailPanel'
import { SuggestionsInbox } from './components/SuggestionsInbox'

type View = 'board' | 'list' | 'projects'
const parseHash = () => {
  const [path, q = ''] = location.hash.replace(/^#\/?/, '').split('?')
  const [view, item] = path.split('/')
  return { view: (['board', 'list', 'projects'].includes(view) ? view : 'board') as View, item: item || null, filters: fromQuery(q) }
}
function usePhone() {
  const [p, setP] = useState(() => matchMedia('(max-width: 720px)').matches)
  useEffect(() => { const m = matchMedia('(max-width: 720px)'); const f = () => setP(m.matches); m.addEventListener('change', f); return () => m.removeEventListener('change', f) }, [])
  return p
}

export default function App() {
  const [init] = useState(parseHash)
  const [client, setClient] = useState<TrackerClient | null>(null)
  const [items, setItems] = useState<TrackerItem[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [labels, setLabels] = useState<Label[]>([])
  const [sugs, setSugs] = useState<Suggestion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<View>(init.view)
  const [filters, setFilters] = useState<Filters>(init.filters)
  const [openId, setOpenId] = useState<string | null>(init.item)
  const [inbox, setInbox] = useState(false)
  const [toasts, setToasts] = useState<ToastData[]>([])
  const [theme, setThemeState] = useState(getTheme())
  const phone = usePhone()
  const toast = (t: Omit<ToastData, 'id'>) => { const id = String(Math.random()); setToasts((x) => [...x, { ...t, id }]); setTimeout(() => setToasts((x) => x.filter((y) => y.id !== id)), 4000) }

  const refresh = useCallback(async (c: TrackerClient) => {
    const [i, p, l, s] = await Promise.all([c.listItems(), c.listPeople(), c.listLabels(), c.listSuggestions()])
    setItems(i); setPeople(p); setLabelColors(l); setLabels(l); setSugs(s)
  }, [])
  useEffect(() => {
    createClient().then(async (c) => { setClient(c); await refresh(c) }).catch((e) => setError(String(e.message ?? e))).finally(() => setLoading(false))
  }, [refresh])
  useEffect(() => {
    const q = toQuery(filters)
    const h = `#/${view}${openId ? `/${openId}` : ''}${q ? `?${q}` : ''}`
    if (location.hash !== h) history.replaceState(null, '', h)
  }, [view, filters, openId])

  const byId = useMemo(() => new Map(items.map((i) => [i.id, i])), [items])
  const peopleMap = useMemo(() => new Map(people.map((p) => [p.id, p])), [people])
  const shown = useMemo(() => applyFilters(items, filters, byId), [items, filters, byId])
  const projects = useMemo(() => {
    const m = new Map<string, { id: string; title: string }>()
    items.forEach((i) => { const p = projectOf(i, byId); if (p) m.set(p.id, p) })
    return [...m.values()].sort((a, b) => a.id.localeCompare(b.id))
  }, [items, byId])
  const projectName = (i: TrackerItem) => projectOf(i, byId)?.id ?? '—'
  const groups: ProjectGroup[] = useMemo(() => {
    const g = new Map<string, ProjectGroup>()
    for (const i of shown) {
      const p = projectOf(i, byId) ?? (items.some((x) => x.parentId === i.id) ? { id: i.id, title: i.title } : { id: '__none', title: 'No project' })
      if (!g.has(p.id)) g.set(p.id, { id: p.id, title: p.id === '__none' ? p.title : `${p.id} · ${p.title}`, items: [] })
      g.get(p.id)!.items.push(i)
    }
    return [...g.values()].sort((a, b) => (a.id === '__none' ? 1 : b.id === '__none' ? -1 : a.id.localeCompare(b.id)))
  }, [shown, byId, items])

  const save = async (id: string, patch: ItemPatch) => {
    if (!client) return
    const prev = items
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...patch } : x)))
    try {
      const it = await client.updateItem(id, patch)
      setItems((xs) => xs.map((x) => (x.id === id ? it : x)))
      toast({ title: `${id} updated`, tone: 'ok' })
    } catch (e) { setItems(prev); toast({ title: `Could not update ${id}`, text: String((e as Error).message), tone: 'err' }) }
  }
  const move = (id: string, to: Status) => { const it = byId.get(id); if (it && it.status !== to) void save(id, { status: to }) }
  const decide = async (id: string, accept: boolean, reason?: string) => {
    if (!client) return
    try {
      if (accept) await client.acceptSuggestion(id); else await client.rejectSuggestion(id, reason)
      toast({ title: `${id} ${accept ? 'accepted' : 'rejected'}`, tone: 'ok' })
      await refresh(client)
    } catch (e) { toast({ title: `Could not ${accept ? 'accept' : 'reject'} ${id}`, text: String((e as Error).message), tone: 'err' }) }
  }

  const count = (pred: (i: TrackerItem) => boolean) => items.filter(pred).length
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }))
  const chips = chipsFor(filters, (k, v) => (v === '__none' ? (k === 'assignee' ? 'Unassigned' : 'No project') : k === 'assignee' ? peopleMap.get(v)?.display ?? v : v))
  const flagFilter = (f: 'stale' | 'needs_triage' | 'blocked' | 'sync') => {
    if (f === 'blocked') set('status', ['blocked'])
    else if (f === 'sync') setInbox(true)
    else set('flags', filters.flags.includes(f) ? filters.flags : [...filters.flags, f])
  }

  const panel = (node: React.ReactNode) => (loading ? <p className="tb-empty" role="status">Loading tracker…</p> : error ? <p role="alert" className="tb-error">Could not load tracker: {error}</p> : node)
  return (
    <div className="tb-app">
      <a href="#main" className="tb-skip">Skip to content</a>
      <AppBar title="Tracker" subtitle={client ? (client.source === 'api' ? 'Live: tracker-api' : 'Offline: fixture data') : 'Connecting…'}
        actions={<>
          <Button variant="outline" size="sm" onClick={() => setInbox(true)} aria-label={`Suggestions inbox, ${sugs.length} pending`}>
            Inbox <span className="tb-count tb-count--pill" aria-hidden="true">{sugs.length}</span>
          </Button>
          <Button variant="ghost" onClick={() => { const t = theme === 'dark' ? 'light' : 'dark'; setTheme(t); setThemeState(t); try { localStorage.setItem('tracker.theme', t) } catch { /* ignore */ } }}>
            {theme === 'dark' ? 'Light theme' : 'Dark theme'}
          </Button>
        </>} />
      <main id="main" className="tb-main">
        <div className="tb-filterbar"><FilterBar applied={[]} aria-label="Filter items">
          <SearchInput aria-label="Search items" placeholder="Search ID, title, label…" value={filters.q} onChange={(e) => set('q', e.target.value)} className="tb-search" />
          <MultiSelect label="Status" value={filters.status} onChange={(v) => set('status', v as Status[])}
            options={STATUSES.map((s) => ({ value: s, label: statusLabel[s], count: count((i) => i.status === s) }))} />
          <MultiSelect label="Priority" value={filters.priority} onChange={(v) => set('priority', v as Filters['priority'])}
            options={PRIORITIES.map((p) => ({ value: p, label: priorityLabel[p], count: count((i) => i.priority === p) }))} />
          <MultiSelect label="Assignee" value={filters.assignee} onChange={(v) => set('assignee', v)}
            options={[{ value: '__none', label: 'Unassigned', count: count((i) => !i.assigneeId) }, ...people.map((p) => ({ value: p.id, label: p.display, count: count((i) => i.assigneeId === p.id) }))]} />
          <MultiSelect label="Labels" value={filters.labels} onChange={(v) => set('labels', v)}
            options={labels.map((l) => ({ value: l.name, label: l.name, count: count((i) => i.labels.includes(l.name)) }))} />
          <MultiSelect label="Project" value={filters.project} onChange={(v) => set('project', v)}
            options={[...projects.map((p) => ({ value: p.id, label: `${p.id} · ${p.title}` })), { value: '__none', label: 'No project' }]} />
          <MultiSelect label="Flags" value={filters.flags} onChange={(v) => set('flags', v as Filters['flags'])}
            options={[{ value: 'stale', label: 'Stale', count: count((i) => i.stale) }, { value: 'needs_triage', label: 'Needs triage', count: count((i) => i.needsTriage) }]} />
          <FilterBarActions>
            <label className="tb-inline-label">Automated (A2A)
              <FilterSelect value={filters.a2a} onChange={(e) => set('a2a', e.target.value as A2AMode)}>
                <option value="group">Group</option><option value="show">Show inline</option><option value="hide">Hide</option>
              </FilterSelect>
            </label>
          </FilterBarActions>
        </FilterBar></div>
        {chips.length > 0 && (
          <div className="filterbar__applied tb-chips" aria-label="Applied filters" role="group">
            {chips.map((c) => <span key={c.id} className="filter-chip">{c.label}
              <button type="button" aria-label={`Remove filter ${c.label}`} onClick={() => setFilters((f) => removeChip(f, c.id))}>×</button></span>)}
            <button type="button" className="filterbar__clear" onClick={() => setFilters({ ...emptyFilters, a2a: filters.a2a })}>Clear all</button>
          </div>
        )}
        <SummaryStrip items={shown} onFlag={flagFilter} />
        <p className="sr-only" role="status" aria-live="polite">{loading ? '' : `${shown.length} of ${items.length} items shown`}</p>
        <Tabs label="Tracker views" value={view} onChange={(v) => setView(v as View)} className="tb-tabs" tabs={[
          { id: 'board', label: `Board · ${shown.length}`, panel: panel(<Board items={shown} people={peopleMap} a2a={filters.a2a} onOpen={setOpenId} onMove={move} />) },
          { id: 'list', label: 'List', panel: panel(<ListView items={shown} people={peopleMap} a2a={filters.a2a} onOpen={setOpenId} projectName={projectName} />) },
          { id: 'projects', label: `Projects · ${groups.length}`, panel: panel(<ProjectsView groups={groups} onOpen={setOpenId} onFilter={(p) => { set('project', [p]); setView('board') }} />) },
        ]} />
      </main>
      {client && <DetailPanel id={openId} load={client.getItem.bind(client)} byId={byId} people={peopleMap} phone={phone}
        onClose={() => setOpenId(null)} onOpen={setOpenId} onSave={save} />}
      <SuggestionsInbox open={inbox} onClose={() => setInbox(false)} suggestions={sugs} byId={byId} phone={phone}
        onAccept={(id) => decide(id, true)} onReject={(id, r) => decide(id, false, r)} onOpenItem={(id) => { setInbox(false); setOpenId(id) }} />
      <Toaster toasts={toasts} onDismiss={(id) => setToasts((x) => x.filter((t) => t.id !== id))} />
    </div>
  )
}
