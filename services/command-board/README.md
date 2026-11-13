# Command Board Service (`services/command-board`)

Canonical store + REST API for the Quantum Command Board (TRK-0686) — the
graduated home of the board that started as a Muse Space. The Space
syncs against this API (see `apps/command-board/SYNC.md`); the hub-api
`quantum_board_*` MCP tools wrap it for fleet agents.

**Stack:** TypeScript + Fastify 5 + better-sqlite3 (WAL) + zod, mirroring
`services/notekeeper`. Port **8798** on `127.0.0.1` by default.

## Model

Boards → Items (column `inbox|now|next|later|waiting|done`, kind
`task|idea`, priority flag, assignee `scotty|cooper`, checked, Cooper status
line, Tracker id) with subtasks and comments, plus an append-only activity
feed and a `changes` sync log. Every row carries an `origin`
(`app|space|mcp|seed`) and items/boards/comments carry a nullable unique
`space_id` for Space mapping. The store seeds on first boot with the real
backlog the Space opened with (7 boards, 9 items) — never demo data after
that.

## API (`/api/v1`)

| Route | Purpose |
|---|---|
| `GET /state` | Full state (boards, items with subtasks+comments, activity) — the `quantum_board_state` shape |
| `GET/POST /boards`, `DELETE /boards/:id` | Board CRUD (delete unfiles items to Inbox) |
| `GET/POST /items`, `GET/PATCH/DELETE /items/:id` | Item CRUD + filing |
| `POST /items/:id/cooper-update` | Cooper composite: status line + move + comment + activity in one call |
| `POST /items/:id/comments` | Comment (author free-form; agents pass their identity) |
| `POST /items/:id/subtasks`, `PATCH/DELETE /subtasks/:id` | Checkbox subtasks |
| `GET /activity` | Activity feed |
| `GET /sync/changes?since=`, `POST /sync/push` | Space sync (see SYNC.md) |
| `GET /health` (root) | `{ status, schema_version, boards, items }` |

## Run / verify

```sh
npm install
npm test            # vitest: service, REST contract, sync push, auth
npm run smoke       # builds, then scripts/smoke.mjs against a running server
npm run build && npm start
```

Env: `PORT` (8798), `HOST` (127.0.0.1), `BOARD_DB` (`./data/command-board.db`),
`BOARD_TOKEN` (optional Bearer for `/api/*`; production fronting is the
Solorion login seam).
