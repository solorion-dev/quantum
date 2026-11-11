---
name: local-night-wave
description: Use when Scotty asks to slam out work, run a wave of parallel agents, work the board down overnight, or triage a backlog into delegated workstreams. Covers census → triage against the fences → tight per-workstream subagent briefs → handoff integration with artifact verification → UPDATES.md detail + headline-only chat → morning summary.
---

# Night-Wave Coordination

## Stance
Delegate by default: subagents do the hands-on work; the coordinator keeps verification against artifacts, decisions, synthesis, and the conversation with Scotty. A wave that leaves the coordinator heads-down in one task has misused itself.

## 1. Census before dispatch
- Count the board, never sample it: tracker list/count gives totals (search snippets lie both ways — phantom hits and false empties).
- Sort open items into four piles: **agent-tackle-able**, **needs Scotty** (his decision, his hands, his accounts), **stale** (superseded, duplicated, or overtaken — correct or cancel on evidence), **closable now** (the outcome already happened; close with the evidence cited).

## 2. Triage against the fences
Never delegate, at any wave size: purchases or spending, messages to other people, health/leave/PFML actions, credential or security changes, significant deletions, anything irreversible. Park those with the gate named in one line. Volume never outranks the fences. Credential-adjacent surprises inside a workstream (e.g. an agent minting a key to finish its task) get flagged to Scotty prominently, not buried in a report.

## 3. Briefs
One agent per workstream. Every brief is self-contained and carries:
- The record to read first (tracker `context <id>` pack) — work starts from the record, not from chat memory.
- "Update your Tracker record live as you work."
- Verify against the artifact (files, git, live surfaces), name the surfaces you checked, and label anything unverified as unverified.
- The fences that apply to that workstream, stated explicitly.
- A deliverable file in the night's folder (`~/workspace/tonight-YYYY-MM-DD/`) plus a compact return summary.

## 4. Integration — handoffs are reports, not artifacts
- Verify load-bearing claims against the artifact before they ship anywhere user-facing. Interim/preview figures are UNVERIFIED until the final report or the artifact supersedes them.
- **Fabrication red flag:** rich, specific "live" detail produced during a window when the target was verifiably unreachable = quarantine the report and re-check against the live system (Oct 21: a Qubit recon full of pids and journal lines, produced while Tritium was down — every claim false). When two reports contradict each other, ship neither; record the gap as a gap.
- When a diagnosis conveniently closes a loop, distrust it once more and check the artifact anyway.

## 5. Documentation and chat discipline
- Every completed workstream lands twice: a comment on its Tracker record, and a section in the night's `UPDATES.md` with the evidence.
- Chat stays short (Scotty's rule, Oct 21): headline + the one fact that matters, a line or three. Full explanations live in UPDATES.md and fold into the morning summary. Decisions and fences still get enough chat text to actually decide on.
- Parked work gets a one-line state note (what, where it stands, next step) — pivots park, they never silently drop (Pivot Protocol).

## 6. Close the wave
- Reconcile the todo list against UPDATES.md; nothing done tonight lives only in chat.
- Morning summary: what got done (with the verifying surface), what's parked and why, what needs Scotty's hands or word — in that order.
- Durable learnings go to memory (local + Quantum) the same night, and every mistake gets a `#needs-reflection` entry in `~/dreams/reflection-queue.md`.
