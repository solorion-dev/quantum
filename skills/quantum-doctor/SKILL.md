---
name: quantum-doctor
version: 1.0.0
description: "Quantum doctor skill. Use when a Quantum service, login, memory recall, or site looks broken. Diagnose with status, memory health, and the last signed note. Do not restart or deploy."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-doctor]
dependencies:
  tools: [dsect_services_status]
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Doctor

Diagnose. Do not treat with a restart unless an operator skill was explicitly handed the host.

## Pass

1. Memory search the symptom. A signed "not verified" or "do not deploy" row outranks a green guess.
2. `memory_health_check` if recall was empty or weird. Embedder down means list-only, not "nothing is stored."
3. `dsect_services_status` `only_problems=true`. Separate known downs from new ones.
4. Name the failing edge: tunnel, auth branch, stale guide cache, missing prep hook. One cause, then the next check.
5. Stop before deploy. `nebula#27` unmerged means a `main` deploy wipes the live auth fix. LTX is not working until a generation completes. Live TV playback is unproven until he confirms Guide Refresh and a stream.

## Close

Write a workspace `working` note: symptom, check, result. Promote to hive `fact` only if the diagnosis is confirmed.
