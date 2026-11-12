# settle-check

**Verify a delegated-work claim against its settled artifacts — never against the worker's summary.**

Delegated work is eventually consistent: summaries and interim previews
arrive before the writes flush, and a preview formatted as a final handoff
is a stale read, not a verdict. On Oct 21–22, 2026, nineteen reflected
failures in this fleet were that one mistake — verdicts taken from interim
previews, totals counted by eye (a header said 31/15; parsing said
30 = 16/14), a replacement loop that trashed the old version when the new
upload returned no ID. AGENTS.md now carries the rule ("Settle-window
verification for delegated work"); this tool is the rule as code.

## What it does

Given a JSON **claim manifest**, settle-check:

1. **Snapshots** every named artifact (exists, size, mtime, sha256).
2. **Waits** the manifest's `settle_seconds` window and snapshots again.
   Anything that changed during the window is still
   flushing: verdict **UNSETTLED**. The tool refuses to judge a claim
   whose artifacts are still moving.
3. Only on a stable snapshot does it **judge**: minimum sizes, sha256
   hashes, required substrings, and **counts derived by parsing the
   source** (JSON list / pointer, JSONL, CSV data rows, non-empty lines)
   — never a number copied from a summary or counted by eye.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | VERIFIED — settled artifacts match the claim |
| 1 | FAILED — settled artifacts contradict the claim |
| 2 | NO VERDICT — unsettled, bad manifest, or unparseable count source. Re-run later; record no verdict from this run |

The 1-vs-2 distinction is the point: a broken or still-flushing run must
never be recorded as a failure of the work (or absorbed silently as a
gap), and a still-flushing run must never be recorded as success.

## Manifest

```json
{
  "claim": "Night Loop cycle 5: 30 Codex notes filed",
  "settle_seconds": 60,
  "files": [
    {"path": "/path/to/report.md", "min_size": 500, "contains": "cycle 5"},
    {"path": "/path/to/payload.bin", "sha256": "<expected hex>"}
  ],
  "counts": [
    {"path": "/path/to/index.json", "pointer": "notes", "expect": 30},
    {"path": "/path/to/ledger.csv", "expect": 16}
  ]
}
```

`format` is inferred from the extension (`.json` / `.jsonl` / `.csv`,
otherwise non-empty lines) and can be set explicitly per count entry.

## v2: remote claims (Tracker status / GitHub PR)

v1 judged claims about *files*. v2 adds claims about *remote state* —
a Tracker item's status, a GitHub PR's head SHA / state / merged flag —
so a claim like "PR #363 is pushed and merged" gets the same settle
treatment as a file claim.

The tool still makes **no network calls** (stdlib only, read-only, by
design). Instead the operator produces a **snapshot file** first, and
the manifest points at it:

```json
{
  "claim": "TRK-0123 done and PR #363 merged",
  "settle_seconds": 60,
  "remote_snapshot": "remote-snapshot.json",
  "remote_claims": [
    {"type": "tracker_status", "id": "TRK-0123", "expect_status": "done"},
    {"type": "github_pr", "repo": "solorion-dev/quantum", "number": 363,
     "expect_head_sha": "aaaaaaa", "expect_state": "closed",
     "expect_merged": true}
  ]
}
```

- `remote_claims` follows v1's top-level-list style (a plain `claims`
  list is accepted as an alias). Remote claims can be combined with
  v1 `files`/`counts` entries in the same manifest.
- `github_pr` claims need **at least one** of `expect_head_sha`
  (prefix match, minimum 7 characters), `expect_state`,
  `expect_merged`; a claim with none is malformed.
- A relative `remote_snapshot` path resolves against the **manifest
  file's own directory** (v1 `files`/`counts` paths keep their
  verbatim meaning).

### Snapshot file shape

```json
{
  "tracker":   {"TRK-0123": {"status": "done"}},
  "github_prs": {"solorion-dev/quantum#363":
                 {"head_sha": "<full 40-char sha>", "state": "closed",
                  "merged": true}}
}
```

### Producing a snapshot

Read the live state through the hub MCP bridge and write what it
returns into the snapshot file, e.g. from this VM:

```bash
python3 ~/workspace/custom-connectors/custom.legacy-tritium-mcp/bin/mcp.py \
  call quantum_tracker_get '{"id": "TRK-0123"}'
python3 ~/workspace/custom-connectors/custom.legacy-tritium-mcp/bin/mcp.py \
  call quantum_github_get_pull_request \
  '{"repo": "solorion-dev/quantum", "number": 363}'
```

### Remote settle semantics

The snapshot file participates in the settle window exactly like a
file artifact — it is hashed at both passes. If it **changes during
the window** (the operator re-generating it mid-run, the remote state
still flushing), the whole run is **UNSETTLED** (exit 2). If the
snapshot file is **missing or unparseable**, or a claim's entry is
**absent** from it, the run is **NO VERDICT** (exit 2, reported as
incomplete with the reason) — never a false FAILED, never a false
VERIFIED. A present entry whose values mismatch an expectation is
**FAILED** (exit 1). Malformed remote claims (unknown `type`, missing
`expect_status`, no `expect_*`, sub-7-char `expect_head_sha`) follow
v1's bad-manifest handling: the CLI reports `bad manifest` and exits 2.

Runnable pair: `examples/remote-manifest.json` +
`examples/remote-snapshot.json` (VERIFIED against each other).

## Usage

```bash
python3 src/settle_check.py claim.json          # human report
python3 src/settle_check.py claim.json --json   # machine report
python3 -m unittest discover -s tests           # 40 tests (18 v1 + 22 v2)
```

Stdlib only, Python 3.10+. No network, no credentials, read-only: the
tool never modifies the artifacts it verifies.
