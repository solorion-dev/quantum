---
name: local-tracker-github-sync
description: Use when running, planning, resuming, or reporting the Tracker→GitHub sync — mirroring Tracker records to GitHub issues, doing a sync dry-run or apply, handling close-pending items, or checking what a sync run did. The Tracker on Tritium is the source of truth; GitHub is a one-way mirror.
---

# Tracker → GitHub Sync Operator

## Doctrine
One-way only. Tracker state flows out to GitHub issues; nothing on GitHub — no close, no edit, no comment — ever flows back through this sync. The design lives at `~/workspace/goals/tracker-to-github-sync-for-goals-and-tasks/files/DESIGN.md`; read it before any run. Draft tooling: `~/workspace/tracker-build/github_sync.py` (dry-run by default). Record: TRK-0235.

## Before any run
1. **Re-plan from the live DB.** Dry-run numbers go stale within hours — on Oct 21 the DB moved 233 → 243 records between the dry-run and the approved apply. Never execute a frozen plan; regenerate and report the delta.
2. Apply runs only on Scotty's explicit call, and he sets the width (full backlog vs open-only). Done items are create-then-close-for-history only when he says so.
3. Confirm the bridge is healthy on the named surface (`memory_health_check` or a GitHub list call returns real data) before starting.

## Execution rules
- **Bridge only:** `python3 ~/workspace/custom-connectors/custom.legacy-tritium-mcp/bin/mcp.py call quantum_github_* '<json>'`, every write with `"agent": "cooper"`. Never the `gh` CLI (cooper-the-fox is suspended), never the per-call-approval connector CLI — Scotty banned the approval-card path.
- **Solo-bridge rule:** one agent against the bridge at a time, calls serial. On "Session superseded," back off and retry serially — never parallelize around it.
- **Link-back idempotency:** immediately after GitHub confirms a create, write the mapping into the Tracker (a `links` row, kind `github_issue`, plus a sync event) before the next op. A run that dies halfway must be resumable without duplicates.
- **Marker dedupe:** every mirrored issue body ends with `<!-- tracker:TRK-#### -->`. Before any CREATE, search the target repo for the marker and ADOPT a hit instead of creating.
- **Mirror set:** kinds goal/issue/task/bug/milestone only. Exclude `source='github-sync'` items (the inbound pull owns them), decisions and notes, items whose external_ref points at a PR, and anything tagged `no-github`. Cancelled-and-never-mirrored = SKIP, counted in the plan so the gap is visible.
- **Routing:** default repo `dsect-net/quantum`; a `repo:<name>` tag routes a CREATE to `dsect-net/<name>`. Mapped items always sync to the repo their mapping names.
- **Ordering:** ADOPTs, then CREATEs parents-before-children, then SYNCs, then SKIPs.
- **No board writes in v1.** The bridge has no reliable project-item tool for this; `status:*` labels carry the board-visible state.

## The close gap
The bridge has **no issue edit/close tool**. Closes therefore degrade, honestly:
- Post the completion comment ("Closed per Tracker TRK-#### — status done").
- Put every such issue on a **close-pending list** in the run report for Scotty's browser pass.
- Never report an item closed that only has a comment. "Created + commented + close-pending" is the truthful status.

## Verify before reporting
1. Count Tracker records carrying `github_issue` links vs the plan.
2. Spot-read 3 created issues through the bridge (one open, one done-history, one sync target): marker + labels present.
3. Report: final plan numbers, delta vs dry-run, created / synced / skipped counts, the full close-pending list, and any failures with where the run stopped.
4. Comment the outcome on TRK-0235 and set its status to match reality (in_review while close-pending remains).
