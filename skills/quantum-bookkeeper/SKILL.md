---
name: quantum-bookkeeper
version: 1.0.0
description: "Quantum Bookkeeper entry. Use to file, lint, or fold Codex notes, or to fold Quantum Memory dupes. Canonical vault work is Skills/codex-bookkeeper. Do not durable-delete memory."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-bookkeeper]
dependencies:
  tools: [list_memories]
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Bookkeeper

Load `Skills/codex-bookkeeper/SKILL.md` for vault triage, frontmatter, filenames, and the dated report. This file only adds the fleet rules that skill does not own.

Older bookkeeper notes (inaugural 2026-08 scan, holographic FactStore) are drafts. The live skill and `system/memory_doctrine.md` win.

## Memory fold

1. Open with `list_memories` `agent=fleet` `tier=durable` `order_by=recent`.
2. Near-dupes get a fold note, not a second durable row. `add_memory` already folds near-identical content.
3. Two live decisions that contradict: write a `correction` naming both ids. Do not delete either.
4. Expired rows: `prune_memories` dry-run first. `confirm=true` only on an assigned bookkeeper pass.
5. Durable delete of a live row is Bookkeeper-only, and still not this session unless Scotty assigned the delete.

## Close

Report path stays `Bookkeeping/reports/YYYY-MM-DD Bookkeeper Report — <agent>.md`. Memory one-liner goes to hive `kind=note` with that path. No balances in the stamp.
