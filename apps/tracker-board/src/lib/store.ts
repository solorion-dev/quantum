import { useCallback, useEffect, useRef, useState } from 'react'
import type { Card, ColumnId } from '../types'
import { COLUMN_LABEL } from '../types'
import { backendFieldsOf, COLUMN_TO_STATUS, isStale, loadSnapshot, patchToUpdate, updateItem } from './api'
import type { ItemUpdate, SyncStatus } from './api'

// The board's data layer, wired to the real tracker backend:
//   - list:   /board-data.json snapshot of the live Tracker DB
//   - edits:  POST /api/item/<id>/update (whitelist) via the vite /api proxy
//   - delete: a soft delete — POST update { status: 'cancelled' }
// There is no create endpoint on the backend, so the store has no addCard:
// the create affordances are hidden in the UI until the backend grows one.
// localStorage caches ONLY the last real snapshot (never local inventions),
// so a reload shows real data fast and an unreachable snapshot shows an
// honest error instead of demo data.
const CACHE_KEY = 'tracker.cards.v2'

interface Cache {
  cards: Card[]
  generatedAt: string
}

function loadCache(): Cache | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Cache
    if (!Array.isArray(parsed.cards) || !parsed.cards.length) return null
    return parsed
  } catch {
    return null
  }
}

function saveCache(cache: Cache) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(cache))
  } catch {
    /* ignore */
  }
}

export type Notify = (message: string, undoable?: boolean) => void

export function useBoard(notify: Notify) {
  const cached = useRef<Cache | null | undefined>(undefined)
  if (cached.current === undefined) cached.current = loadCache()

  const [cards, setCards] = useState<Card[]>(() => cached.current?.cards ?? [])
  const [generatedAt, setGeneratedAt] = useState<string | null>(() => cached.current?.generatedAt ?? null)
  const [status, setStatus] = useState<SyncStatus>('syncing')
  const [syncedAt, setSyncedAt] = useState(Date.now())
  const [error, setError] = useState<string | null>(null)

  const cardsRef = useRef(cards)
  const generatedAtRef = useRef(generatedAt)
  const history = useRef<Card[][]>([])
  const [historyLen, setHistoryLen] = useState(0)
  const notifyRef = useRef(notify)
  useEffect(() => {
    notifyRef.current = notify
  })

  const applyCards = useCallback((next: Card[], cacheIt: boolean) => {
    cardsRef.current = next
    setCards(next)
    if (cacheIt) saveCache({ cards: next, generatedAt: generatedAtRef.current ?? '' })
  }, [])

  const refresh = useCallback(async () => {
    setStatus('syncing')
    try {
      const snap = await loadSnapshot()
      generatedAtRef.current = snap.generatedAt
      setGeneratedAt(snap.generatedAt)
      applyCards(snap.cards, true)
      history.current = []
      setHistoryLen(0)
      setStatus('live')
      setError(null)
      setSyncedAt(Date.now())
    } catch (e) {
      setStatus('offline')
      setError(e instanceof Error ? e.message : 'Could not load the board snapshot')
    }
  }, [applyCards])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const pushHistory = useCallback(() => {
    history.current.push(cardsRef.current)
    if (history.current.length > 40) history.current.shift()
    setHistoryLen(history.current.length)
  }, [])

  /**
   * Apply an edit optimistically, then persist it with one POST /update.
   * On failure the board rolls back to the pre-edit state and says so.
   */
  const commitEdit = useCallback(
    (next: Card[], id: string, fields: ItemUpdate, message?: string) => {
      const prev = cardsRef.current
      pushHistory()
      applyCards(next, false)
      if (message) notifyRef.current(message, true)
      if (!Object.keys(fields).length) return
      setStatus('syncing')
      updateItem(id, fields)
        .then((row) => {
          // Trust the server's updated_at; keep everything else as edited.
          const serverTs = typeof row.updated_at === 'string' ? Date.parse(row.updated_at) : NaN
          const merged = cardsRef.current.map((c) =>
            c.id === id && !Number.isNaN(serverTs)
              ? { ...c, updatedAt: serverTs, stale: isStale(c.column, serverTs) }
              : c,
          )
          applyCards(merged, true)
          setStatus('live')
          setError(null)
          setSyncedAt(Date.now())
        })
        .catch((e: Error) => {
          applyCards(prev, false)
          setStatus('offline')
          setError(e.message)
          notifyRef.current(`Save failed — ${e.message}`)
        })
    },
    [applyCards, pushHistory],
  )

  const moveCard = useCallback(
    (id: string, col: ColumnId, beforeId: string | null) => {
      const cur = cardsRef.current
      const card = cur.find((c) => c.id === id)
      if (!card) return
      const rest = cur.filter((c) => c.id !== id)
      const moved: Card = { ...card, column: col, updatedAt: Date.now(), stale: isStale(col, Date.now()) }
      let idx = beforeId ? rest.findIndex((c) => c.id === beforeId) : -1
      if (idx < 0) {
        let last = -1
        rest.forEach((c, i) => {
          if (c.column === col) last = i
        })
        idx = last === -1 ? rest.length : last + 1
      }
      const next = [...rest.slice(0, idx), moved, ...rest.slice(idx)]
      const sameOrder = next.every((c, i) => c.id === cur[i].id)
      if (sameOrder && card.column === col) return
      if (card.column === col) {
        // Pure reorder: order is not persisted by the backend — drop silently.
        pushHistory()
        applyCards(next, false)
        return
      }
      commitEdit(next, id, { status: COLUMN_TO_STATUS[col] }, `${id} moved to ${COLUMN_LABEL[col]}`)
    },
    [applyCards, commitEdit, pushHistory],
  )

  const updateCard = useCallback(
    (id: string, patch: Partial<Card>, message?: string) => {
      const cur = cardsRef.current
      const card = cur.find((c) => c.id === id)
      if (!card) return
      const fields = patchToUpdate(patch)
      const merged: Card = { ...card, ...patch, updatedAt: Date.now() }
      merged.stale = isStale(merged.column, merged.updatedAt)
      if (patch.column && patch.column !== card.column) {
        // moving through a patch -> place at the top of the new column
        const rest = cur.filter((c) => c.id !== id)
        const first = rest.findIndex((c) => c.column === patch.column)
        const idx = first === -1 ? rest.length : first
        commitEdit([...rest.slice(0, idx), merged, ...rest.slice(idx)], id, fields, message)
        return
      }
      commitEdit(
        cur.map((c) => (c.id === id ? merged : c)),
        id,
        fields,
        message,
      )
    },
    [commitEdit],
  )

  /** Soft delete: the backend has no DELETE — the item is cancelled instead. */
  const deleteCard = useCallback(
    (id: string) => {
      updateCard(id, { column: 'cancelled' }, `${id} cancelled`)
    },
    [updateCard],
  )

  const sortColumn = useCallback(
    (col: ColumnId) => {
      const cur = cardsRef.current
      const rank = { critical: 0, high: 1, medium: 2, low: 3, none: 4 } as const
      const inCol = cur.filter((c) => c.column === col)
      const sorted = [...inCol].sort((a, b) => rank[a.priority] - rank[b.priority])
      let k = 0
      const next = cur.map((c) => (c.column === col ? sorted[k++] : c))
      // Order is not persisted by the backend; this is a local tidy only.
      pushHistory()
      applyCards(next, false)
      notifyRef.current(`${COLUMN_LABEL[col]} sorted by priority`, true)
    },
    [applyCards, pushHistory],
  )

  const undo = useCallback(() => {
    const prev = history.current.pop()
    setHistoryLen(history.current.length)
    if (!prev) return
    const cur = cardsRef.current
    applyCards(prev, false)
    // Restore any backend fields the undone edit had changed.
    const curById = new Map(cur.map((c) => [c.id, c]))
    const restores: { id: string; fields: ItemUpdate }[] = []
    for (const p of prev) {
      const was = curById.get(p.id)
      if (!was) continue
      const before = backendFieldsOf(p)
      const after = backendFieldsOf(was)
      const fields: ItemUpdate = {}
      for (const k of Object.keys(before) as (keyof ItemUpdate)[]) {
        if (before[k] !== after[k]) (fields as Record<string, unknown>)[k] = before[k]
      }
      if (Object.keys(fields).length) restores.push({ id: p.id, fields })
    }
    if (!restores.length) return
    setStatus('syncing')
    Promise.all(restores.map((r) => updateItem(r.id, r.fields)))
      .then(() => {
        saveCache({ cards: prev, generatedAt: generatedAtRef.current ?? '' })
        setStatus('live')
        setError(null)
        setSyncedAt(Date.now())
      })
      .catch((e: Error) => {
        setStatus('offline')
        setError(e.message)
        notifyRef.current(`Undo failed — ${e.message}`)
      })
  }, [applyCards])

  return {
    cards,
    status,
    syncedAt,
    generatedAt,
    error,
    refresh,
    moveCard,
    updateCard,
    deleteCard,
    sortColumn,
    undo,
    canUndo: historyLen > 0,
  }
}
