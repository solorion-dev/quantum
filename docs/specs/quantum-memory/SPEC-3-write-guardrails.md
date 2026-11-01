# SPEC-3: Quantum Memory write guardrails (draft v0.1, Quill, 2026-11-01)

Status: DRAFT for Forge review. No server code changed. Basis: Tag Scheme & Tier Criteria v0.3 (D1-D7), standing rule #2267.

## 1. Current shape (observed via the MCP proxy schema)
- Tool: `add_memory` (proxied as `memory_add_memory`). Args: `content` (required), `agent` (default `"fleet"`), `kind` (default `"note"`), `tier` (enum transient|project|durable, default `"transient"`), `importance` (0.5), `tags` (list|null), `team` (null).
- Near-duplicate content is folded into an existing row (seen_count bumped).
- The server source is NOT in `solorion-dev/quantum` (formerly dsect-net/quantum; repo holds the app, `services/notekeeper`, `services/singularity`, `tools/`). Forge to confirm the file/function for `add_memory` (likely the Python MCP server on Tritium, the "QuantumMemory()" write path).
- Problems: defaults `agent=fleet` (invalid author per D3), `team=null`, and `tier=transient` silently apply; no secret scan.

## 2. Required changes
1. Make `agent`, `team`, `tier` effectively required: an omitted value is treated as missing (the server must distinguish "omitted" from "default"; switch defaults to `null`).
2. Validate against allowlists (config): teams `quantum, fleet, apogee, harbor, scott`; agents per tag doc + `antigravity`; `fleet`/`quantum` rejected as agents (D3).
3. Content prefix check: `content` should start with `[team:<team>] [agent:<agent>]` matching the fields. Mismatch -> warn (or reject in strict mode).
4. Normalize tags: lowercase, kebab-case, dedupe, `TRK-0173` -> `trk:0173`.
5. Secret scan on `content` and `tags` before embedding/storing.

## 3. Reject vs warn policy
| Check | `enforce` mode (target) | `warn` mode (migration) |
|---|---|---|
| team missing/null | REJECT `E_MISSING_TEAM` | accept, default to agent's home team, add tag `needs-review`, warning |
| agent missing / `fleet` / `quantum` | REJECT `E_MISSING_AGENT` / `E_INVALID_AGENT` | REJECT (never default author) |
| tier missing | REJECT `E_MISSING_TIER` | accept as `project` + `needs-review`, warning (never silent transient) |
| tier not in enum | REJECT `E_INVALID_TIER` | REJECT |
| team/agent not on allowlist | REJECT `E_UNKNOWN_TEAM`/`E_UNKNOWN_AGENT` | warn + `needs-review` |
| content prefix missing/mismatched | warn `W_PREFIX` | warn |
| secret, high-confidence pattern | REJECT `E_SECRET_DETECTED` | REJECT (always) |
| secret, entropy-only hit | warn `W_POSSIBLE_SECRET` (stored, tagged `secret-review`) | same |
| unnormalized tags | fix silently, `W_TAGS_NORMALIZED` info | same |

Rejected writes store nothing, embed nothing, and log only the error code, agent, team, and a hash of the content (never the content or the matched value).

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

## 6. Config flags (env)
| Flag | Default | Meaning |
|---|---|---|
| `QM_GUARD_MODE` | `warn` -> `enforce` after migration | warn / enforce / off |
| `QM_TEAM_ALLOWLIST` | `quantum,fleet,apogee,harbor,scott` | |
| `QM_AGENT_ALLOWLIST` | from tag doc | |
| `QM_AGENT_HOME_TEAM` | path to JSON map | used for warn-mode defaulting |
| `QM_SECRET_SCAN` | `on` | on/off (off only in tests) |
| `QM_SECRET_ENTROPY_MIN` | `4.0` | bits/char |
| `QM_SECRET_MIN_LEN` | `24` | |
| `QM_REQUIRE_PREFIX` | `warn` | warn / reject |

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

All secret fixtures must be synthetic and generated at test time (no real-looking live credentials committed).

## 8. Open questions for Forge
1. Where does `add_memory` live (repo/path/function)? It is not in solorion-dev/quantum.
2. Can the server tell "omitted" from "default" (FastMCP defaults)? Proposal: defaults -> null.
3. Does the proxy (`memory_*` names) need the same validation, or only upstream?
4. Scan before or after the near-dup fold? Spec says before.
5. Rollout: how long in `warn` before `enforce`, and who flips it (Scotty?).
