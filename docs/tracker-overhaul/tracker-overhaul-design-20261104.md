# Tritium Tracker overhaul: design note (step 1)
Author: Volt (Harbor). Date: 2026-11-04. Status: draft for Helm/Scotty. Read-only investigation; nothing live touched.

## 1. Current architecture (as found)
- **DB:** SQLite at `/mnt/fast/tracker/tracker.db` on Tritium (Quantum memory #1712). Source of truth since Oct 18. Seeded with 141 items; ids now run past TRK-0523.
- **CLI:** `/mnt/fast/tracker/tracker.py` (stdlib + numpy). Semantic search uses local llama-embed `:8082` `/v1/embeddings`, brute-force cosine.
- **MCP:** 11 `quantum_tracker_*` tools in hub-api (PR #94, `lib/mcp-tracker-tools.js`). Production hub checkout is `/home/scott/dsect-hub-api`, branch `fix/service-probes-and-registry-audit`, not main (#1717).
- **Live board:** `board_server.py` on Tritium, port 7654, systemd user unit `tracker-board.service`, served on tailnet via Tailscale Serve. Plain server-rendered kanban (v1 read-only, v2 adds the detail sheet, edit, and drag). Also embedded as HA panel `/config/dashboards/tracker.yaml`. **The live board code is not in any repo I could find.**
- **React board (Pixel's lead):** `solorion-dev/quantum` (dsect-net/quantum redirects here), path **`apps/tracker-board`** (not `apps/tracker`), branch `worker/cooper/tracker-board-ui` @ `48fb36f` (Oct 26, "Tracker-v1.2-design"). Vite 7 + React 19 + TS 5.9 + Tailwind 4 + framer-motion. Not on main: 4 ahead, 43 behind. It does **not** use `@dsect/ui` or the Quantum UI kit today. It loads a `/board-data.json` snapshot (`scripts/snapshot-board.py`) and proxies `/api` to board_server.py. Verdict: this is the best base for the overhaul UI, but it is a prototype beside the live board, not what runs live.
- **Schema (from the MCP output and code; a direct `.schema` dump failed because Tritium SSH returned 502 at 02:51 ET):**
  - `items`: id (TRK-nnnn), kind {goal,issue,task,decision,milestone,bug,note}, title, body, status {backlog,planned,in_progress,in_review,blocked,done,cancelled}, priority {critical,high,medium,low,none}, assignee (handle text), parent_id, due_at, points, source, external_ref, created_at, updated_at
  - `tags` (item↔tag)
  - `links` (url / github issue|pr / memory id)
  - `relations` (project, related, blocks, depends_on, parent, child, supersedes)
  - `events` (comments + change history, with actor)
  - `embeddings` (per item)
  - `people` (handles, Matrix ids, mailboxes, hub workers)
  - Exact table and column names still need confirming with a read-only `sqlite3 -readonly .schema`.

## 2. Proposed data model (additive migrations; nothing existing is dropped)
- `items`: existing columns plus `assignee_id` FK→people (keep the handle text during transition) and `field_clock` JSON (per-field `{writer, at}` for last-writer tracking).
- `people`: id, handle, display, kind (human/agent), github_login, active. **This table is the authority on assignees.**
- `labels`(id, name, color) and `item_labels`(item_id, label_id). Existing tags migrate into them.
- `status_history`(id, item_id, from, to, actor, at, source {ui,cli,mcp,github-suggest}).
- `github_links`(item_id, repo, number, type {issue,pr}, project_id, project_item_id, node_id, etag, remote_updated_at, last_synced_at, UNIQUE(repo, number), UNIQUE(item_id, repo)).
- `suggested_changes`(id, item_id, field, proposed_value, remote_actor, delivery_id, state {open,accepted,rejected}, decided_by, at).
- `sync_log`(id, run_id, direction {out,in}, item_id, action, result, delivery_id, error, at).
- `webhook_deliveries`(delivery_id PK, event, received_at). Used for dedupe.

## 3. Sync direction and conflict rule (interim defaults)
- **Tracker DB is the source of truth. GitHub Projects mirrors it outward.** An outbound run pushes title, status→Project Status field, priority/points/due→custom fields, and labels.
- **Inbound changes never write directly.** A GitHub close/reopen, field edit, or assignee change creates a `suggested_changes` row for a human to accept in the board.
- **Assignees:** only `people` decides. GitHub assignee changes are suggestions, mapped through `people.github_login`.
- **Conflict:** `field_clock` records the last writer per field. Outbound skips a field if the remote `updated_at`/etag moved since the last sync and the remote value differs; that case becomes a suggestion instead of an overwrite.
- **Idempotent upsert keyed by TRK id:** the Project item carries a `TRK` text field, and `github_links` is unique on (item_id, repo). A rerun produces no diff.

## 4. Auth: GitHub App on solorion-dev (Scotty's choice; he approves the install after reading this; NOT created)
- **Permissions (least privilege):**
  - Organization: Projects read/write.
  - Repository: Metadata read; Issues read; Pull requests read.
  - Upgrade Issues/PRs to write **only if** we later mirror labels or closes out to issues. Not needed for v1, which mirrors only into the Project.
- **Webhooks:** `projects_v2_item`, `issues`, `pull_request`, `installation` (+ `installation_repositories`).
  - Verify `X-Hub-Signature-256` with HMAC-SHA256 and a constant-time compare. Reject anything unsigned or mismatched.
  - Dedupe on `X-GitHub-Delivery` via `webhook_deliveries`.
  - Respond 2xx fast and process async.
  - The receiver stays tailnet-only, or uses a Cloudflare tunnel route (Scotty's call).
- **Repos:** "selected repositories" only. Proposed: `solorion-dev/quantum` and `hub-api`, plus any repo whose issues are linked from tracker items. Scotty picks the final list. Not all repos.
- **Secrets:** the App private key (.pem) and webhook secret live on Tritium only, e.g. `/etc/tracker-sync/` (0600, owner scott) loaded through the systemd `EnvironmentFile`/`LoadCredential`. They are never committed, never logged, and gitleaks runs on every push. Short-lived installation tokens are minted per run and not stored.
- **Until install:** `GITHUB_ADAPTER=mock`. A mock GraphQL adapter (in-memory Project + recorded fixtures) implements `addProjectV2ItemById`, `updateProjectV2ItemFieldValue`, and the items query. A read-only path can hit public REST for public repos with no token. Replayable webhook payload fixtures (signed with a test secret) exercise the inbound path. The adapter swap needs config only, no code change.

## 5. API (board backend, folded into hub-api later)
| Method | Path | Purpose |
|---|---|---|
| GET | /api/items?status&kind&label&assignee&q&cursor | list (replaces snapshot) |
| GET | /api/items/:id | `{item, comments, statusHistory, changes, relations, links, githubLink}` in one payload |
| POST | /api/items | create |
| PATCH | /api/items/:id | whitelisted field edit, writes field_clock + status_history |
| POST | /api/items/:id/comments | comment |
| GET | /api/people, /api/labels | registries |
| GET | /api/sync/status, /api/sync/log | sync health |
| GET | /api/suggestions?state=pending | inbound review (state: pending/accepted/rejected/all) |
| POST | /api/suggestions/:id/accept | applies the change via normal update; logged to status history/events |
| POST | /api/suggestions/:id/reject | body `{reason?}` |
| POST | /api/sync/run?dry=1 | outbound mirror (mock until install) |
| POST | /webhooks/github | signed receiver |

## 6. TypeScript item type (for Pixel)
```ts
export type Status = 'backlog'|'planned'|'in_progress'|'in_review'|'blocked'|'done'|'cancelled'
export type Priority = 'critical'|'high'|'medium'|'low'|'none'
export type Kind = 'goal'|'issue'|'task'|'decision'|'milestone'|'bug'|'note'
export type SyncState = 'unlinked'|'pending'|'synced'|'suggested'|'error'
export interface GitHubLink { repo: string; number: number; type: 'issue'|'pull_request'
  projectItemId: string|null; url: string; etag: string|null; remoteUpdatedAt: string|null }
export interface TrackerItem { id: `TRK-${string}`; kind: Kind; title: string; body: string
  status: Status; priority: Priority; assigneeId: string|null; labels: string[]
  parentId: string|null; dueAt: string|null; points: number|null
  createdAt: string; updatedAt: string
  readonly stale: boolean        // computed: not done/cancelled and no update in 14 days
  readonly needsTriage: boolean  // computed: no assignee, or priority 'none', or backlog with no labels
  github: GitHubLink|null
  sync: { state: SyncState; lastSyncedAt: string|null; pendingSuggestionId: string|null; error: string|null } }
```
Fixture (20 fake items, TRK-9001..9020, fake repo `solorion-dev/sandbox`): `docs/tracker-overhaul/fixture.json` (exact `GET /api/items` shape). Seed source: `apps/tracker-api/fixtures/items.json`.
Detail payload adds `comments[{id,actor,body,at}]`, `statusHistory[{fromStatus,toStatus,actor,source,at}]`, `relations[{rel,itemId,direction}]`, `links[{kind,target,label}]`, `githubLink`. Suggestions: `{id:'SUG-n', itemId, field, currentValue, proposedValue, remoteActor, reason, state:'pending'|'accepted'|'rejected', decidedBy, decisionReason, decidedAt, createdAt}`.
Backend implemented in `apps/tracker-api` (see its README).

## 7. Test plan
- Unit tests: status/priority mapping, field_clock conflict, upsert idempotency (run twice, zero diff), and HMAC verify (good, bad, and missing signatures).
- Delivery-id dedupe: replaying the same payload is a no-op.
- Integration: the mock adapter against a **copy** of tracker.db, covering migration up/down, outbound mirror, and inbound close→suggestion→accept.
- People authority: a GitHub assignee change yields only a suggestion.
- Scout E2E at 1920x1080 (and 1280x720) on the React board against the fixture and a staging DB copy: board, drawer, edit, drag, suggestions inbox. No secret appears in logs; gitleaks runs in CI.

## 8. Milestones
1. Nov 4 AM: this note + fixture on `experimental/tracker-overhaul-20261104`.
2. Nov 4 PM: migrations against a DB copy; API list/patch/create; mock adapter.
3. Nov 5 AM: sync engine (outbound + suggestions) and webhook receiver with tests. Pixel moves the UI to the Quantum UI kit against the fixture/API.
4. **Nov 5 EOD: branch ready for Scout's QA**, running on mocks and a DB copy.
5. After Scotty: App install, live cutover, retiring board_server.py.

## 9. Open questions
- Exact table names, and whether `people` already has a github_login column. Needs the read-only schema dump; Tritium SSH failed.
- Should board_server.py be checked into a repo before we replace it?
- `@dsect/ui` vs the Quantum UI kit: which package and repo does Pixel mean? Neither is in `apps/tracker-board` today.
- Which GitHub Project (number) is the mirror target?
- Webhook ingress: tailnet-only plus polling, or a public tunnel?
