---
name: quantum-shift
version: 1.0.0
description: "Quantum shift skill. Use when an agent is on duty until a set time, assigned a role from ROLES.md, and must keep working, email progress, park blockers, and send a shift overview at the end."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-shift]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Shift

You are on a shift. The clock ends the shift, not an empty list.

## Open

1. Record start, end, and role. End time is the one he named. If he did not name one, ask once, then do not start.
2. Read the role. Order: the path he gave, then `ROLES.md` in the working repo, then `Agents/Prompts/Roles/` in the Codex. Role file wins over chat memory. Known role names from quantum#24: ANY, RESEARCHER, GAME DEV, JANITOR, SLEEP, OPS. SLEEP means no productive work. Log that and stop.
3. Memory open on the role and the open tasks. Set up a desk: queue, evidence path, mail address for updates. Overnight desk at `~/workspace/overnight-desk/` if that host path exists. Do not invent it.
4. Write the first queue. Pull open todos, goals, and parked items in this role. If the queue is empty, add work that the role file allows. Do not invent a new product.

## Loop

Repeat until the end time.

1. Take the next task in the role. Finish it or park it.
2. Halted means parked, not stopped. Write what blocked it, what you tried, and the next check. Mail that park note. Pick the next task.
3. Email him a progress update at each finished task, and at least every 45 minutes if a task is still running. Use `quantum-mail` from your own mailbox. Subject: `shift <role> <HH:MM>`. Body: done, doing, parked. No secrets.
4. Merge, deploy, restart, and spending stay gated. A shift does not grant them. Retry the same non-destructive step without re-asking. That is memory 726.
5. Five minutes before the end, stop starting new tasks.

## Close

1. Audit the shift against the queue. Done, parked, untouched. Do not claim a check you did not run.
2. Email the shift overview: window, role, done, parked, evidence paths, what the next shift should pick up.
3. Write a hive `note` with the overview path and the mail subject. Queue residue stays workspace.

Role shape is `references/roles.md`.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
