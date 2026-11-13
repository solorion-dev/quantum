# Cooper local twin (pre-reconciliation)

Seeded from Codex `quantum`; this is the divergent local copy (`local-quantum`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# Quantum — fleet entry

`/quantum <ask>` means this skill, then a memory open, then the matching child skill. Do not answer a Quantum question from chat memory alone.

Older drafts (2026-08 skill-creation prompt, holographic sqlite paths, retired roster names, FORGE) are historical. Live docs and a memory hit win. If they disagree, say so and follow the newer signed row.

## Open (required)

1. `search_memory` on the user's ask, `k=5`, `min_importance` 0.4. Also `list_memories` `agent=fleet` `tier=durable` `order_by=recent` `limit=8`, and the same for your own agent id.
2. Embedder down: list only, and say so. Do not invent a recall.
3. Read `references/map.md` in this skill if the ask names a product, box, or rule. Codex path: `Skills/quantum/references/map.md`. Vault law: `system/memory_doctrine.md`, `system/memory_rules.md`, `Quantum Codex Rules and Guidelines.md`.
4. Route:

| Ask | Skill |
|---|---|
| What is X, where does it live, /quantum start | stay here |
| Service up/down, add a service | `quantum-systems` |
| Something is broken | `quantum-doctor` |
| @dsect.net mail | `quantum-mail` |
| Nebula, LTX, generation login | `quantum-nebula` |
| Login, tunnel versus tailnet, dsect-auth | `quantum-auth` |
| Issues, draft PRs, merge | `quantum-github` |
| Jellyfin, M3U, Live TV | `quantum-live-tv` |
| New goal, codename, register | `quantum-goals` |
| Shared todo, hand a task to another agent | `quantum-todos` |
| File, lint, fold notes or memory dupes | `quantum-bookkeeper` |

## Close (required)

Write what changed.

- Decision or product fact: `add_memory` `agent=fleet` `team=quantum` `tier=durable` `kind=decision|fact`. First line `Signed <agent-id> <date>`.
- Mid-task residue: your agent id, `tier=transient` or `project`. Not the hive.
- Family, health, money: `team=scott`. Never a group recall.
- Supersede. Do not stack a dead name next to the live one. Bookkeeper is the only durable deleter.
- No secrets, tokens, or balances in memory.
- Codex note only if another agent or Scotty needs the file. Memory holds the one-liner plus the path.

Grok's agent id is `grok-tessa`. Stamp that, not `grok-apogee`.

## Do not

- Deploy Nebula from `main` while `nebula#27` is the live auth fix and unmerged. Merge is Scotty's call.
- Call LTX-2.5 working until a generation completes.
- Treat a known down (claude-rc, ws-axiom archived, mcp-oauth-funnel, quantum-memory-funnel) as a new incident.
- Restart a host service from this skill. Status is read-only here.

## Knowledge graph

Start at `references/map.md`. Child skills are separate directories under `Skills/`.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
