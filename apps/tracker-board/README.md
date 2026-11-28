# Tracker Board — Tracker-v1.2-design

The Tracker board UI: the **v1.2 design by Arena.AI**, integrated by Cooper
and wired to the **real tracker backend** (no demo data ships in this app).
Tracked as **TRK-0267** under the direction pinned on **TRK-0204**: a React
app in the quantum monorepo consuming the tracker service. The stopgap
`board_server.py` page stays live and untouched; this app replaces it only
when it has earned the swap (Scotty's call).

## Stack

- Vite + React 19 + TypeScript, Tailwind CSS 4, framer-motion, lucide-react.
- Self-contained styling (Arena's design system in `src/index.css`).
- **Deviation from the earlier plan:** v1.2 does *not* use the `@dsect/ui`
  kit from `dsect-net/design-system` — Arena's design is a complete visual
  system of its own, so the vite alias and kit dependency were dropped for
  this version rather than mixing two systems.

## Data flow

The tracker board service (`board_server.py` on Tritium, port 7654) has
**no list endpoint, no create, no delete, no PUT**. The app works with what
exists:

- **Board list** — a snapshot. `scripts/snapshot-board.py` reads the live
  Tracker DB (`/mnt/fast/tracker/tracker.db`, read-only) and writes
  `public/board-data.json` (`{generated_at, items[], projects[]}`). The app
  fetches that file and adapts it to cards:
  - status → column: `in_review → review`, `in_progress → progress`,
    everything else identity (incl. dedicated `backlog` and `cancelled`
    columns)
  - `due_at` → due date; `""` assignee → none
  - project = the title of the project hub (from `projects[]` membership)
    containing the item, else `General`
  - priority `none` is a real backend value: it renders with 0 bars and
    ranks last in priority sorts — it is never folded into `medium`
  - the "stale" chip is derived: an open item untouched for 21+ days (the
    backend has no stale flag)
  - within a column, cards sort by priority rank, then most recently
    updated first (the stopgap board's order)
- **Detail** — opening a card fetches `GET /api/item/<id>` and shows the
  real body, comments, and history.
- **Edits** — drag between columns and drawer edits POST to
  `/api/item/<id>/update` with the service's whitelist mapping:
  `description → body`, `column → status`, `due → due_at`,
  `assignee null → ""`, plus `title`, `priority`, `points`.
  `due_at` is always sent as a string (`""` clears it — `null` is a 400).
  Card order/position is **not** persisted (the backend has no field for
  it); reordering within a column is local and silent by design.
  Edits apply optimistically and roll back with an error if the POST fails.
- **Sync status** — the header pill reflects real load/edit results
  (`Live` / `Syncing` / `Offline`). Settings shows read-only backend info
  (snapshot `generated_at`, service route, cards loaded) — there is no
  user-configurable endpoint anymore.
- **localStorage** caches only the last real snapshot, so a reload paints
  real data instantly; an unreachable snapshot shows an honest error state,
  never demo data.

### Create / delete semantics

- **Create: not available.** The backend has no create endpoint, so the
  New / Add / Duplicate affordances are hidden (marked with code comments)
  until the backend grows one. No local-only fake cards.
- **Delete = cancel.** The backend has no DELETE; the UI's "Cancel item"
  posts `{status: "cancelled"}`, moving the card into the Cancelled column
  (a soft delete — nothing is destroyed).

## Run it

```bash
npm install
npm run dev        # vite dev server on :5174
npm run build      # tsc -b && vite build
npm run preview    # serves the build on :4174
```

`/api` is proxied by vite to `TRACKER_API` (default
`http://127.0.0.1:7654`). From a dev machine, point it at Tritium's tailnet
address:

```bash
TRACKER_API=http://100.66.182.7:7654 npm run preview
```

Regenerate the board snapshot from the live DB (on Tritium, or wherever the
DB is reachable):

```bash
python3 scripts/snapshot-board.py > public/board-data.json
```

## Screenshots

`screenshots/` holds the earlier stopgap-era shots (`desktop.png`,
`phone.png`, `sheet.png`) and the v1.2 verification set (`v12-desktop.png`,
`v12-phone.png`, `v12-drawer.png`) taken against the real 2026-10-26
snapshot (467 items: 32 review / 83 progress / 47 blocked / 173 planned /
1 backlog / 126 done / 5 cancelled).
