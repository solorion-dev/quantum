# decision-queue-check

Read-only, stdlib-only Python 3.10+ auditor for the pending-decisions
queue (`~/workspace/decisions/queue.md`). It never edits the queue —
it flags the three ways a decision item silently rots:

1. **OVERDUE** — an item still `awaiting` past its stated deadline.
   Under the decision-timeout rule (Oct 13, 2026) an unanswered item
   past deadline is one Cooper may auto-decide; an overdue item
   nobody noticed is a decision made by default, without a report.
2. **FENCE** — an open item that is fenced-class (money, messages to
   others, health/leave, deletions, credentials, irreversible — the
   queue header's own categories) but carries **no fence marker**.
   The marker is what stops a timeout run from treating the item as
   auto-decidable; fenced items NEVER auto-decide.
3. **OUTCOME** — an auto-decided item (or a full-handoff batch item —
   the TRK-0343 review class, named by the queue's own Outcome-lines
   header) older than 14 days with **no outcome line**. This is the
   Nov 1, 2026 TRK-0343 14-day review pass, as code.

## Usage

```bash
python3 src/decision_queue_check.py --queue <queue.md> \
  [--now <ISO date|datetime>] [--json]
```

`--now` pins the audit instant for deterministic runs (default: now,
America/New_York). The queue file is the only input — operator-read,
settle-check style; the tool makes no network calls.

## How the queue is parsed

- **Rows:** the markdown decisions table only — a pipe line whose
  first cell is a bare number, with the six columns (#, Decision,
  Asked, Deadline, Recommended, Status). Prose outside the table
  (e.g. the below-table #12 bullet in the real file) is not a queue
  row. Statuses classify per the file's own legend: `awaiting` /
  `emailed` → awaiting; `AUTO-DECIDED` → auto_decided; `DONE` → done;
  `DECIDED` / `decided-by-scotty` → decided; `dropped` → dropped.
- **Deadlines** resolve in this order:
  1. A cell starting with `none` — an explicit no-deadline item
     (never overdue).
  2. `window-start +Nh` — resolved **only** against the anchor the
     file states for itself ("First clocks started <date>", in the
     real file's Notes). No anchor in the file → unparseable.
  3. An ISO date (`YYYY-MM-DD`).
  4. A long-form date (`Wed Oct 14, 2026 ~01:44 EDT`): optional
     `~HH:MM` time and timezone token. Known tokens: EDT, EST, ET,
     UTC, GMT; a missing token reads as America/New_York (the file's
     own convention); an **unknown** token is unparseable. A date
     with no time is due at end of day. Invalid calendar dates
     (Feb 30) are unparseable.
- **Anything else is UNPARSEABLE.** An unparseable deadline on an
  open (awaiting) item makes the run INCOMPLETE — the parser never
  guesses an instant, and never treats an unreadable deadline as
  "no deadline". Deadlines on closed items are not evaluated.
- **Fence marker:** the item's Deadline or Status cell contains
  `fenced`, `never auto-decide(s)`, `does not auto-decide`,
  `not auto-decide`, or `no auto-decide` (case-insensitive).
- **Fence class:** the item's Decision or Recommended text matches a
  category pattern — credential (`credential`, `password`, `keyId`,
  `api key`, `secret`), money (`payment`, `invoice`, `$<amount>`),
  health/leave (`medical leave`, `PFML`, `FMLA`, `leave period`,
  `health`), deletion (`delete`, `deletion`, `wipe`), or
  message-to-others (`send a message/email/text`, `message to`,
  `email to`). The check applies to open items only — once an item
  is decided, the fence question is moot.
- **Outcome lines:** a line anywhere in the file carrying both an
  exact `#N` (not a prefix of a longer number — #14's outcome does
  not satisfy #1) and `Outcome <ISO date>`.

## Verdicts and exit codes

| Exit | Verdict      | Meaning |
|------|--------------|---------|
| 0    | `CLEAN`      | No findings; every open item's deadline parsed |
| 1    | `FINDINGS`   | At least one OVERDUE, FENCE, or OUTCOME finding |
| 2    | `INCOMPLETE` | Queue missing/unreadable/not UTF-8, zero rows parsed, OR an open item's deadline (or a review-class item's decision date) is unparseable. Findings from the other checks are still reported |

Human output is a verdict line, one line per finding / unparseable
item, and a counts line (items by status class, findings,
unparseable). `--json` emits `verdict`, `counts`, `findings`
(`overdue` / `fence` / `outcome`), `unparseable`, and `errors`.

Exit 2 is overloaded, as in the sibling tools: an argparse usage
error also exits 2 but prints a usage message and **no verdict
line** — that is how you tell it from an `INCOMPLETE` verdict. A
checker that parses nothing must never say CLEAN.

## Worked example

Using the shipped `examples/` (audit pinned to `--now 2026-11-21`):

```bash
cd tools/decision-queue-check

# fenced item carries its marker, deadlines in the future,
# the one auto-decision has its outcome line -> CLEAN, exit 0
python3 src/decision_queue_check.py \
  --queue examples/queue-clean.md --now 2026-11-21

# one of each rot class: #1 overdue, #2 a credential rotation with
# no fence marker, #3 auto-decided 51 days ago with no outcome line
# -> FINDINGS, exit 1, exactly those three
python3 src/decision_queue_check.py \
  --queue examples/queue-findings.md --now 2026-11-21

# an awaiting item whose deadline is prose ("when the render batch
# feels right") -> INCOMPLETE, exit 2, never guessed
python3 src/decision_queue_check.py \
  --queue examples/queue-incomplete.md --now 2026-11-21
```

## Tests

```bash
python3 -m pytest tests/ -q   # 25 tests, subprocess-driven
```

The suite covers every deadline form (none / relative-with-anchor /
relative-without-anchor / ISO / long-form / invalid calendar date /
prose), the three negative probes (overdue awaiting flags,
fence-class without marker flags, unparseable deadline yields
INCOMPLETE with no guessed verdict), the outcome review class
(auto-decided and full-handoff; Scotty-decided items excluded;
exact-number outcome matching), the shipped examples, the read-only
guarantee (input bytes and mtimes pinned unchanged), the `--json`
shape, and the usage-error-no-verdict distinction.
