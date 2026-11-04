// In-memory dev client over docs/tracker-overhaul/fixture.json. Never talks to a server;
// edits live only in this tab. Shapes mirror Volt's endpoints so the swap is a flag flip.
import fixture from '../dev/fixture.json'
import extras from '../dev/fixture-extras.json'
import type { ItemDetail, Label, Person, Relation, Suggestion, TrackerItem } from '../types'
import type { ItemPatch, TrackerClient } from './api'

const clone = <T,>(v: T): T => structuredClone(v)
const delay = (ms = 60) => new Promise((r) => setTimeout(r, ms))

const PEOPLE: Person[] = ['coda', 'pixel', 'quill', 'scout', 'volt'].map((id) => ({ id, display: id[0].toUpperCase() + id.slice(1), kind: 'agent', active: true }))

export class FixtureClient implements TrackerClient {
  readonly source = 'fixture' as const
  private items: TrackerItem[]
  private suggestions: Suggestion[]
  private seq = 9200
  constructor(synthetic = 0) {
    this.items = clone([...(fixture.items as TrackerItem[]), ...(extras.items as TrackerItem[])])
    // ?source=fixture&synthetic=600 pads the dataset with fake items for load testing (real tracker ~600 items).
    const base = this.items.slice(0, 20)
    for (let n = 0; this.items.length < synthetic; n++) {
      const b = base[n % base.length]
      this.items.push({ ...clone(b), id: `TRK-${10000 + n}`, title: `Synthetic ${n + 1}: ${b.title}`, parentId: null, github: null,
        sync: { ...b.sync, state: 'unlinked', pendingSuggestionId: null } } as TrackerItem)
    }
    const first = this.items[0]
    this.suggestions = [
      { id: 'SUG-1', itemId: first.id, field: 'status', currentValue: first.status, proposedValue: 'done', remoteActor: 'volt-fake-gh',
        reason: 'issue closed on GitHub', state: 'pending', createdAt: '2026-11-04T07:30:00Z' },
    ]
    first.sync = { ...first.sync, state: 'suggested', pendingSuggestionId: 'SUG-1' }
  }
  async listItems() { await delay(); return clone(this.items) }
  async getItem(id: string): Promise<ItemDetail> {
    await delay()
    const item = this.items.find((i) => i.id === id)
    if (!item) throw new Error(`404 ${id}`)
    const relations: Relation[] = [
      ...(item.parentId ? [{ rel: 'parent', itemId: item.parentId, direction: 'in' as const }] : []),
      ...this.items.filter((i) => i.parentId === id).map((c) => ({ rel: 'parent', itemId: c.id, direction: 'out' as const })),
    ]
    return clone({
      item, comments: [], changes: [],
      statusHistory: [{ fromStatus: null, toStatus: item.status, actor: 'fixture', source: 'fixture', at: item.createdAt }],
      relations, links: [], githubLink: item.github,
    })
  }
  async updateItem(id: string, patch: ItemPatch) {
    await delay()
    const it = this.items.find((i) => i.id === id)
    if (!it) throw new Error(`404 ${id}`)
    Object.assign(it, patch, { updatedAt: new Date().toISOString() })
    return clone(it)
  }
  async createItem(input: ItemPatch & { title: string }) {
    const now = new Date().toISOString()
    const it: TrackerItem = { id: `TRK-${++this.seq}`, kind: 'task', body: '', status: 'backlog', priority: 'none', assigneeId: null, labels: [],
      parentId: null, dueAt: null, points: null, createdAt: now, updatedAt: now, github: null, stale: false, needsTriage: true,
      sync: { state: 'unlinked', lastSyncedAt: null, pendingSuggestionId: null, error: null }, ...input }
    this.items.push(it)
    return clone(it)
  }
  async listPeople() { return clone(PEOPLE) }
  async listLabels(): Promise<Label[]> { return [...new Set(this.items.flatMap((i) => i.labels))].sort().map((name) => ({ name })) }
  async listSuggestions() { await delay(); return clone(this.suggestions.filter((s) => s.state === 'pending')) }
  private settle(s: Suggestion) {
    const it = this.items.find((i) => i.id === s.itemId)
    if (it) it.sync = { ...it.sync, state: 'synced', pendingSuggestionId: null }
    return it
  }
  async acceptSuggestion(id: string) {
    const s = this.suggestions.find((x) => x.id === id)
    if (!s || s.state !== 'pending') throw new Error('404')
    s.state = 'accepted'
    const it = this.settle(s)
    if (it) (it as unknown as Record<string, unknown>)[s.field] = s.proposedValue
  }
  async rejectSuggestion(id: string) {
    const s = this.suggestions.find((x) => x.id === id)
    if (!s || s.state !== 'pending') throw new Error('404')
    s.state = 'rejected'
    this.settle(s)
  }
}
