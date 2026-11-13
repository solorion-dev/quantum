# Cooper local twin (pre-reconciliation)

Seeded from Codex `quantum-systems`; this is the divergent local copy (`local-quantum-systems`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# Quantum Systems

New system is a mode here, not a second skill. One checklist, one status tool.

## Status

- Open memory on the service name before probing, so a known down is not reported as a new incident.

- Run `dsect_services_status` for the status check and pass `only_problems=true` when the user asked what is down.

- Treat claude-rc, ws-axiom archived, mcp-oauth-funnel and quantum-memory-funnel as known downs, not new incidents, and say so if they appear.

- Do not restart, edit a unit, or deploy from this skill. Hand the host command to an operator and say so.

## Stop or restart one process safely

- Identify the exact target before any stop or restart, using its listener, its PID file, or its systemd unit, and record the full command line and PID of that one process.

- Never stop a process with a name or command pattern match such as `pkill -f` or `pgrep -f` against a shared term like a script name, because one pattern can match many fleet services and the shell running the command itself.

- List every process the chosen identifier matches before acting, and stop and re-identify the target if the list holds anything beyond the one intended process.

- Prefer the systemd unit for a service restart so the stop, the start and the restart policy stay with the unit that owns the process.

- Verify after the action that only the intended process changed state, then re-check the affected service on the path the user actually uses before calling it back.

- Carry this exact-PID rule into every subagent brief that includes stopping or restarting a process, because a delegated agent runs the same commands with the same blast radius.

## New system mode

Use when the user wants a service added, not when one is merely down.

- Name the service, its port, its box, and who consumes it, and refuse a name that collides with Nebula, Sol, Lightspeed, or Hub.

- Read `projects/README.md` before minting a new abbreviation, and file the goal with the quantum-goals skill.

- Catalogue the service only after it can start, because a red row for a service that cannot start trains people to ignore red.

- Write a hive `fact` with the unit name and the Codex or repo path, and keep secrets out of the row.

## Close

- Keep status residue `transient` unless a new catalogue decision was made.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Route a single named service that looks down through the service chain diagnosis skill, which traces the user path hop by hop before any restart is considered.

- Leave a process running and report the exact target and the proposed action when the identifier cannot be narrowed to one process with confidence.
