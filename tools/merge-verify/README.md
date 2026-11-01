# merge-verify

Post-merge verification. **After any merge, run this on the merged
tip before calling the branch done.** A green PR diff does not prove
the merged tree works.

Born from the Oct 25, 2026 Eidolon bad merge: a merge in the PR #7
lineage dropped declarations while keeping their uses — the diff
looked fine, the merged tree carried 25 typecheck errors and two
crashing pages, and none of it was visible until someone actually
ran the merged tree. That night the fleet rule was set
(AGENTS.md, Oct 26, 2026):

> A merge is not verified until the merged tree runs — a green PR
> diff does not prove the merged tip works: after any merge,
> exercise the merged tree itself (typecheck/build/tests + smoke
> run) before calling the branch done.

`merge-verify` is that rule as a tool: it pins the exact HEAD you
think you merged, proves the tree you are about to test is pristine,
runs every configured check against that tree, and then proves the
checks did not pollute the tree they claimed to verify.

## What it checks

| Step | Why |
|---|---|
| Repo is a git work tree | No verdict on a directory that is not the merged tree |
| Config exists, parses, checks list non-empty — or checks are discovered from `package.json` (v2, see below) | A missing or empty config with no discoverable checks is not a pass — it is `INCOMPLETE` |
| `HEAD` matches `--expect-head` (full SHA or unique prefix ≥7 chars), when given | You verified the tip you merged, not some other commit that drifted in |
| `--expect-ancestor` is an ancestor of `HEAD` (`git merge-base --is-ancestor`), when given | The commits you expected to land actually landed |
| Tree clean before checks (`git status --porcelain` empty, when `require_clean`) | Uncommitted changes mean the tree tested is not the merged tip |
| Every check in the config, run sequentially, all of them | One tool runs typecheck + tests + build + smoke as a single verdict; it does not stop at the first failure, so you see the full damage |
| Tree clean after checks (when `require_clean` and it was clean before) | A check that writes files polluted the tree — the tested tree no longer matches the merged tip (`tree_dirty_after`, `FAILED`) |

Check commands are argv arrays from the config — never shell
strings, no shell execution. Each check records its name, exit
code (`null` if it timed out or its executable was missing),
duration, `timed_out` flag, and a tail of its combined output
(last 40 lines / ~4000 chars).

The tool never modifies the repo: no checkout, no fetch, no
writes. The only git commands it runs are read-only
(`rev-parse`, `status`, `merge-base`).

## Config

Default: `<repo>/merge-verify.json`. Override with `--config PATH`.

```json
{
  "require_clean": true,
  "checks": [
    {
      "name": "typecheck",
      "command": ["npx", "tsc", "--noEmit"],
      "timeout_s": 600
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `require_clean` | Optional, default `true`. Require a pristine tree before checks, and fail if checks dirty it. |
| `checks[].name` | Human-readable check name, reported verbatim in the verdict. |
| `checks[].command` | Argv array, e.g. `["npm", "test"]`. Never a shell string. |
| `checks[].timeout_s` | Optional, default `600`. Seconds before the check is killed and counted as timed out. |
| `checks[].cwd` | Optional subdirectory relative to the repo root to run the check in. Defaults to the repo root. |

See `merge-verify.example.json` for a plausible Quantum-app
config (typecheck via `npx tsc --noEmit`, unit tests, build).
JSON has no comments, so field explanations live here, not there.

## Auto-discovery from package.json (v2)

When no config file is present, v2 derives a default check set
from the repo's `package.json` instead of stopping immediately —
so a JS/TS repo with no `merge-verify.json` still gets its merged
tree exercised.

**Precedence — a real config always wins:**

1. An explicit `--config PATH` is used as-is. A missing or
   invalid explicit config is `INCOMPLETE` (exit 2); discovery
   is never attempted for an explicit path.
2. Else `<repo>/merge-verify.json`, if it exists, is used as in
   v1.
3. Else discovery from `<repo>/package.json` is attempted
   (unless `--no-auto-discover` was given).

**Discovery order:** candidate scripts are considered in the
fixed order `typecheck`, `test`, `build`. Only scripts actually
present in `package.json`'s `"scripts"` (with a non-empty string
value) become checks; missing, empty, and non-candidate scripts
(e.g. `lint`) are skipped. Each discovered check is named after
its script and run as an argv array,
`[<package-manager>, "run", <script>]`, with the default timeout
(600s). Discovered checks always run with `require_clean: true`.

**Package-manager detection:** a lockfile in the repo root wins,
in this priority order — `pnpm-lock.yaml` → pnpm, `yarn.lock` →
yarn, `package-lock.json` or `npm-shrinkwrap.json` → npm,
`bun.lock` or `bun.lockb` → bun. With no lockfile, the
`package.json` `"packageManager"` field is used (the name before
the `@`, e.g. `"pnpm@9.0.0"` → pnpm). Otherwise the default is
npm.

**`--no-auto-discover`** restores strict v1 behaviour: no config
file means `INCOMPLETE`, even if `package.json` has usable
scripts.

**Transparency:** the result gains two fields. `config_source`
is `"file"` when a real config file was used, `"package.json"`
when checks were discovered, and `null` when neither produced a
check set. `discovered` lists the script names discovered from
`package.json` (in discovery order), and is `[]` when discovery
was not used. Human-readable output prints a line such as
`config: derived from package.json (scripts: typecheck, test)`
when discovery was used; `--json` output carries both fields.

**The honesty rule:** if `package.json` is missing, unparseable,
not a JSON object, or has zero candidate scripts, no checks
could be discovered — the verdict is `INCOMPLETE` (exit 2) with
an error naming that no config was found and no checks could be
discovered. Discovery never invents a verdict: no discoverable
checks is never `VERIFIED`.

## Verdicts & exit codes

- `VERIFIED` (0) — all identity checks pass, all checks exit 0,
  and the tree was clean throughout.
- `FAILED` (1) — something that actually ran actually failed:
  a check exited non-zero, `--expect-head` / `--expect-ancestor`
  did not match, or the tree became dirty during checks
  (`tree_dirty_after`).
- `INCOMPLETE` (2) — no verdict is possible: validation failed
  (not a git tree, missing/unparseable config, empty checks
  list), the tree was dirty before checks, or a check timed out
  or its executable was missing — that check never ran to a
  result, so calling the tree verified *or* failed would be a lie.

### Precedence rule

If a `FAILED` condition and an `INCOMPLETE` condition both occur,
`FAILED` wins **only if at least one check actually ran and
failed**. Timeouts / missing executables with no failing check =
`INCOMPLETE`. Identity failures (`--expect-head` /
`--expect-ancestor`) and `tree_dirty_after` are likewise verified
`FAILED` conditions in their own right — they were observed, not
missing — so they also yield `FAILED` even without a failing
check. Keep it simple: a result you observed beats a result you
never got, and a result you never got is never upgraded to a pass.

## Usage

```sh
# verify the merged tip in the current repo, using its
# merge-verify.json, and pin the exact HEAD you merged
python3 src/merge_verify.py --repo /path/to/repo \
  --expect-head <merged-tip-sha>

# also require a known commit to have landed in the merge
python3 src/merge_verify.py --repo /path/to/repo \
  --expect-head <merged-tip-sha> \
  --expect-ancestor <sha-that-must-be-in-history>

# machine-readable: one JSON object
# {verdict, exit_code, repo, head, expect_head_ok,
#  expect_ancestor_ok, tree_clean_before, tree_clean_after,
#  checks: [{name, exit_code, duration_s, timed_out, tail}],
#  errors: [...], config_source, discovered}
python3 src/merge_verify.py --repo /path/to/repo --json

# explicit config elsewhere
python3 src/merge_verify.py --repo /path/to/repo \
  --config /path/to/merge-verify.json

# no merge-verify.json? v2 derives checks from package.json
# scripts (typecheck, test, build) automatically — or opt out
# and restore strict v1 behaviour (no config = INCOMPLETE):
python3 src/merge_verify.py --repo /path/to/repo \
  --no-auto-discover
```

Human-readable output is the default: verdict, head SHA,
per-check lines with exit/duration, and output tails for
failures.

Read-only. Stdlib only (Python 3.10+).

## Adoption

After any merge in the fleet workflow, run `merge-verify` on the
merged tip before calling the branch done — not on the PR branch,
not on the diff, on the merged tree itself. It pairs with
settle-check (claims): settle-check proves artifacts stopped
changing, merge-verify proves the merged tree runs. One guards
against reading too early; the other guards against trusting a
diff that never executed.

## Field check (Oct 26, 2026, self-hosting)

merge-verify verified a real merge of *its own tree*: the tool was
committed on a branch, merged `--no-ff` into main in a scratch repo
with its config committed, and run with the check set to its own
test suite — **VERIFIED, exit 0, tree clean before and after, check
exit 0.** The two runs before it are the tool working as designed:
the first returned INCOMPLETE because the config file itself was
untracked (tree not pristine), and the second FAILED with
`tree_dirty_after` because pytest's `__pycache__`/`.pytest_cache`
were not yet gitignored in the scratch repo — exactly the pollution
the clean-tree rule exists to catch.

## Tests

```sh
python3 -m pytest tests/ -q   # 36 tests (16 v1 + 20 v2):
                              # good merge VERIFIED,
                              # the Eidolon bad-merge shape
                              # (definition removed, use kept)
                              # FAILED with the failing check named,
                              # expect-head match/mismatch,
                              # expect-ancestor hit/miss, dirty
                              # tree before = INCOMPLETE, timeout
                              # and missing executable =
                              # INCOMPLETE, missing/invalid/empty
                              # config = INCOMPLETE, check that
                              # dirties the tree = FAILED,
                              # --json shape, non-git dir, and
                              # cwd-subdir checks — all against
                              # real temp git repos with real
                              # commits and a real merge; the v2
                              # tests add discovery order and
                              # missing-script skipping, pnpm /
                              # yarn / bun lockfile and default
                              # npm selection (via fake pm
                              # shims on PATH), the
                              # packageManager-field fallback,
                              # lockfile-over-field precedence,
                              # config-file and explicit
                              # --config precedence over
                              # package.json, --no-auto-discover,
                              # and every no-discovery path
                              # (missing / invalid / non-object /
                              # no-candidate package.json) =
                              # INCOMPLETE, plus discovered
                              # pass = VERIFIED with
                              # config_source="package.json" and
                              # discovered fail = FAILED
```
