# codex-lint-drift

Read-only, stdlib-only Python 3.10+ checker that compares two local
files — by default the installed copy of the Codex linter and an
operator-supplied verified canonical copy — by sha256 and size, and
reports whether the installed copy has drifted. It makes no network
calls; both inputs are operator-produced local files.

## Why it exists

On **2026-10-18** the canonical `codex_lint.py` (13,179 bytes, sha256
`f8b5cd34f88346408e9df4a62d14e05e0bb8a0c80c922b918a159c061e19c6f7`)
was restored verbatim into the `local-codex-bookkeeper` skill at
`~/workspace/custom-skills/local-codex-bookkeeper/scripts/codex_lint.py`,
fixing a dead reference that skill-audit had found. After that restore,
nothing mechanically checked that the installed copy still matched the
canonical Codex copy (`Skills/codex-bookkeeper/scripts/codex_lint.py`
in the Codex vault). A silent edit, a bad sync, or a partial restore
would be invisible until the linter misbehaved. This tool is that
check, in the operator-snapshot style of settle-check and
hub-catalogue-guard.

## Usage

```bash
python3 src/codex_lint_drift.py \
  --installed <path> --canonical <path> [--json]
```

Both flags accept any two files; `codex_lint.py` is the documented
default use. Defaults:

- `--installed`: `~/workspace/custom-skills/local-codex-bookkeeper/scripts/codex_lint.py`
- `--canonical`: `~/workspace/codex-lint-drift/canonical/codex_lint.py`
  (the operator's verified-canonical drop point — see below)

An absent default is not a crash and never a MATCH: it is an
`INCOMPLETE` verdict, exit 2.

## Producing the canonical copy (operator step — the tool never fetches)

The canonical file lives in the Codex vault, reachable via the hub
bridge `quantum_codex_read`. **Do not** build a canonical copy from a
naive paged read: the bridge pager has a known bug (hub-api#102) where
naive paging loses or duplicates bytes at chunk boundaries, so a hash
derived from an unverified paged read proves nothing. Use the
checksum-verified fetch discipline in the `local-codex-fetch` skill
(oracle = the server-reported sha256 + byte count; fall back to the
byte-exact base64 transport; write only on a verified match), save the
verified file to a local path, and run this tool on that path. Only
then does a MATCH verdict mean "the installed copy is byte-identical
to what the Codex holds".

## Verdicts and exit codes

| Exit | Verdict      | Meaning |
|------|--------------|---------|
| 0    | `MATCH`      | Both files read, non-empty, identical sha256 and size |
| 1    | `DRIFT`      | Both files read, non-empty, sha256 differs; the first differing line number is reported when both files decode as UTF-8 text |
| 2    | `INCOMPLETE` | Either file missing, unreadable, or empty |

Human output is a verdict line, one line per side (`path`, `size`,
`sha256`), and — on DRIFT with both sides text — a
`first differing line: N` line. `--json` emits `verdict`,
`installed` / `canonical` objects (`path`, `size`, `sha256`; `null`
for a side that could not be read), `first_differing_line`, and
`errors`.

Exit 2 is overloaded, as in the sibling tools: an argparse usage
error also exits 2 but prints a usage message and **no verdict
line** — that is how you tell it from an `INCOMPLETE` verdict. A
checker that read nothing must never say MATCH — two empty files are
INCOMPLETE, not a match.

## Worked example

Using the shipped `examples/`:

```bash
cd tools/codex-lint-drift

# identical copies -> MATCH, exit 0
python3 src/codex_lint_drift.py \
  --installed examples/installed.txt \
  --canonical examples/canonical-same.txt

# line 2 changed -> DRIFT, exit 1, "first differing line: 2"
python3 src/codex_lint_drift.py \
  --installed examples/installed.txt \
  --canonical examples/canonical-drift.txt
```

The real check, once the operator has placed a checksum-verified
canonical copy at the default canonical path (or passes `--canonical`
explicitly):

```bash
python3 src/codex_lint_drift.py --json
```

## Tests

```bash
python3 -m pytest tests/ -q   # 13 tests, subprocess-driven
```

The suite covers identical MATCH, differing-content DRIFT with the
differing line reported, an extra-line DRIFT, a size-only difference,
missing installed, missing canonical, empty files, the `--json` shape
(both MATCH and INCOMPLETE), binary DRIFT with no line claimed, the
read-only guarantee (input bytes and mtimes pinned unchanged), the
shipped examples, and the usage-error-no-verdict rule.
