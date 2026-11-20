# evolution-check

Read-only, stdlib-only checker for the daily evolution build system.
It answers one question before a run starts: **is anything in the idea
backlog already shipped?**

## Why it exists

The evolution system keeps two files:

- a **build log** — one dated line per shipped build:
  `- YYYY-MM-DD — Title (TRK-####, PR #NNN, merged SHA): ...`
- an **idea backlog** — bullets; shipped items are struck through
  with `~~...~~`.

On **2026-11-09** a backlog item that had already shipped on
2026-11-07 (boot-ref-sweep v3, TRK-0614, PR #358) was still open in
the backlog. The run picked it up and dispatched a duplicate build;
only the builder's first source read caught it. This tool encodes
that check so it runs *before* dispatch, not by luck during it.

## Usage

```bash
python3 src/evolution_check.py \
  --log <build-log.md> \
  --backlog <backlog.md> \
  [--json] [--max-gap-days N]   # N defaults to 4
```

Example (the real files):

```bash
python3 src/evolution_check.py \
  --log ~/workspace/goals/quantum-the-dsect-everything-app/hidden_files/evolution-build-log.md \
  --backlog ~/workspace/goals/quantum-the-dsect-everything-app/hidden_files/evolution-idea-backlog.md
```

## Checks

1. **STALE (FAIL)** — an OPEN backlog bullet references a TRK id or
   PR number that appears in any build-log entry, without
   acknowledging that build. The thing already shipped; the backlog
   was never struck. Each finding reports the backlog line number,
   the shared id, and the log date that shipped it.
   Struck (`~~...~~`) bullets are already handled and never stale.
   PR shapes counted: `PR #NNN`, `PR repo#NNN`, and bare `#NNN`
   inside a PR list. A bare `repo#NNN` alone is an issue or
   cross-reference, not a PR (e.g. `hub-api#102` is an issue).
1b. **CITED (WARN)** — same shared id, but the bullet acknowledges
   that build. Those bullets are adoption/extension follow-ups, not
   un-struck shipped items — they are surfaced for a human and
   never fail the run. (Added 2026-11-11: the literal rule
   false-flagged 16 adoption bullets in the real backlog.)

   **v2 acknowledgment is per shared id, not per bullet** (v1
   decided once per bullet: one marker anywhere cited every shared
   id in it). Each open bullet's text is split into **segments** on
   semicolons, sentence-ending periods (a `.` followed by a space
   or end-of-text), and newlines only — never on commas, colons,
   parentheses, or em-dashes. A segment is acknowledged when it
   contains any of three markers (case-insensitive):

   - `built <ISO date>` or `shipped <ISO date>`;
   - a merges condition — `after PR #?N merges`, or one of
     `once` / `after` / `as` / `when` / `until` followed within 60
     characters (with no segment boundary in between) by the word
     `merges` — covering both "once … merges" and list-governing
     shapes like "(#86, #293, …) as each merges";
   - the completion assertion `is now done`.

   A shared id is CITED when **any occurrence** of that id lies
   inside an acknowledged segment; otherwise it is STALE — so a
   bullet acknowledging build A but silently re-listing shipped
   build B now STALEs on B only, while A stays CITED. One
   bullet-level exception is kept from v1, documented as such: the
   version-extension lead-in (`**Title** — vN:`) acknowledges **all**
   shared ids in the bullet, because the bullet is by definition
   the next version of the named shipped tool.

   The Nov 15, 2026 lesson is preserved: a bare
   `DONE <date> (… TRK-…)` progress label is still **not** an
   acknowledgment — it matches none of the segment markers.
2. **GAP (WARN)** — calendar gaps between consecutive distinct log
   dates larger than `--max-gap-days` (missed runs, e.g. 2026-10-23
   and 2026-11-10 had no builds). WARN only — never fails the run.
3. **INCOMPLETE (no verdict)** — either file missing/unreadable, or
   zero log entries / zero backlog bullets parsed. A checker that
   parses nothing must never say CLEAN.

## Verdicts and exit codes

| Exit | Verdict      | Meaning                                        |
|------|--------------|------------------------------------------------|
| 0    | `CLEAN`      | No stale items (GAP warnings may be reported)  |
| 1    | `STALE`      | At least one open backlog item already shipped |
| 2    | `INCOMPLETE` | Input missing/unreadable/unparseable — no verdict |

Human output is a verdict line plus one line per finding and a counts
line. `--json` emits:

```json
{
  "verdict": "CLEAN | STALE | INCOMPLETE",
  "stale": [{"backlog_line": 3, "id": "TRK-0614", "kind": "trk",
             "log_date": "2026-11-07", "log_line": 3, "bullet": "..."}],
  "cited": [{"backlog_line": 9, "id": "PR #311", "kind": "pr",
             "log_date": "2026-10-27", "log_line": 20, "bullet": "...",
             "acknowledged_via": "segment"}],
  "gaps": [{"from": "2026-11-01", "to": "2026-11-06",
            "gap_days": 5, "max_gap_days": 4}],
  "counts": {"log_entries": 2, "backlog_open": 1, "backlog_struck": 1}
}
```

(INCOMPLETE results add an `errors` list explaining what failed.
The JSON contract is additive only over v1: `cited` findings gained
the `acknowledged_via` field — `"segment"` or `"lead-in"` — in v2;
`stale` findings and the human output wording are unchanged.)

The tool is **read-only**: it never modifies the input files.

## Tests

```bash
python3 -m pytest tests/ -q
```

The suite (29 tests: the 20 v1 tests unchanged, plus 9 v2 tests)
drives the real CLI in subprocesses and covers the 2026-11-09
incident as a fixture (open → STALE naming TRK-0614; struck →
CLEAN), stale-by-PR-number-only, `PR repo#NNN` references, bare
`repo#NNN` NOT counting as a PR, the CITED class (built-date
clause, after-merges condition, vN extension lead-in), unrelated
open items staying CLEAN, GAP warnings that never fail, both
log-date separator forms, missing/empty/unparseable inputs exiting
2, and the read-only guarantee. The v2 tests add: mixed bullets
splitting CITED/STALE per id (TRK and PR forms), citation via a
second occurrence in an acknowledged segment, the merges-list
segment, the `is now done` NOTE segment (id after an em-dash),
segment isolation, the lead-in exception citing all ids, the
`DONE <date>` label staying STALE, and `acknowledged_via` in the
JSON. First real-files run (2026-11-11): CLEAN, 15 CITED warnings,
0 STALE. v2 calibration run (2026-11-20) against the real files:
CLEAN, exit 0, 0 STALE, with a CITED set identical to v1's on the
same files (every cited finding via `"segment"`).

## Layout

```
tools/evolution-check/        (canonical home: solorion-dev/quantum)
├── README.md
├── src/
│   └── evolution_check.py    # the CLI (stdlib only)
└── tests/
    └── test_evolution_check.py
```

Staged 2026-11-11 at `~/workspace/evolution-2026-11-11/evolution-check/`
for Cooper to verify and ship to `tools/evolution-check/` in the
quantum monorepo, alongside siblings proof-check / settle-check /
merge-verify / boot-ref-sweep / hive-queue-audit.
