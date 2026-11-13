---
name: quantum-goals
version: 1.0.0
description: "Quantum goal skill. Use to create, name, or file a Codex goal. Reads projects/README.md before minting an ID. Filename drops brackets and quotes."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-goals]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Goals

Law is `system/project_goal_system.md` and `system/template_goal.md`. Read them before writing. This skill is the procedure.

## Pass

1. Memory search the goal name so you do not mint a second id for work that already has one.
2. Read `projects/README.md`. ABBR comes from that register. Next number is the register's next number, not a commit message.
3. Form: `[ABBR-NNN] "CODENAME" — Short Name`. Codename is one uppercase word, unique across projects.
4. Filename drops brackets and quotes: `NEB-002 CODA — Local Audio Generation.md`. Title and H1 keep the display form. Wiki link uses the filename.
5. File under that project's `goals/` using `system/template_goal.md`. Full vault frontmatter.
6. Update the register row in the same pass. An id only in a commit is not claimed.
7. Single-goal exceptions (no OVERVIEW/ROADMAP) get flagged, not hidden.

## Close

Hive `decision` with the id, codename, and path. Do not paste the whole goal note into memory.
