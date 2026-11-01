# SPEC-3: Quantum Memory write guardrails (draft v0.2, Quill, 2026-11-01)

Status: DRAFT v0.2, updated with Forge's server answers; ready for Forge to implement on an experimental branch. No server code changed. Basis: Tag Scheme & Tier Criteria v0.3 (D1-D7), standing rule #2267.

## 1. Current shape (observed via the MCP proxy schema)
- Tool: `add_memory` (proxied as `memory_add_memory`). Args: `content` (required), `agent` (default `"fleet"`), `kind` (default `"note"`), `tier` (enum transient|project|durable, default `"transient"`), `importance` (0.5), `tags` (list|null), `team` (null).
- Near-duplicate content is folded into an existing row (seen_count bumped).
- The server source is NOT in `solorion-dev/quantum`. Write path (Forge): hub proxy `add_memory` -> upstream `quantum_memory_mcp.py add_memory` -> `QuantumMemory.remember()` (see Implementation notes).
- Problems: defaults `agent=fleet` (invalid author per D3), `team=null`, `kind=note`, `tier=transient`, `importance=0.5` silently apply; the existing secret check (`_secret_hit`) returns `status: skipped` with no error, so callers think the write succeeded.

## 2. Required changes
1. Make `agent`, `team`, `tier` effectively required. Change the `add_memory` parameter defaults (`agent`, `kind`, `tier`, `importance`) to `Optional = None` and resolve them in the handler: `kind`->`note`, `importance`->0.5 still default; missing `agent`/`team`/`tier` go through the checks in section 3.
1a. Author identity: upstream takes the actor from the hub proxy (`actor_key_id`, key-bound `agent`/`team`), never from the client's `agent` argument, because the hub uses one shared upstream token. Direct (non-hub) callers such as snap.py, scripts and the CLI must pass `agent` explicitly and are validated the same way.
2. Validate against allowlists (config): teams `quantum, fleet, apogee, harbor, scott`; agents per tag doc + `antigravity`; `fleet`/`quantum` rejected as agents (D3).
3. Content prefix check: `content` should start with `[team:<team>] [agent:<agent>]` matching the fields. Mismatch -> warn (or reject in strict mode).
4. Normalize tags: lowercase, kebab-case, dedupe, `TRK-0173` -> `trk:0173`.
5. Secret scan on `content` and `tags` before the near-dup fold and embedding (`_secret_hit` already runs there); a hit becomes an error response (`E_SECRET_DETECTED`), not `status: skipped`.
6. Layering: must-hold checks live upstream (in `remember()` / the MCP handler) because snap.py, scripts and the CLI bypass the hub. The proxy additionally does cheap schema, size and required-tier checks and injects the actor.

## 3. Reject vs warn policy
Each check has its own flag (`off` / `warn` / `enforce`, section 6); the columns show behaviour per mode. The secret scan has no warn phase for high-confidence hits.
| Check | `enforce` mode (target) | `warn` mode (migration) |
|---|---|---|
| team missing/null | REJECT `E_MISSING_TEAM` | accept, default to agent's home team, add tag `needs-review`, warning |
| agent missing / `fleet` / `quantum` (direct callers) | REJECT `E_MISSING_AGENT` / `E_INVALID_AGENT` | REJECT (never default author) |
| tier missing | REJECT `E_MISSING_TIER` | accept as `project` + `needs-review`, warning (never silent transient) |
| tier not in enum | REJECT `E_INVALID_TIER` | REJECT |
| team/agent not on allowlist | REJECT `E_UNKNOWN_TEAM`/`E_UNKNOWN_AGENT` | warn + `needs-review` |
| content prefix missing/mismatched | warn `W_PREFIX` | warn |
| secret, high-confidence pattern | REJECT `E_SECRET_DETECTED` | REJECT (always) |
| secret, entropy-only hit | warn `W_POSSIBLE_SECRET` (stored, tagged `secret-review`) | same |
| hub key agent/team != args.agent/team | REJECT `E_ACTOR_MISMATCH` | proxy overwrites args with key-bound values + `W_ACTOR_OVERRIDDEN` |
| oversize content (proxy) | REJECT `E_TOO_LARGE` | REJECT |
| unnormalized tags | fix silently, `W_TAGS_NORMALIZED` info | same |

Rejected and warned writes store nothing extra, embed nothing (on reject), and log one `memory_audit` row (SPEC-4 section 3) with action `write_rejected`/`write_warned`, code, actor, actor_key_id, team and content_hash only (never the content or the matched value). This audit log is what the warn->enforce review reads.

## 4. Secret scan
High-confidence patterns (reject):
- Private key blocks: `-----BEGIN [A-Z ]*PRIVATE KEY-----`
- Known token prefixes: `ghp_|gho_|ghu_|ghs_|ghr_|github_pat_` + 20+ chars; `xox[abprs]-`; `sk-[A-Za-z0-9]{20,}`; `AKIA[0-9A-Z]{16}`; `AIza[0-9A-Za-z_-]{35}`; JWTs `eyJ[\w-]+\.[\w-]+\.[\w-]+` (HA long-lived tokens are JWTs).
- Assignments: `(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)\s*[:=]\s*\S{8,}` where the value is not a placeholder.
- Bearer headers: `Authorization:\s*Bearer\s+\S{16,}`.
- URLs with credentials: `\w+://[^/\s:]+:[^@\s]+@`.
Entropy heuristic (warn): tokens >= 24 chars of `[A-Za-z0-9+/=_-]` with Shannon entropy >= 4.0 bits/char.
Allowlist (no hit): 40-char hex git SHAs and 7-12 char short SHAs when near "commit"/"@"/"sha"; UUIDs; `$ENV_VAR` / `${VAR}` names; mentions of a secret by name only (e.g. "stored as box secret HA_TOKEN"); placeholders `<redacted>`, `***`, `xxxx`, `changeme`, `example`; URLs without userinfo; Drive/Docs file ids inside `docs.google.com`/`drive.google.com` URLs.

## 5. Error / response shapes
Reject:
```json
{"ok": false, "error": {"code": "E_MISSING_TEAM", "field": "team",
  "message": "team is required; one of quantum, fleet, apogee, harbor, scott",
  "hint": "prefix content with [team:X] [agent:Y] and pass team, agent, tier"}}
```
Secret reject: `{"ok": false, "error": {"code": "E_SECRET_DETECTED", "field": "content", "detector": "github_pat", "span": [120, 160], "message": "possible credential; remove it and refer to the secret by name"}}` (span only, never the value).
Accept with warnings:
```json
{"ok": true, "id": 2400, "folded_into": null, "tier": "project",
 "warnings": [{"code": "W_PREFIX", "message": "content prefix [team:harbor] [agent:quill] missing"}]}
```

## 6. Config flags (env), one per check
| Flag | Default | Meaning |
|---|---|---|
| `QM_GUARD_TEAM` | `warn` | off / warn / enforce |
| `QM_GUARD_AGENT` | `warn` | off / warn / enforce (missing/collective agent rejects in both on modes) |
| `QM_GUARD_TIER` | `warn` | off / warn / enforce |
| `QM_GUARD_ALLOWLIST` | `warn` | off / warn / enforce |
| `QM_GUARD_PREFIX` | `warn` | off / warn / enforce |
| `QM_GUARD_ACTOR` | `warn` | off / warn / enforce (hub key mismatch) |
| `QM_SECRET_SCAN` | `enforce` | starts in enforce (it already blocks writes today); off only in tests |
| `QM_TEAM_ALLOWLIST` | `quantum,fleet,apogee,harbor,scott` | |
| `QM_AGENT_ALLOWLIST` | from tag doc | |
| `QM_AGENT_HOME_TEAM` | path to JSON map | used for warn-mode defaulting |
| `QM_SECRET_ENTROPY_MIN` | `4.0` | bits/char |
| `QM_SECRET_MIN_LEN` | `24` | |
| `QM_PROXY_MAX_BYTES` | `20000` | proxy size check |

Rollout (Forge #10): each check runs in `warn` for at least 7 days AND 200 writes; it may move to `enforce` once false positives are < 1% (reviewed from `memory_audit`) and there are zero misses on the synthetic secret test set. Helm recommends; Scotty decides per check; flipping one flag back rolls it back.

## 7. Test cases
| # | Case | Input (abridged) | Mode | Expected |
|---|---|---|---|---|
| T1 | pass | team=harbor agent=quill tier=project, prefixed | enforce | ok, no warnings |
| T2 | missing team | team omitted | enforce | `E_MISSING_TEAM` |
| T3 | missing team | team omitted, agent=quill | warn | ok, team=harbor, tag needs-review, warning |
| T4 | missing agent | agent omitted | both | `E_MISSING_AGENT` |
| T5 | collective agent | agent=fleet | both | `E_INVALID_AGENT` |
| T6 | missing tier | tier omitted | enforce | `E_MISSING_TIER` |
| T7 | missing tier | tier omitted | warn | ok, tier=project, needs-review |
| T8 | invalid tier | tier=permanent | both | `E_INVALID_TIER` |
| T9 | unknown team | team=dsect | enforce | `E_UNKNOWN_TEAM` |
| T10 | prefix mismatch | field team=harbor, prefix [team:apogee] | enforce | ok + `W_PREFIX` |
| T11 | GitHub PAT | content has `ghp_` + 36 chars (synthetic) | both | `E_SECRET_DETECTED` detector=github_pat; nothing stored |
| T12 | private key | `-----BEGIN OPENSSH PRIVATE KEY-----` | both | reject |
| T13 | JWT | synthetic `eyJ...` three-part | both | reject |
| T14 | password assignment | `password: hunter2hunter2` | both | reject |
| T15 | creds in URL | `https://u:p4ssw0rd@host` | both | reject |
| T16 | entropy only | 32-char random base64 with no keyword | both | ok + `W_POSSIBLE_SECRET`, tag secret-review |
| FP1 | git SHA | "merged at 09f3e0d", 40-hex commit | both | ok, no secret warning |
| FP2 | secret by name | "Stored as box secret HA_TOKEN ($HA_TOKEN)" | both | ok |
| FP3 | placeholder | `token: <redacted>` | both | ok |
| FP4 | UUID | goal/session UUID | both | ok |
| FP5 | Drive URL | docs.google.com/document/d/<id>/edit | both | ok |
| FP6 | word "password" | "rotate the password next week" | both | ok |
| T17 | tag normalize | tags ["TRK-0173","Foo Bar","foo-bar"] | both | ["trk:0173","foo-bar"], info |
| T18 | rejected write logging | T11 input | both | log row has code + content hash only |
| T19 | fold path | duplicate of T1 | both | guardrails run before fold; ok, folded_into=id |
| T20 | defaults resolved in handler | kind, importance omitted | enforce | ok, kind=note, importance=0.5 stored |
| T21 | secret hit is an error | T11 input | both | `ok:false` + `E_SECRET_DETECTED`, never `status: skipped` |
| T22 | hub actor injection | hub key bound to quill; args.agent omitted | both | stored agent=quill, actor_key_id passed upstream |
| T23 | hub actor spoof | key bound to quill; args.agent=forge | enforce | `E_ACTOR_MISMATCH`, nothing stored |
| T24 | hub actor spoof | same as T23 | warn | stored agent=quill + `W_ACTOR_OVERRIDDEN` |
| T25 | bypass path | direct upstream call (CLI/snap.py) with agent omitted | enforce | `E_MISSING_AGENT` (upstream enforces without the hub) |
| T26 | proxy size check | content > `QM_PROXY_MAX_BYTES` | both | `E_TOO_LARGE` at proxy, no upstream call |
| T27 | per-check flags | `QM_GUARD_TEAM=enforce`, `QM_GUARD_PREFIX=warn`, team omitted + bad prefix | mixed | `E_MISSING_TEAM` |
| T28 | flag off | `QM_GUARD_PREFIX=off`, bad prefix | off | ok, no `W_PREFIX` |
| T29 | audit of reject | T2 input | enforce | `memory_audit` row action=write_rejected, code, content_hash, no content |

All secret fixtures must be synthetic and generated at test time (no real-looking live credentials committed).

## 8. Implementation notes (Forge, 2026-11-01)
- Hub (`dsect-net/hub-api`, branch main) is a proxy only: `lib/mcp-gateway-memory.js` (`createMemoryProxy`, `callHubTool`); call handler in `lib/mcp-gateway-http.js` ~L415-455 does role checks and audit; `add_memory` requires the developer role.
- Real logic is upstream in `/home/scott/.local/share/hermes/shared/`: `quantum_memory_mcp.py` `add_memory` (~L295, port 8083) -> `QuantumMemory.remember()` in `quantum_memory.py` (~L447). `_secret_hit` is at ~L184 and runs before the embedding fold.
- Defaults move to `Optional=None`, resolved in the handler. Must-hold checks upstream; proxy does schema/size/required-tier + actor injection.
- Hub key records (`lib/mcp-gateway-keys.js`) gain optional `agent` and `team`; proxy overwrites or rejects mismatched `args.agent` and forwards `actor_key_id`.
- Storage/audit: see SPEC-4 section 8 (SQLite, `memory_audit` via `_migrate()`, snap.py snapshot first).
- Rollout flags per section 6. No merges, no Tritium deploys; Forge builds on an experimental branch.

## 9. Open questions
1. The upstream folder `/home/scott/.local/share/hermes/shared/` may not be under git. Where are these changes committed? (Cooper or Scotty to decide.)
