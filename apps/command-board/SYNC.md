# Command Board Sync — Muse Space ⇄ Quantum App (TRK-0686)

One shared board, two doors. This document is the sync contract between the
**Muse "Command Board" Space** (Scotty's quick-capture surface) and the
**Quantum Command Board app** (`apps/command-board` UI +
`services/command-board` API). It describes exactly what each side must do;
the app side is implemented in this repo, the Space side is driven by Cooper
from the Muse seat (artifact edits are not made from this repo).

## Source of truth

The **app API is canonical**: `services/command-board` owns the SQLite store
and every durable write ultimately lands there. The Space keeps its own
artifact-local copy so capture stays instant and offline-tolerant, and syncs
deltas against the API. Fleet agents never write to the Space directly —
they use the API or the `quantum_board_*` MCP tools (hub-api), which wrap
the same API. That keeps one write path, one audit trail.

## Identity mapping

Every app row carries a nullable `space_id` (unique) — the id of the same
entity in the Space. Space rows carry the app id in their `trkId`-adjacent
metadata field `appId` once linked. Mapping rules:

- First contact for an entity: the pushing side sends its own id as
  `spaceId` (Space→app) and the app returns the app id in the push result;
  the Space stores it. From then on both sides address the entity by the
  pair (appId, spaceId).
- Boards map by name as a fallback only during bootstrap (the seven seeded
  boards share names on both sides); after bootstrap, ids rule.

## Endpoints (implemented app-side)

- `GET  /api/v1/sync/changes?since=<seq>` — the app's change log (every
  upsert/delete of boards, items, comments, subtasks, activity) after the
  caller's cursor, each entry with the entity's current full snapshot
  (`null` snapshot = deleted). Response: `{ cursor, changes[] }`.
- `POST /api/v1/sync/push` — accepts `{ entities: [...] }`, each
  `{ entity: 'board'|'item'|'comment', spaceId, updatedAt, data }`.
  Entities are upserted by `spaceId`. Response reports per-entity
  `{ applied, reason?, id }` so the pusher can record app ids and see
  conflicts it lost.

## Conflict rule

**Last-write-wins per entity, by `updatedAt`** (the Space's per-field LWW
refines this where fields don't overlap; v1 ships entity-level):

- Push: an incoming entity is applied only when its `updatedAt` is newer
  than the stored row's `updated_at`. Older pushes are acknowledged with
  `applied: false, reason: 'stale'` — never an error.
- Pull: the consumer applies snapshots the same way against its own rows.
- **Comments are append-only**: they never overwrite; they dedupe by
  `spaceId`. A comment that loses a race still exists — conversation is
  never silently dropped.
- **Deletes propagate as tombstones** in the change log (`op: 'delete'`,
  snapshot `null`). The Space applies a tombstone only if it has no local
  edit newer than the tombstone's `at`.
- The **activity feed is the audit**: every applied change, from either
  side, writes an activity row with its origin (`app`, `space`, `mcp`,
  `seed`). If the two surfaces ever disagree about what happened, the
  activity log — not either UI — is where you look.

## The loop (Space side — what Cooper's seat must wire)

1. On Space open and on its 30-minute review pass, the Space calls
   `GET /api/v1/sync/changes?since=<stored cursor>` and applies snapshots
   (skipping entities whose `origin` is `space` and whose `spaceId` it
   already holds at the same `rev` — echoes of its own pushes).
2. When Scotty captures or edits in the Space, the Space queues the entity
   and pushes it with `POST /api/v1/sync/push` on the next pass; app ids
   from the response are stored back onto the Space rows.
3. Cooper's review pass reads new Inbox items from the **API state**
   (`quantum_board_state`), files them via `quantum_board_update`, and
   comments via `quantum_board_comment` — those writes flow back to the
   Space on its next pull, so Scotty sees filing happen in the surface he
   captured in.

## Failure behavior

- API unreachable: the Space keeps capturing locally and retries the push
  next pass; nothing is blocked and nothing is lost. The app UI shows a
  plain "service unreachable" banner rather than stale data dressed as live.
- A push batch is idempotent: replaying it is a no-op (upsert by `spaceId`,
  comment dedupe). Cursors only advance on fully-applied pulls.
- Auth: sync endpoints sit behind the same optional `BOARD_TOKEN` bearer
  as the rest of `/api/*`; production fronting is the Solorion login seam.

## Bootstrap (one time)

The app seeds the Space's original backlog on first boot (`seedIfEmpty`),
so both sides start from the same seven boards and nine items. Bootstrap
linking: the first sync pass matches seeded entities by (board name, item
title) and stamps `space_id`s; after that, ids rule and titles may drift
freely on either side.
