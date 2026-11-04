import { useState } from 'react'
import { Button, Dialog, EmptyState, TextField } from '@dsect/ui'
import type { Suggestion, TrackerItem } from '../types'
import { fmtDateTime } from '../lib/meta'

const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : Array.isArray(v) ? v.join(', ') : String(v))

export function SuggestionsInbox({ open, onClose, suggestions, byId, phone, onAccept, onReject, onOpenItem }: {
  open: boolean; onClose: () => void; suggestions: Suggestion[]; byId: Map<string, TrackerItem>; phone: boolean
  onAccept: (id: string) => Promise<void>; onReject: (id: string, reason?: string) => Promise<void>; onOpenItem: (id: string) => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const run = async (id: string, f: () => Promise<void>) => { setBusy(id); try { await f() } finally { setBusy(null) } }
  return (
    <Dialog open={open} onClose={onClose} variant={phone ? 'sheet' : 'drawer'} title={`Suggestions inbox (${suggestions.length})`} closeLabel="Close suggestions" className="tb-inbox">
      <p className="tb-muted">Changes made on GitHub wait here until a person accepts or rejects them.</p>
      {suggestions.length === 0 ? <EmptyState title="Inbox zero" text="No pending GitHub suggestions." inline /> : (
        <ul className="tb-plain tb-sugs">
          {suggestions.map((s) => {
            const it = byId.get(s.itemId)
            return (
              <li key={s.id} className="card tb-sug">
                <div className="tb-sug-head">
                  <button type="button" className="tb-linkbtn" onClick={() => onOpenItem(s.itemId)}><span className="tb-id">{s.itemId}</span> {it?.title ?? ''}</button>
                  <span className="tb-muted">{s.id} · {fmtDateTime(s.createdAt)}{s.remoteActor ? ` · ${s.remoteActor}` : ''}</span>
                </div>
                <p><strong>{s.field}</strong>: <del>{show(s.currentValue)}</del> → <ins>{show(s.proposedValue)}</ins></p>
                {s.reason && <p className="tb-muted">{s.reason}</p>}
                {rejecting === s.id ? (
                  <div className="tb-sug-actions">
                    <TextField label="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
                    <Button size="sm" variant="outline" onClick={() => setRejecting(null)}>Cancel</Button>
                    <Button size="sm" disabled={busy === s.id} onClick={() => run(s.id, async () => { await onReject(s.id, reason || undefined); setRejecting(null); setReason('') })}>Confirm reject</Button>
                  </div>
                ) : (
                  <div className="tb-sug-actions">
                    <Button size="sm" disabled={busy === s.id} onClick={() => run(s.id, () => onAccept(s.id))}>Accept {s.id}</Button>
                    <Button size="sm" variant="outline" disabled={busy === s.id} onClick={() => setRejecting(s.id)}>Reject {s.id}</Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Dialog>
  )
}
