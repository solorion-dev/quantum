# tracker-api (experimental — tracker overhaul)

Python 3.11+ **stdlib only** (no pip install). Runs against a **local SQLite copy seeded from fake fixtures** and a
**mock GitHub Projects v2 GraphQL adapter**. It refuses to open the live DB (`/mnt/fast/tracker/…`) and makes no
network calls. Design: `docs/tracker-overhaul/tracker-overhaul-design-20261104.md`.

## Run locally (Pixel)
```bash
cd apps/tracker-api
python3 -m tracker_api --reset          # seeds data/tracker-local.db from fixtures/items.json, serves :7655
# options: --port 7655 --db path.db --cors http://localhost:5173   (env: PORT, TRACKER_DB, CORS_ORIGIN)
```
Point the board at it (in `apps/tracker-board`, no code changes needed for the proxy):
```bash
TRACKER_API=http://127.0.0.1:7655 npm run dev     # vite proxies /api -> tracker-api
```
or call it directly from the browser (CORS allows `http://localhost:5173`). Send `X-Actor: <handle>` to attribute edits
(defaults to `board-ui`). Every route also works without the `/api` prefix.

## Endpoints
| Method | Path | Notes |
|---|---|---|
| GET | /api/health | |
| GET | /api/items?status&kind&label&assignee&q&cursor&limit | `{items, nextCursor}` |
| POST | /api/items | `{title, body?, kind?, status?, priority?, assigneeId?, dueAt?, points?, parentId?, labels?}` → 201 item |
| GET | /api/items/:id | `{item, comments, statusHistory, changes, relations, links, githubLink}` |
| PATCH | /api/items/:id | whitelisted fields (as POST) → `{item, changed[]}`; 400 on bad enum / unknown person |
| POST | /api/items/:id/comments | `{body}` |
| GET | /api/people, /api/labels | registries (people = assignee authority) |
| GET | /api/suggestions?state=pending\|accepted\|rejected\|all | inbound GitHub changes awaiting a human |
| POST | /api/suggestions/:id/accept | applies via normal update (history, field clock) |
| POST | /api/suggestions/:id/reject | `{reason?}` |
| GET | /api/sync/status, /api/sync/log | |
| POST | /api/sync/run?dry=1 | outbound mirror to the **mock** Project |
| POST | /api/webhooks/github | HMAC `X-Hub-Signature-256` verified, deduped by `X-GitHub-Delivery` |

Item fields: see `TrackerItem` in the design note. `stale` (open + no update in 14 days) and `needsTriage`
(no assignee, or priority `none`, or backlog with no labels) are **computed, read-only**.

Try the inbound path locally (fake secret `local-dev-fake-secret`, override with `TRACKER_WEBHOOK_SECRET`):
```bash
B='{"action":"closed","issue":{"number":100},"repository":{"full_name":"solorion-dev/sandbox"}}'
S=$(printf %s "$B" | openssl dgst -sha256 -hmac local-dev-fake-secret | sed 's/.* //')
curl -s localhost:7655/api/webhooks/github -H "X-GitHub-Event: issues" -H "X-GitHub-Delivery: demo-1" \
  -H "X-Hub-Signature-256: sha256=$S" -d "$B"
curl -s 'localhost:7655/api/suggestions?state=pending'
```

### Fields added Nov 4
- People: `display` is the name field. `name` is a **deprecated alias** (same value), removed next release.
- Item `project`: `{id, title, derived}`. The live schema has no project column, so it is the top-level ancestor via
  `parentId` (a root is its own project). If an explicit `items.project` column exists it wins
  (`migrations/002_project_column.sql`, **proposed, not applied**, for review).
- Item `automated` (bool): true when the item's **creator** (its `created` event actor, or `items.source`) or its
  **last writer** (latest `field_clock` entry) is automated: provenance source in
  `sync|github|github-sync|webhook|a2a|agent|automation`, or the actor's `people.kind` in `agent|bot|a2a|sync|system`,
  or a system handle (`sync`, `github-sync`, `a2a`, `webhook`). Humans and unknown UI actors are not.
  Accepting a GitHub suggestion counts as the accepting person's write.
- Relations: `relations(item_id, related_id, 'parent')` stores parent → child, so `{rel:"parent", direction:"out"}`
  reads **"Parent of"** and `direction:"in"` reads **"Child of"**.

## Tests
```bash
cd apps/tracker-api && python3 -W ignore -m unittest discover -s tests -t .
```

## Not here yet (needs Scotty)
Real GitHub App adapter / installation tokens, the webhook secret and private key (Tritium env only, never committed),
running against the live DB, deploy. Swapping the adapter is config-only: implement `GitHubAdapter`.
