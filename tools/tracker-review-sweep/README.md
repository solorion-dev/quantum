# tracker-review-sweep

Read-only, stdlib-only Python 3.10+ auditor that surfaces **stale
in-review Tracker records** from an operator-produced snapshot JSON.
It makes no network calls; the snapshot is a file an operator hands it.

## Why it exists

On **2026-11-25** the Tracker board held **737 records with 75 in
review**. The scarce resource is not work — it is deciding. Records
sit `in_review` waiting for a decision, and the longer one sits
without even a linked PR or issue, the more likely the decision has
been forgotten rather than merely delayed. This tool names those
records so the decision debt can be swept deliberately.

Tracker record for this tool: **TRK-0744** (evolution build
2026-11-27).

## Usage

```bash
python3 src/tracker_review_sweep.py <snapshot.json> \
  [--days N] [--now ISO8601] [--json]
```

- `--days N` — staleness threshold in days (default **14**). A record
  is stale only when its age is *strictly greater* than the threshold.
- `--now ISO8601` — override "now" (deterministic runs and tests).
  Defaults to the current UTC time.
- `--json` — machine-readable output.

## Producing a snapshot (operator step — the tool never fetches)

Export Tracker records through the hub bridge and save the result:

```bash
# all in-review records (the sweep's usual input)
python3 ~/workspace/custom-connectors/custom.legacy-tritium-mcp/bin/mcp.py \
  call quantum_tracker_list '{"agent":"cooper","status":"in_review","limit":100}' \
  > snapshot.json

# or a single record in full (adds the `links` list)
python3 ~/workspace/custom-connectors/custom.legacy-tritium-mcp/bin/mcp.py \
  call quantum_tracker_get '{"agent":"cooper","id":"TRK-0123"}'
```

The bridge list response is `{"ok": true, "items": [...]}` — that
shape is accepted as-is. A bare JSON list of records, or an object
with an `items`, `records`, or `results` list, is also accepted.

## Record fields read

Extra fields are ignored. The tool reads:

| Field | Meaning |
|---|---|
| `id` | Record id, e.g. `TRK-0123`. Required; missing or duplicate ids make the snapshot INCOMPLETE |
| `status` | In-review is `in_review`, `review`, or `in-review`, case-insensitive (the real Tracker uses `in_review`) |
| `title` | Shown in STALE lines |
| `updated_at` | ISO 8601; age is measured from here first |
| `created_at` | ISO 8601; fallback when `updated_at` is missing/unparseable |
| link fields | Any of `github_pr`, `github_issue`, `pr_url`, `issue_url`, `external_ref` (non-empty), or `links` (non-empty list/dict/string). Real shapes: `quantum_tracker_list` items carry `external_ref`; `quantum_tracker_get` items additionally carry a `links` list |

## What counts as STALE

A record is flagged STALE when **all three** hold:

1. status is in-review, **and**
2. age (`now` − `updated_at`, falling back to `created_at`) is
   strictly greater than `--days` (default 14), **and**
3. it carries no linked PR/issue in any link field above.

An in-review record **with** a link, or younger than the threshold,
is not flagged. An in-review record with **no parseable timestamp**
is an INCOMPLETE finding for that record — never silently passed,
never counted stale, because its age cannot be proven.

## Verdicts and exit codes

| Exit | Verdict | Meaning |
|------|---------|---------|
| 0 | `CLEAN` | Snapshot read; no stale records and no incomplete findings |
| 1 | `STALE` | At least one stale record; each is named with id, age in days, and title |
| 2 | `INCOMPLETE` | Snapshot missing/unreadable/unparseable, empty (zero records), duplicate ids, or an in-review record whose age cannot be determined — no trustworthy verdict |

Exit 2 is overloaded, as in the sibling tools (settle-check,
hub-catalogue-guard): a command-line usage error also exits 2 but
prints a usage message and **no verdict line** — that is how you tell
it from an INCOMPLETE verdict. A checker that reads nothing must
never say CLEAN.

Human output is a verdict line, a counts line (`records, in_review,
stale, incomplete` + threshold), then one `STALE:` line per stale
record (oldest first), `INCOMPLETE:` lines for per-record findings,
and `ERROR:` lines for snapshot-level problems. `--json` emits
`verdict`, `counts`, `threshold_days`, `now`, `stale[]` (id, title,
age_days, stamp field/value), `incomplete[]`, and `errors[]`.

The input file is never modified (a test pins its bytes and mtime).

## Worked examples

Using the shipped `examples/` with a fixed `--now`:

```bash
cd tools/tracker-review-sweep

# young + linked + done records only -> CLEAN, exit 0
python3 src/tracker_review_sweep.py examples/clean.json \
  --now 2026-11-27T12:00:00+00:00

# TRK-0901 has sat in review, unlinked, since 2026-10-01 -> STALE, exit 1
python3 src/tracker_review_sweep.py examples/stale.json \
  --now 2026-11-27T12:00:00+00:00
```

## Tests

```bash
python3 -m unittest discover -s tests -v   # 26 tests
```

The suite drives the real CLI in subprocesses: stale/young/exactly-at-
threshold, linked via `github_pr` / `links` / `external_ref`,
empty-string links not counting, status spellings, `created_at`
fallback, `--days` override, no-timestamp INCOMPLETE, missing /
malformed / empty / wrong-shape / duplicate-id snapshots, usage
errors carrying no verdict line, wrapped snapshot shapes, the real
bridge shape, `--now` determinism, `--json` shape, the read-only
guarantee, and the shipped examples.
