---
description: "Live Quantum map. Read when a /quantum turn names a product, box, rule, or old draft."
connections: []
---

# Quantum map

Recall, then trust a newer signed memory over this file. This is the 2026-10-06 picture.

## What things are

| Name | Is | Is not |
|---|---|---|
| Quantum | The fleet: Tritium host, Codex vault, Quantum Memory, DSECT mail, agent workstations | A single app |
| Tritium | The hub box (mini PC). Host services live here | The laptop |
| Codex | Shared markdown vault. Law in `system/` and the Rules file | The memory database |
| Quantum Memory | One SQLite store. Hive `agent=fleet`. Workspace `agent=<id>`. Private `team=scott` | Codex, and not TRI-008 RAM |
| Nebula | Generation product and site (`nebula.dsect.net`, public tunnel) | FORGE. FORGE is retired |
| Sol | Pretty chat UI on Hermes (TRI-017) | The mail client |
| Lightspeed | Mail client and server | The chat face |
| Hub | `hub.dsect.net`, tailnet-only on purpose (WhoIs breaks if proxied) | The public site |
| Qubit | Manager | A product name |
| Bookkeeper | Vault librarian plus the only durable memory deleter | A second memory store |

## Lanes

Hive facts every agent may read. Workspace notes stay on the writer. Scott-private never goes to a group search.

## Session tools

Memory: `search_memory`, `list_memories`, `add_memory`. Health: `memory_health_check` if a recall looks empty.

Codex: `quantum_codex_list`, `quantum_codex_read`, `quantum_codex_search`, `quantum_codex_write` (overwrite needs `expected_sha256`).

Mail: `quantum_mail_list`, `quantum_mail_read`, `quantum_mail_send`. Send only from your own mailbox.

Services: `quantum_services_status`. Read-only.

GitHub via DSECT: `quantum_github_read_file`. Merge stays Scotty's call.

## Stale on purpose

The 2026-08 skill-creation prompt, per-agent holographic sqlite paths, and the Spark/Vex/Loki roster line are drafts. Do not revive them. Commandments 4, 6, and 10 were rewritten against mail, profile skills, and the hub board.

## Open work already logged

- Nebula LTX-2.5: prep/restore hook around video queue was requested and not finished. Do not call it working.
- `nebula#27` auth fix is live on the branch. A deploy from `main` wipes it. Merge is his.
- Live TV: after a tuner or M3U change, Refresh Guide, not Refresh Channels. Playback unproven until he confirms a stream.
