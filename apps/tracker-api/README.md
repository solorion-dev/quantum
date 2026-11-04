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
| POST | /api/sync/run?dry=1 | outbound mirror to the **mock** Project; `dry=1` writes nothing but reports the same planned counts (added, updatedFields, ...) as a real run |
| DELETE | /api/items/:id | **501, out of scope**: items are never deleted; set `status` to `cancelled` |
| POST | /api/webhooks/github | HMAC `X-Hub-Signature-256` verified, deduped by `X-GitHub-Delivery` |

Item fields: see `TrackerItem` in the design note. `stale` (open + no update in 14 days) and `needsTriage`
(no assignee, or priority `none`, or backlog with no labels) are **computed, read-only**.

`TRACKER_WEBHOOK_SECRET` is **required**: the server refuses to start (non-zero exit, clear error, before touching
any DB) if it is unset or blank. There is no default. Use a throwaway value locally; tests use an explicit fake.

Try the inbound path locally:
```bash
export TRACKER_WEBHOOK_SECRET=local-throwaway   # start the server with this set
B='{"action":"closed","issue":{"number":100},"repository":{"full_name":"solorion-dev/sandbox"}}'
S=$(printf %s "$B" | openssl dgst -sha256 -hmac "$TRACKER_WEBHOOK_SECRET" | sed 's/.* //')
curl -s localhost:7655/api/webhooks/github -H "X-GitHub-Event: issues" -H "X-GitHub-Delivery: demo-1" \
  -H "X-Hub-Signature-256: sha256=$S" -d "$B"
curl -s 'localhost:7655/api/suggestions?state=pending'
```

### Fields added Nov 4
- People: `display` is the name field. `name` is a **deprecated alias** (same value), removed next release.
- Item `project`: `{id, title, derived}`. The live schema has no project column, so it is the top-level ancestor via
  `parentId`. Only a top-level item **with children** is a project; a parentless item with no children has
  `project: null` (the board shows it under "No project"). If an explicit `items.project` column exists it wins
  (`migrations/002_project_column.sql`, **proposed, not applied**, for review).
- Item `automated` (bool): true **only** when the item's **creating write** (its `created` event actor, or
  `items.source`) or its **last write** (latest `field_clock` entry) came from an unattended path: write source in
  `sync|github|github-sync|webhook|a2a|automation`, or a system handle (`sync`, `github-sync`, `a2a`, `webhook`).
  `people.kind` does **not** count: an agent acting through the board UI or API with `X-Actor` is a directed write
  and is not automated. Accepting a GitHub suggestion counts as the accepting person's write.
- Relations: `relations(item_id, related_id, 'parent')` stores parent → child, so `{rel:"parent", direction:"out"}`
  reads **"Parent of"** and `direction:"in"` reads **"Child of"**.

## Tests
```bash
cd apps/tracker-api && python3 -W ignore -m unittest discover -s tests -t .
```

## Not here yet (needs Scotty)
Real GitHub App adapter / installation tokens, the webhook secret and private key (Tritium env only, never committed),
running against the live DB, deploy. Swapping the adapter is config-only: implement `GitHubAdapter`.
