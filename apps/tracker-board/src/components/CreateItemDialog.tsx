// Create-item dialog (modal on desktop, bottom sheet on phones). POST /api/items via the client.
import { useEffect, useRef, useState } from 'react'
import { Button, Dialog, SelectField, TextArea, TextField } from '@dsect/ui'
import type { Label, Person, Priority, Status, TrackerItem } from '../types'
import type { ItemPatch } from '../lib/api'
import { PRIORITIES, STATUSES, priorityLabel, statusLabel } from '../lib/meta'

export type CreateInput = ItemPatch & { title: string }

export function CreateItemDialog({ open, initialStatus, onClose, onCreate, people, labels, items, phone }: {
  open: boolean; initialStatus: Status; onClose: () => void; onCreate: (input: CreateInput) => Promise<boolean>
  people: Person[]; labels: Label[]; items: TrackerItem[]; phone: boolean
}) {
  const [title, setTitle] = useState('')
  const [status, setStatus] = useState<Status>(initialStatus)
  const [priority, setPriority] = useState<Priority>('none')
  const [assigneeId, setAssignee] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [parentId, setParent] = useState('')
  const [body, setBody] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const titleRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset the form each time the dialog opens
    setTitle(''); setStatus(initialStatus); setPriority('none'); setAssignee(''); setPicked([]); setParent(''); setBody(''); setError(null); setBusy(false)
    const t = window.setTimeout(() => titleRef.current?.focus(), 30)
    return () => window.clearTimeout(t)
  }, [open, initialStatus])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) { setError('Title is required'); titleRef.current?.focus(); return }
    setBusy(true)
    const ok = await onCreate({ title: title.trim(), status, priority, assigneeId: assigneeId || null, labels: picked, parentId: parentId || null, body })
    setBusy(false)
    if (!ok) titleRef.current?.focus()
  }

  return (
    <Dialog open={open} onClose={onClose} variant={phone ? 'sheet' : 'modal'} title="New item" closeLabel="Close new item" className="tb-create">
      <form className="tb-create-form" onSubmit={submit} noValidate aria-busy={busy}>
        <TextField ref={titleRef} label="Title (required)" value={title} required aria-required="true" error={error ?? undefined}
          onChange={(e) => { setTitle(e.target.value); if (error) setError(null) }} />
        <div className="tb-create-row">
          <SelectField label="Status" value={status} onChange={(e) => setStatus(e.target.value as Status)}>
            {STATUSES.map((s) => <option key={s} value={s}>{statusLabel[s]}</option>)}
          </SelectField>
          <SelectField label="Priority" value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
            {PRIORITIES.map((p) => <option key={p} value={p}>{priorityLabel[p]}</option>)}
          </SelectField>
          <SelectField label="Assignee" value={assigneeId} onChange={(e) => setAssignee(e.target.value)}>
            <option value="">Unassigned</option>
            {people.filter((p) => p.active !== false).map((p) => <option key={p.id} value={p.id}>{p.display}</option>)}
          </SelectField>
        </div>
        <fieldset className="tb-create-labels">
          <legend className="text-label">Labels</legend>
          {labels.length === 0 && <span className="tb-muted">No labels yet</span>}
          {labels.map((l) => (
            <label key={l.name} className="tb-check">
              <input type="checkbox" checked={picked.includes(l.name)}
                onChange={(e) => setPicked((x) => e.target.checked ? [...x, l.name] : x.filter((y) => y !== l.name))} />
              {l.name}
            </label>
          ))}
        </fieldset>
        <SelectField label="Parent" value={parentId} onChange={(e) => setParent(e.target.value)}>
          <option value="">No parent</option>
          {items.map((i) => <option key={i.id} value={i.id}>{i.id} · {i.title.slice(0, 60)}</option>)}
        </SelectField>
        <TextArea label="Description" rows={4} value={body} onChange={(e) => setBody(e.target.value)} />
        <div className="tb-create-actions">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create item'}</Button>
        </div>
      </form>
    </Dialog>
  )
}
