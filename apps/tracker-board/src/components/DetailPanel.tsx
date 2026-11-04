import { useEffect, useState } from 'react'
import { Button, Dialog, KeyValue, SelectField, Spinner } from '@dsect/ui'
import type { ItemDetail, Person, Priority, Status, TrackerItem } from '../types'
import type { ItemPatch } from '../lib/api'
import { PRIORITIES, STATUSES, fmtDate, fmtDateTime, priorityLabel, statusLabel, syncLabel } from '../lib/meta'
import { FlagBadges, GitHubBadge, PriorityBadge } from './Badges'

const relLabel = (rel: string, dir: 'in' | 'out') =>
  rel === 'parent' ? (dir === 'out' ? 'Parent of' : 'Child of') : rel === 'blocks' ? (dir === 'out' ? 'Blocks' : 'Blocked by') : `${rel.replace(/_/g, ' ')} (${dir})`

export function DetailPanel({ id, load, byId, people, phone, onClose, onOpen, onSave }: {
  id: string | null; load: (id: string) => Promise<ItemDetail>; byId: Map<string, TrackerItem>; people: Map<string, Person>
  phone: boolean; onClose: () => void; onOpen: (id: string) => void; onSave: (id: string, p: ItemPatch) => Promise<void>
}) {
  const [d, setD] = useState<ItemDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<ItemPatch>({})
  const [saving, setSaving] = useState(false)
  const cached = id ? byId.get(id) : undefined
  // Make the scrollable dialog body keyboard-reachable (axe scrollable-region-focusable).
  useEffect(() => {
    if (!id) return
    const t = window.setTimeout(() => {
      const b = document.querySelector<HTMLElement>('.tb-detail .dialog__body')
      if (b && !b.hasAttribute('tabindex')) { b.tabIndex = 0; b.setAttribute('aria-label', `${id} details`) }
    }, 0)
    return () => window.clearTimeout(t)
  })
  useEffect(() => {
    if (!id) return
    let live = true
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before fetching a new item id
    setD(null); setErr(null); setEditing(false)
    load(id).then((x) => live && setD(x)).catch((e) => live && setErr(String(e.message ?? e)))
    return () => { live = false }
  }, [id, load, cached?.updatedAt])
  const it = d?.item ?? cached
  const who = (h: string | null | undefined) => (h ? people.get(h)?.display ?? h : '—')
  return (
    <Dialog open={!!id} onClose={onClose} variant={phone ? 'sheet' : 'drawer'} className="tb-detail"
      closeLabel="Close details"
      title={it ? <><span className="tb-id">{it.id}</span> {it.title}</> : 'Loading item'}
      footer={it && (editing ? (
        <>
          <Button variant="outline" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
          <Button size="sm" disabled={saving || !Object.keys(draft).length} onClick={async () => {
            setSaving(true); try { await onSave(it.id, draft); setEditing(false) } finally { setSaving(false) }
          }}>{saving ? 'Saving…' : 'Save changes'}</Button>
        </>
      ) : <Button variant="outline" size="sm" onClick={() => { setDraft({}); setEditing(true) }}>Edit status, priority or assignee</Button>)}>
      {!it && !err && <Spinner />}
      {err && <p role="alert" className="tb-error">Could not load details: {err}</p>}
      {it && (
        <div className="tb-detail-body">
          <div className="tb-detail-badges">
            <span className="tb-status-pill">{statusLabel[it.status]}</span>
            <PriorityBadge p={it.priority} /><span className="tb-kind">{it.kind}</span><FlagBadges item={it} />
          </div>
          {editing && (
            <fieldset className="tb-edit">
              <legend className="sr-only">Edit item</legend>
              <SelectField label="Status" defaultValue={it.status} onChange={(e) => setDraft((x) => ({ ...x, status: e.target.value as Status }))}>
                {STATUSES.map((s) => <option key={s} value={s}>{statusLabel[s]}</option>)}
              </SelectField>
              <SelectField label="Priority" defaultValue={it.priority} onChange={(e) => setDraft((x) => ({ ...x, priority: e.target.value as Priority }))}>
                {PRIORITIES.map((p) => <option key={p} value={p}>{priorityLabel[p]}</option>)}
              </SelectField>
              <SelectField label="Assignee" defaultValue={it.assigneeId ?? ''} onChange={(e) => setDraft((x) => ({ ...x, assigneeId: e.target.value || null }))}>
                <option value="">Unassigned</option>
                {[...people.values()].map((p) => <option key={p.id} value={p.id}>{p.display}</option>)}
              </SelectField>
            </fieldset>
          )}
          <KeyValue items={[
            { label: 'Assignee', value: who(it.assigneeId) },
            { label: 'Labels', value: it.labels.length ? it.labels.join(', ') : '—' },
            { label: 'Due', value: fmtDate(it.dueAt) },
            { label: 'Points', value: it.points ?? '—', numeric: true },
            { label: 'Created', value: fmtDateTime(it.createdAt) },
            { label: 'Updated', value: fmtDateTime(it.updatedAt) },
          ]} />
          {it.body && <section aria-labelledby="sec-desc"><h3 id="sec-desc" className="tb-sec">Description</h3><p className="tb-bodytext">{it.body}</p></section>}

          <section aria-labelledby="sec-links"><h3 id="sec-links" className="tb-sec">Links</h3>
            {(d?.links.length || it.github) ? (
              <ul className="tb-plain">
                {it.github && <li><a href={it.github.url} target="_blank" rel="noreferrer">{it.github.repo}#{it.github.number}</a> ({it.github.type === 'pull_request' ? 'pull request' : 'issue'})</li>}
                {d?.links.map((l, n) => <li key={n}><a href={l.target} target="_blank" rel="noreferrer">{l.label || l.target}</a> <span className="tb-muted">{l.kind}</span></li>)}
              </ul>) : <p className="tb-muted">No links.</p>}
          </section>

          <section aria-labelledby="sec-sync"><h3 id="sec-sync" className="tb-sec">Sync</h3>
            {it.github ? <>
              <p><GitHubBadge github={d?.githubLink ?? it.github} sync={it.sync} /></p>
              <KeyValue items={[
                { label: 'State', value: syncLabel[it.sync.state] },
                { label: 'Last synced', value: fmtDateTime(it.sync.lastSyncedAt) },
                { label: 'Remote updated', value: fmtDateTime((d?.githubLink ?? it.github).remoteUpdatedAt) },
                ...(it.sync.pendingSuggestionId ? [{ label: 'Suggestion', value: it.sync.pendingSuggestionId }] : []),
                ...(it.sync.error ? [{ label: 'Error', value: it.sync.error }] : []),
              ]} />
            </> : <p className="tb-muted">Not linked to GitHub.</p>}
          </section>

          <section aria-labelledby="sec-rel"><h3 id="sec-rel" className="tb-sec">Relations</h3>
            {d?.relations.length ? (
              <ul className="tb-plain">{d.relations.map((r, n) => {
                const o = byId.get(r.itemId)
                return <li key={n}><span className="tb-muted">{relLabel(r.rel, r.direction)}</span>{' '}
                  <button type="button" className="tb-linkbtn" onClick={() => onOpen(r.itemId)}>{r.itemId}{o ? ` · ${o.title}` : ''}</button>
                  {o && <span className="tb-muted"> ({statusLabel[o.status]})</span>}</li>
              })}</ul>) : <p className="tb-muted">{d ? 'No relations.' : 'Loading…'}</p>}
          </section>

          <section aria-labelledby="sec-hist"><h3 id="sec-hist" className="tb-sec">History</h3>
            <ol className="tb-plain">
              {d?.statusHistory.map((h, n) => <li key={n}>{fmtDateTime(h.at)}: {h.fromStatus ? `${statusLabel[h.fromStatus]} → ` : 'Created as '}{statusLabel[h.toStatus]} <span className="tb-muted">by {who(h.actor)}{h.source ? ` via ${h.source}` : ''}</span></li>)}
              {d?.changes.map((c, n) => <li key={`c${n}`}>{fmtDateTime(c.at)}: {c.body} <span className="tb-muted">by {who(c.actor)}</span></li>)}
            </ol>
          </section>

          <section aria-labelledby="sec-com"><h3 id="sec-com" className="tb-sec">Comments ({d?.comments.length ?? 0})</h3>
            {d?.comments.length ? <ul className="tb-plain">{d.comments.map((c) => <li key={c.id}><strong>{who(c.actor)}</strong> <span className="tb-muted">{fmtDateTime(c.at)}</span><p>{c.body}</p></li>)}</ul>
              : <p className="tb-muted">No comments.</p>}
          </section>
        </div>
      )}
    </Dialog>
  )
}
