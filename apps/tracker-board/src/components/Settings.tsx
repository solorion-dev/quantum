import { motion } from 'framer-motion'
import { Download, RefreshCw, X } from 'lucide-react'
import { cn } from '../lib/cn'
import { dateTimeLabel } from '../lib/format'
import type { SyncStatus } from '../lib/api'
import type { Card } from '../types'

interface Props {
  status: SyncStatus
  error: string | null
  generatedAt: string | null
  cards: Card[]
  onClose: () => void
  onRefresh: () => void
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <span className="shrink-0 text-[10.5px] font-semibold uppercase leading-5 tracking-[0.14em] text-fg-faint">{label}</span>
      <span className="text-right text-[12.5px] leading-relaxed text-fg-muted">{children}</span>
    </div>
  )
}

export function Settings({ status, error, generatedAt, cards, onClose, onRefresh }: Props) {
  const exportJson = () => {
    const blob = new Blob([JSON.stringify(cards, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `tracker-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const snapshotTime = generatedAt ? Date.parse(generatedAt) : NaN

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-fg/20 backdrop-blur-sm"
      />
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        className="relative w-full max-w-md rounded-2xl border border-line bg-bg p-6 shadow-2xl"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight">Server &amp; data</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-fg-muted hover:bg-subtle hover:text-fg">
            <X size={16} />
          </button>
        </div>
        <p className="mt-1.5 text-[13px] leading-relaxed text-fg-muted">
          This board is wired to the Quantum tracker backend — there is nothing to configure here. The list loads from a
          snapshot of the live Tracker DB; card details and edits go to the tracker board service.
        </p>

        <div className="mt-4 divide-y divide-line border-y border-line">
          <InfoRow label="Data source">
            Board snapshot
            {!Number.isNaN(snapshotTime) && (
              <>
                <br />
                generated {dateTimeLabel(snapshotTime)}
              </>
            )}
          </InfoRow>
          <InfoRow label="Item service">
            Tracker board service · port 7654
            <br />
            via the <code className="font-mono text-[12px] text-fg">/api</code> proxy
          </InfoRow>
          <InfoRow label="Cards loaded">{cards.length}</InfoRow>
        </div>

        <div className="mt-3 flex items-center gap-2 text-[12px] text-fg-muted">
          <span className={cn('h-1.5 w-1.5 rounded-full', status === 'offline' ? 'ring-1 ring-fg' : 'bg-fg')} />
          {status === 'syncing' && 'Syncing…'}
          {status === 'live' && 'Connected'}
          {status === 'offline' && (error ?? 'Could not reach the server')}
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <button
            onClick={onRefresh}
            className="flex h-9 items-center gap-2 rounded-lg bg-fg px-4 text-[13px] font-medium text-bg transition-opacity hover:opacity-90 active:scale-95"
          >
            <RefreshCw size={13} /> Sync now
          </button>
          <button
            onClick={exportJson}
            className="flex h-9 items-center gap-2 rounded-lg border border-line px-3 text-[13px] hover:border-line-strong active:scale-95"
          >
            <Download size={13} /> Export JSON
          </button>
        </div>
      </motion.div>
    </div>
  )
}
