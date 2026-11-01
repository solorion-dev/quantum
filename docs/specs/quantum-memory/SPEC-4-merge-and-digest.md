# SPEC-4: Memory merge/update tool + digest-since-date (draft v0.1, Quill, 2026-11-01)

Status: DRAFT for Forge review. No server code changed. Basis: Tag Scheme v0.3 (D6, D7, "fix tiers before dedupe" #346, "survivor tier only after review").

## 1. Gaps today
No get-by-id, no update, no merge, no change log; `list_memories` truncates around 20 KB; `prune_memories` deletes only expired rows.

## 2. New tools
### 2.1 `get_memory(id) -> Memory` (helper, read-only)

### 2.2 `update_memory`
```json
{"id": 2271, "actor": "quill", "team": "harbor",
 "changes": {"tier": "durable", "tags_add": ["decision"], "tags_remove": [],
             "content": null, "importance": null, "expires_at": null, "kind": null},
 "reason": "standing decision, D7 promotion",
 "approval": {"approved_by": null, "evidence": null},
 "dry_run": true}
```
Rules: never changes `agent` (author) or `created_at`; `team` change only via re-attribution (D3) with reason; tags are add/remove only and normalized (SPEC-3); new content goes through SPEC-3 guardrails + secret scan; `dry_run` defaults true.
Response: `{"ok": true, "dry_run": true, "id": 2271, "diff": {...before/after...}, "approval_required": false, "audit_id": null}`

### 2.3 `merge_memories`
```json
{"ids": [101, 102, 103], "survivor_id": 101, "actor": "quill",
 "merged_content": null, "tier": null, "reason": "dup cluster 33.1",
 "approval": {"approved_by": null, "evidence": null}, "dry_run": true}
```
Rules: survivor keeps its id, author, created_at; tags = normalized union; seen_count = sum; importance = max; `merged_from` = ids; tier = survivor's unless `tier` set explicitly (never auto-highest); expires_at = latest of members unless explicitly set; members are soft-deleted (`superseded_by` = survivor), not hard-deleted; a merge across different teams or authors requires review flag; a member already superseded is rejected.

### 2.4 `memory_digest`
```json
{"since": "2026-10-25T00:00:00-04:00", "until": null, "team": "harbor", "agent": null,
 "tier": null, "include": ["created","updated","merged","expired","pruned"],
 "format": "summary", "limit": 200, "cursor": null}
```
Response:
```json
{"since": "...", "counts": {"created": 41, "updated": 6, "merged": 2, "expired": 7},
 "items": [{"id": 2312, "event": "created", "at": "...", "team": "harbor", "agent": "quill",
            "tier": "project", "snippet": "first 200 chars"}],
 "next_cursor": null}
```
Paginated by cursor to avoid the ~20 KB truncation. Snippets pass through the secret scan redactor. `since` required; timezone-aware ISO 8601.

## 3. Audit trail
New table `memory_audit(audit_id, at, actor, actor_team, action[update|merge|retier|restore], memory_id, before_json, after_json, reason, approved_by, approval_evidence, dry_run)`. Append-only, written in the same transaction as the change. `restore_memory(audit_id)` reverts one change (itself audited; restores that shorten expiry follow the same approval rules).

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

"Needs Scotty" means `approval.approved_by = "scotty"` and `approval.evidence` points to his own message (link or message id). The server records it; an agent relaying "Scotty agreed" does not count; Forge should decide whether the server can verify evidence or only records it (open question). Without approval the call returns `E_APPROVAL_REQUIRED` and changes nothing (dry run diff still returned).
Actor identity must come from the authenticated MCP key, not the request body, when available.

## 5. Errors
`E_NOT_FOUND`, `E_APPROVAL_REQUIRED {rule}`, `E_FORBIDDEN_FIELD {field: agent|created_at}`, `E_ALREADY_SUPERSEDED`, `E_SECRET_DETECTED` (SPEC-3), `E_INVALID_SINCE`, `E_TOO_MANY_IDS`.

## 6. Config
`QM_MERGE_MAX_IDS` (default 10), `QM_BULK_THRESHOLD` (2), `QM_PROMOTERS` (`cooper,quill`), `QM_APPROVER` (`scotty`), `QM_PROTECTED_TEAMS` (`scott`), `QM_DIGEST_PAGE` (200).

## 7. Test cases
| # | Case | Expected |
|---|---|---|
| U1 | update dry_run default | diff returned, no change, no audit row (or audit dry_run=true) |
| U2 | Quill promotes project->durable | ok, expires_at null, audit row with before tier |
| U3 | Volt promotes to durable | `E_APPROVAL_REQUIRED` (not a promoter) |
| U4 | Quill demotes durable->transient, no approval | `E_APPROVAL_REQUIRED rule=demote` |
| U5 | same with approved_by=scotty + evidence | ok, audit records evidence |
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

## 8. Open questions for Forge
1. Server location and DB (SQLite/Postgres?) for the audit table and soft delete columns (`superseded_by`, `merged_from`).
2. Can actor identity come from the MCP key (quill-mcp-key etc.)?
3. How should Scotty's approval be evidenced and checked?
4. Should search/list hide superseded rows by default (proposed yes)?
5. Do prune events need to be logged now so the digest can show them?
