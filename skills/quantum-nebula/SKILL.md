---
name: quantum-nebula
version: 1.0.0
description: "Nebula skill for Quantum. Use for nebula.dsect.net, LTX-2.5, ComfyUI video queue, or Nebula login. Do not deploy from main while nebula#27 is the live auth fix. Do not call LTX working until a generation completes."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-nebula]
dependencies:
  tools: [search_memory]
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Nebula

Nebula is the generation product. FORGE is retired. Recall before acting. Memory 722 (2026-10-07) supersedes earlier "password never set" if they conflict: he set one via Secure Vault, and it did not sync to users.db.

## Pass

1. `search_memory` on Nebula, LTX, and dsect-auth. Newer signed row wins.
2. Do not deploy from `main` while the live server is on the `nebula#27` fix branch. A main deploy wipes that fix. Merge is Scotty's call.
3. Login: Secure Vault does not write `users.db`. Do not pull a password out of the vault. He re-supplies it on a channel that can hash into `/home/scott/.config/dsect-auth/users.db`, then an end-to-end login test.
4. LTX-2.5 workflows may exist under ComfyUI. Prep script is `/home/scott/nebula-ltx25/ltx-prep.sh`. The open request is to run prep when a video is queued and restore `llama-qwen` and `comfyui` when it finishes. Not done until a generation completes.
5. `nebula#28` mobile workflow picker is UI-only and needs his visual review before merge.

## Close

Hive `fact` only if you verified a generation or a login. Otherwise a workspace `working` note.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
