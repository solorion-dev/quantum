# SPEC-4: Memory merge/update tool + digest-since-date (draft v0.2, Quill, 2026-11-01)

Status: DRAFT v0.2, updated with Forge's server answers; ready for Forge to implement on an experimental branch. No server code changed. Basis: Tag Scheme v0.3 (D6, D7, "fix tiers before dedupe" #346, "survivor tier only after review").

## 1. Gaps today
No get-by-id, no update, no merge, no change log; `list_memories` truncates around 20 KB; `prune_memories` / `prune()` hard-deletes expired rows and returns only a count, with no log and no timer.

## 2. New tools
### 2.1 `get_memory(id) -> Memory` (helper, read-only)
Always returns the row, including superseded rows (with `superseded_by`, `merged_from`).

### 2.1a Visibility of superseded rows
`search_memory`, `list_memories` and the vector `_nearest` lookup filter `superseded_by IS NULL` unless `include_superseded=true`.

### 2.2 `update_memory`
```json
{"id": 2271,
 "changes": {"tier": "durable", "tags_add": ["decision"], "tags_remove": [],
             "content": null, "importance": null, "expires_at": null, "kind": null},
 "reason": "standing decision, D7 promotion",
 "approval_id": null,
 "dry_run": true}
```
Rules: never changes `agent` (author) or `created_at`; `team` change only via re-attribution (D3) with reason; tags are add/remove only and normalized (SPEC-3); new content goes through SPEC-3 guardrails + secret scan (a hit is `E_SECRET_DETECTED`, nothing changes); `dry_run` defaults true. The actor comes from the hub key (`actor_key_id`), not the body.
Response: `{"ok": true, "dry_run": true, "id": 2271, "diff": {...before/after...}, "approval_required": false, "audit_id": null}`

### 2.3 `merge_memories`
```json
{"ids": [101, 102, 103], "survivor_id": 101,
 "merged_content": null, "tier": null, "reason": "dup cluster 33.1",
 "approval_id": null, "dry_run": true}
```
Rules: survivor keeps its id, author, created_at; tags = normalized union; seen_count = sum; importance = max; `merged_from` = ids; tier = survivor's unless `tier` set explicitly (never auto-highest); expires_at = latest of members unless explicitly set; members are soft-deleted (`superseded_by` = survivor), not hard-deleted; a merge across different teams or authors requires review flag; a member already superseded is rejected; the final merged content (supplied `merged_content` or the survivor's) is secret-scanned before commit; `content_hash` is recomputed and must not collide with the unique `(content_hash, agent)` index (collision -> `E_DUPLICATE`).

### 2.4 `memory_digest`
```json
{"since": "2026-10-25T00:00:00-04:00", "until": null, "team": "harbor", "agent": null,
 "tier": null, "include": ["created","updated","merged","expired","pruned"],
 "format": "summary", "limit": 200, "cursor": null}
```
Response:
```json
{"since": "...", "counts": {"created": 41, "updated": 6, "merged": 2, "expired": 7, "pruned": 3},
 "items": [{"id": 2312, "event": "created", "at": "...", "team": "harbor", "agent": "quill",
            "tier": "project", "snippet": "first 200 chars"}],
 "next_cursor": null}
```
Paginated by cursor to avoid the ~20 KB truncation. Snippets pass through the secret scan redactor. `since` required; timezone-aware ISO 8601. `pruned` events come from `memory_audit` rows (no content, so no snippet); `created` from `created_at`, `expired` from `expires_at` in window.

## 3. Storage and audit trail (SQLite 3.46.1, `quantum_memory.db`)
Existing `memories`: id, content, content_hash, agent, team, kind, tier, importance, tags (JSON), created_at, last_seen, seen_count, expires_at; unique index `(content_hash, agent)`; side tables `memory_vec` (sqlite-vec) and `embed_cache`.
Migration in `_migrate()` (ALTER TABLE ADD COLUMN, same pattern as `team`), after a snap.py snapshot:
- `memories.superseded_by INTEGER NULL`, `memories.merged_from TEXT NULL` (JSON id list); index on `superseded_by`.
- `memory_audit(audit_id, at, actor, actor_key_id, actor_team, action[write_rejected|write_warned|update|merge|retier|restore|prune], memory_id, content_hash, before_json, after_json, reason, approval_id, dry_run)`; indexes on `at` and `memory_id`. Append-only, written in the same transaction as the change.
- `memory_approvals(id, scope, created_by_key, created_at, expires_at, used_at)`; `scope` = tool name + hash of the call params.
- `prune()` writes one `memory_audit` row per deleted row (id, tier, agent, content_hash, expires_at, actor, time; no content) in the same transaction.
Datasette (:8097) also has the DB open; migrations must tolerate a concurrent reader.
`restore_memory(audit_id)` reverts one change (itself audited; restores that shorten expiry follow the same approval rules).

## 4. Approval rules (D7)
| Change | Who may do it without Scotty | Needs Scotty |
|---|---|---|
| Promote to durable (removes expiry) | Cooper or Quill (logged) | — |
| Add tags, fix typos, re-attribute per D3 | row author, Cooper, Quill | — |
| Lengthen expiry | Cooper, Quill | — |
| Shorten expiry / move to transient / demote | — | yes |
| Merge of 2 rows, same author+team | Cooper, Quill | — |
| Bulk merge (> 2 rows, or > 1 cluster per call) or any delete | — | yes |
| Anything touching team=`scott` rows | — | yes |

"Needs Scotty" means the call carries an `approval_id` from `memory_approvals`. Only Scotty's owner key can create one, via an owner-only tool (`create_memory_approval(scope, ttl)`). Upstream verifies the scope matches this tool + params hash, that it is unused and unexpired, marks `used_at`, and audits it. An agent relaying "Scotty agreed" never counts. Without a valid approval the call returns `E_APPROVAL_REQUIRED` and changes nothing (dry-run diff still returned).
Actor identity always comes from the authenticated hub key (`actor_key_id`, key-bound agent/team), not the request body.

## 5. Errors
`E_NOT_FOUND`, `E_APPROVAL_REQUIRED {rule}`, `E_FORBIDDEN_FIELD {field: agent|created_at}`, `E_ALREADY_SUPERSEDED`, `E_SECRET_DETECTED` (SPEC-3), `E_INVALID_SINCE`, `E_TOO_MANY_IDS`, `E_APPROVAL_INVALID {reason: scope|used|expired}`, `E_DUPLICATE`, `E_OWNER_ONLY`.

## 6. Config
`QM_MERGE_MAX_IDS` (default 10), `QM_BULK_THRESHOLD` (2), `QM_PROMOTERS` (`cooper,quill`), `QM_APPROVER` (`scotty`), `QM_PROTECTED_TEAMS` (`scott`), `QM_DIGEST_PAGE` (200), `QM_APPROVAL_TTL_MAX` (24h), `QM_OWNER_KEY_ID` (key id reference only, never the key).

## 7. Test cases
| # | Case | Expected |
|---|---|---|
| U1 | update dry_run default | diff returned, no change, no audit row (or audit dry_run=true) |
| U2 | Quill promotes project->durable | ok, expires_at null, audit row with before tier |
| U3 | Volt promotes to durable | `E_APPROVAL_REQUIRED` (not a promoter) |
| U4 | Quill demotes durable->transient, no approval | `E_APPROVAL_REQUIRED rule=demote` |
| U5 | same with valid approval_id from owner key | ok, approval used_at set, audit records approval_id |
| U6 | shorten expiry by 30 days | approval required |
| U7 | lengthen expiry | ok for Quill |
| U8 | change agent field | `E_FORBIDDEN_FIELD` |
| U9 | edit row with team=scott | approval required |
| U10 | content update containing synthetic token | `E_SECRET_DETECTED`, no change |
| U11 | tags_add "TRK-0099" | stored as trk:0099 |
| M1 | merge 2 same-author rows | survivor keeps id/author; tags union; seen_count summed; member superseded_by set |
| M2 | merge 3 rows, no approval | `E_APPROVAL_REQUIRED rule=bulk` |
| M3 | merge rows of different tiers, tier unset | survivor tier unchanged, flag needs-review |
| M4 | merge includes superseded row | `E_ALREADY_SUPERSEDED` |
| M5 | merge across teams | approval/review flag required |
| M6 | restore after merge | members un-superseded, survivor reverted, audited |
| D1 | digest since date, team=harbor | only harbor events >= since, counts match |
| D2 | digest includes expired | rows with expires_at in window as `expired` |
| D3 | > limit events | next_cursor set; pages concatenate to full set, no dup |
| D4 | naive `since` without tz | `E_INVALID_SINCE` |
| D5 | snippet with secret-like text | redacted in digest |
| D6 | digest with updates | event `updated` with audit_id |
| A1 | non-owner key calls create_memory_approval | `E_OWNER_ONLY` |
| A2 | approval_id reused | `E_APPROVAL_INVALID reason=used` |
| A3 | approval_id expired | `E_APPROVAL_INVALID reason=expired` |
| A4 | approval_id for different params | `E_APPROVAL_INVALID reason=scope` |
| A5 | body says approved_by=scotty, no approval_id | `E_APPROVAL_REQUIRED` |
| S1 | search/list after merge | superseded members hidden |
| S2 | search with include_superseded=true | members returned |
| S3 | get_memory(superseded id) | row returned with superseded_by |
| M7 | merged_content contains synthetic token | `E_SECRET_DETECTED`, no change |
| P1 | prune 3 expired rows | 3 audit rows action=prune, no content, same transaction |
| D7 | digest include pruned | pruned events from audit, counts.pruned=3, no snippet |
| X1 | actor spoof in body | actor taken from hub key; body field ignored |

## 8. Implementation notes (Forge, 2026-11-01)
- Code lives upstream in `/home/scott/.local/share/hermes/shared/` (`quantum_memory_mcp.py`, `quantum_memory.py`); hub `dsect-net/hub-api` only proxies (`lib/mcp-gateway-memory.js`, `lib/mcp-gateway-http.js` ~L415-455) and must expose the new tools with roles.
- DB is SQLite 3.46.1 `quantum_memory.db`; new columns/tables/indexes via `_migrate()` with ALTER ADD COLUMN; take a snap.py snapshot first.
- Hub key records get optional agent/team; proxy forwards `actor_key_id`.
- Approvals: `memory_approvals`, owner-key-only creation, single use, scoped, expiring, audited.
- Superseded rows hidden from search/list/_nearest by default; `get_memory` always returns.
- `prune()` logs to `memory_audit` in-transaction so the digest can show prunes. No prune timer exists today.
- No merges, no Tritium deploys; Forge builds on an experimental branch.

## 9. Open questions
1. The upstream folder may not be under git. Where are these changes committed? (Cooper or Scotty to decide.)
