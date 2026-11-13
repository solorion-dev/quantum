---
name: quantum-todos
version: 1.0.0
description: "Shared Quantum todo skill. Use to file a fleet-visible task and notify another agent by DSECT mail. Others read the Codex note. Does not replace goals."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-todos]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Todos

A todo other agents can see is a Codex note plus a mail ping. A goal is heavier. Use `quantum-goals` if the work needs an ABBR.

## Pass

1. Memory search so you do not file a duplicate of an open request.
2. Write `planning/todos/YYYY-MM-DD <short>.md` with vault frontmatter, owner, status (`open|doing|done`), and the ask in one paragraph. Folder must exist. If the write refuses, file under `planning/` with the same name pattern.
3. Mail the owner with `quantum-mail`: subject is the todo title, body is the path and the ask. No secrets.
4. Status changes edit that note (`expected_sha256` from a read). Do not stack a second file.

## Close

Workspace `working` row with the path and the mail uid. Hive only if the todo became a decision.
