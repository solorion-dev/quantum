---
name: quantum-systems
version: 1.0.0
description: "Quantum systems skill. Use for Tritium service status, known downs, or adding a new system. Includes the new-system checklist. Read-only on host services unless an operator was handed the restart."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-systems]
dependencies:
  tools: [dsect_services_status]
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Systems

New system is a mode here, not a second skill. One checklist, one status tool.

## Status

1. Memory open on the service name.
2. `dsect_services_status`. Pass `only_problems=true` when he asked what is down.
3. Known downs are not new incidents: claude-rc, ws-axiom archived, mcp-oauth-funnel, quantum-memory-funnel. Say that if they appear.
4. Do not restart, edit a unit, or deploy from this skill. Hand the host command to an operator and say so.

## New system mode

Use when he wants a service added, not when one is merely down.

1. Name, port, box, and who consumes it. Refuse a name that collides with Nebula, Sol, Lightspeed, or Hub.
2. Read `projects/README.md` before a new ABBR. Goal filing is `quantum-goals`.
3. Catalogue it only after it can start. A red row for a service that cannot start trains people to ignore red.
4. Write a hive `fact` with the unit name and the Codex or repo path. No secrets in the row.

## Close

Status residue is `transient` unless a new catalogue decision was made.
