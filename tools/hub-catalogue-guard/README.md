# hub-catalogue-guard

Read-only, stdlib-only Python 3.10+ checker that diffs two hub tool
catalogue snapshots — a **base** (usually `main`) and a **candidate**
(usually a PR branch) — and fails when the candidate silently drops
tools the base has. It makes no network calls; snapshots are
operator-produced.

## Why it exists

Two failures motivated this tool:

- **2026-11-13 — hub-api PR #133.** The branch was cut before a tools
  deploy, so merging it would have silently deregistered
  `quantum_skills_list`, `quantum_skills_find`, and `quantum_skills_get`
  — while GitHub showed the PR clean and mergeable. Nothing in the
  normal review flow diffed the tool catalogue. This tool is that diff.
- **2026-11-20 — the 142 settlement.** The hub catalogue count was
  settled at exactly **142 TOOL_DEFS**, with the six `a2a_*` tools
  **inside** the 142. A competing claim of 150 double-counted them.
  Lesson encoded here: duplicate names inside one snapshot make any
  count unreliable, so duplicates are an `INCOMPLETE` verdict, never
  silently deduplicated.

## Usage

```bash
python3 src/hub_catalogue_guard.py \
  --base <snapshot> --candidate <snapshot> \
  [--allow-removal <file>] [--allow <name> ...] [--json]
```

## Producing snapshots (operator step — the tool never fetches)

The tool only reads files you hand it. Produce a snapshot per ref by
either:

1. **Reading TOOL_DEFS from source:** read `lib/mcp-handlers.js` (the
   file that defines `TOOL_DEFS`) on each ref — e.g. via the hub bridge
   `read_file` for the branch and for `main` — and save each read to a
   local file. The guard extracts `name: 'x'` / `name: "x"` entries
   only **after** the first `TOOL_DEFS` occurrence.
2. **Capturing a tools/list response:** save a captured MCP
   `tools/list` response (or its `result.tools` payload) as JSON.

Accepted snapshot shapes:

- JSON: a list of strings; an object with a `tools` list (entries are
  strings or objects with `name`); a tools/list-shaped object
  `{"result": {"tools": [...]}}`; or an object with a `TOOL_DEFS` list
  in either shape.
- JS/text: if the text contains `TOOL_DEFS`, name entries are extracted
  after its first occurrence only. Otherwise, for plain `.txt`, one
  tool name per non-empty, non-comment (`#`) line. JS without
  `TOOL_DEFS` is unparseable.

Tool names are case-sensitive exact strings.

## Verdicts and exit codes

| Exit | Verdict       | Meaning |
|------|---------------|---------|
| 0    | `SAFE`        | Candidate removes nothing, or every removal is allowlisted. Additions are reported, never a failure |
| 1    | `DEREGISTER`  | Candidate is missing at least one non-allowlisted base tool; each missing name is reported |
| 2    | `INCOMPLETE`  | Either input missing/unreadable/unparseable, either snapshot empty (zero tools), or duplicate names within one snapshot |

Allowlisting: `--allow-removal <file>` (JSON list of strings, or one
name per line) plus repeatable `--allow <name>`. Allowlisted removals
are reported separately as `allowed_removals` and do not fail. An
allowlist entry that matches nothing removed is reported as a
`stale_allowance` warning and does not change the verdict.

Human output is a verdict line, a counts line (`base N, candidate M,
added A, removed R, allowed X`), and one sorted line per
removed/added/allowed tool. `--json` emits `verdict`, `counts`,
`added[]`, `removed[]`, `allowed_removals[]`, `stale_allowances[]`,
plus `duplicates`/`errors` as applicable.

Exit 2 is overloaded, as in the sibling tools: an argparse usage error
also exits 2 but prints a usage message and **no verdict line** — that
is how you tell it from an `INCOMPLETE` verdict. A checker that parses
nothing must never say SAFE.

## PR-review workflow

Every hub-api PR review diffs the branch catalogue against `main`
with this tool before merge:

1. Produce the base snapshot from `main` and the candidate snapshot
   from the PR branch (see above).
2. Run the guard. `SAFE` (exit 0) clears the catalogue check.
3. `DEREGISTER` (exit 1) blocks the merge until each removal is either
   restored or deliberately allowlisted with a reason recorded on the
   PR. A branch cut before a tools deploy is the classic cause —
   rebase or cherry-pick the missing tools instead of merging the gap.
4. `INCOMPLETE` (exit 2) means no verdict exists: fix the snapshot
   (missing file, empty parse, duplicates) and re-run. Never record
   it as SAFE.

## Worked example

Using the shipped `examples/`:

```bash
cd tools/hub-catalogue-guard

# base + one added tool -> SAFE, exit 0
python3 src/hub_catalogue_guard.py \
  --base examples/base.json --candidate examples/candidate-safe.json

# base minus the three skills tools (the PR #133 shape)
# -> DEREGISTER, exit 1, naming exactly those three
python3 src/hub_catalogue_guard.py \
  --base examples/base.json --candidate examples/candidate-deregister.json

# allowlist one deliberate removal from the deregister candidate
python3 src/hub_catalogue_guard.py \
  --base examples/base.json --candidate examples/candidate-deregister.json \
  --allow quantum_skills_list --allow quantum_skills_find \
  --allow quantum_skills_get
# -> SAFE, exit 0, all three reported under allowed_removals
```

## Tests

```bash
python3 -m pytest tests/ -q   # 23 tests, subprocess-driven
```

The suite covers every snapshot shape, the PR #133 fixture, allowlist
and stale-allowance behaviour, duplicates, empty/missing/unparseable
inputs, case sensitivity, the read-only guarantee (input bytes and
mtimes pinned unchanged), and the `--json` shape.
