import type { ItemDetail, Label, Person, Status, Suggestion, TrackerItem } from '../types'

/** Everything the UI needs from Volt's tracker-api (apps/tracker-api @ 946dcb8). */
export interface TrackerClient {
  readonly source: 'api' | 'fixture'
  listItems(): Promise<TrackerItem[]>
  getItem(id: string): Promise<ItemDetail>
  updateItem(id: string, patch: ItemPatch): Promise<TrackerItem>
  createItem(input: ItemPatch & { title: string }): Promise<TrackerItem>
  listPeople(): Promise<Person[]>
  listLabels(): Promise<Label[]>
  listSuggestions(): Promise<Suggestion[]>
  acceptSuggestion(id: string): Promise<void>
  rejectSuggestion(id: string, reason?: string): Promise<void>
}
export type ItemPatch = Partial<Pick<TrackerItem, 'title' | 'body' | 'kind' | 'status' | 'priority' | 'assigneeId' | 'labels' | 'dueAt' | 'points' | 'parentId'>> & { status?: Status }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

/** Who edits are attributed to (X-Actor). Configurable; defaults to this UI's agent. */
const ACTOR = (import.meta.env.VITE_TRACKER_ACTOR as string | undefined) ?? 'pixel'

export class HttpClient implements TrackerClient {
  readonly source = 'api' as const
  constructor(private base = '/api') {}
  private async req<T>(path: string, init?: RequestInit): Promise<T> {
    const write = init?.method && init.method !== 'GET'
    const res = await fetch(`${this.base}${path}`, {
      ...init,
      headers: { ...(write ? { 'content-type': 'application/json', 'X-Actor': ACTOR } : {}), ...(init?.headers ?? {}) },
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new ApiError(res.status, (body as { error?: string }).error ?? res.statusText)
    return body as T
  }
  async health() { return this.req<{ ok: boolean }>('/health') }
  async listItems() {
    const out: TrackerItem[] = []
    let cursor: string | null = null
    do {
      const q: string = `?limit=200${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`
      const page: { items: TrackerItem[]; nextCursor?: string | null } = await this.req(`/items${q}`)
      out.push(...page.items)
      cursor = page.nextCursor ?? null
    } while (cursor)
    return out
  }
  getItem(id: string) { return this.req<ItemDetail>(`/items/${encodeURIComponent(id)}`) }
  async updateItem(id: string, patch: ItemPatch) {
    const r = await this.req<{ item: TrackerItem; changed: string[] }>(`/items/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(patch) })
    return r.item
  }
  createItem(input: ItemPatch & { title: string }) { return this.req<TrackerItem>('/items', { method: 'POST', body: JSON.stringify(input) }) }
  // 7fa3ad8 (live schema) returns `name`; 946dcb8 returned `display`. Accept either, fall back to id.
  listPeople() {
    return this.req<{ people: (Omit<Person, 'display'> & { display?: string | null; name?: string | null })[] }>('/people')
      .then((r) => r.people.map((p) => ({ ...p, display: p.display || p.name || p.id })))
  }
  listLabels() { return this.req<{ labels: Label[] }>('/labels').then((r) => r.labels) }
  listSuggestions() { return this.req<{ suggestions: Suggestion[] }>('/suggestions?state=pending').then((r) => r.suggestions) }
  async acceptSuggestion(id: string) { await this.req(`/suggestions/${encodeURIComponent(id)}/accept`, { method: 'POST', body: '{}' }) }
  async rejectSuggestion(id: string, reason?: string) {
    await this.req(`/suggestions/${encodeURIComponent(id)}/reject`, { method: 'POST', body: JSON.stringify(reason ? { reason } : {}) })
  }
}

/**
 * VITE_TRACKER_SOURCE: 'api' (require the API), 'fixture' (offline), or 'auto' (default):
 * use the API when /api/health answers, else fall back to docs/tracker-overhaul/fixture.json.
 */
export async function createClient(): Promise<TrackerClient> {
  const src = (import.meta.env.VITE_TRACKER_SOURCE as string | undefined) ?? 'auto'
  const forced = new URLSearchParams(location.search).get('source')
  const mode = forced === 'fixture' || forced === 'api' ? forced : src
  if (mode !== 'fixture') {
    const http = new HttpClient((import.meta.env.VITE_TRACKER_API_BASE as string | undefined) ?? '/api')
    if (mode === 'api') return http
    try { if ((await http.health()).ok) return http } catch { /* offline: fall through */ }
  }
  const { FixtureClient } = await import('./fixtureClient')
  const n = Number(new URLSearchParams(location.search).get('synthetic') || 0)
  return new FixtureClient(Number.isFinite(n) && n > 0 ? Math.min(n, 5000) : 0)
}
