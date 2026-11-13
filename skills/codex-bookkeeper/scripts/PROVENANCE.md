# codex_lint.py — provenance and tests

**Restored 2026-10-18** (daily evolution build) into this skill copy, fixing
the dead reference found by the 2026-10-17 skill-audit run: the skill's
conformance checks are defined by a `scripts/codex_lint.py` (named in
`references/access-modes.md`; `SKILL.md` tells the bookkeeper to run the
linter when the script exists in the copy being used, else find it in the
canonical Codex copy), but this copy of the skill had no `scripts/` folder
at all — so on this machine the checks could only ever be applied by eye.

- **Source:** the canonical Codex copy,
  `Skills/codex-bookkeeper/scripts/codex_lint.py` in the Quantum Codex vault
  (Tritium: `/home/scott/codex/Skills/codex-bookkeeper/scripts/codex_lint.py`).
- **Verbatim:** byte-for-byte identical to the canonical copy.
  sha256 `f8b5cd34f88346408e9df4a62d14e05e0bb8a0c80c922b918a159c061e19c6f7`,
  13,179 bytes, verified after transfer on 2026-10-18. If the Codex copy is
  ever updated, re-copy it and re-verify the hash rather than editing this
  copy in place — the Codex is the canonical home.
- **What was added here (not in the canonical copy):**
  `test_codex_lint.py` — 28 fixture-vault unit tests covering every check
  family (F frontmatter, N naming, G goal notes, L links, A archive,
  S skill notes) plus CLI exit-code/report/skip behaviour. The canonical
  script shipped untested; these pin its behaviour so a re-sync or edit
  can't silently change what "conformant" means.
- **Run the tests:** `python3 scripts/test_codex_lint.py`
  (requires PyYAML, the linter's own only dependency).
- **Run the linter:** `python3 scripts/codex_lint.py PATH [PATH ...]
  [--vault DIR] [--links] [--strict]` — always pass specific folders,
  never the whole vault (see the script docstring: whole-vault walks stall
  the Drive mount for every other reader).

## codex_fetch.py — added 2026-10-19 (daily evolution build, TRK-0198)

Checksum-verified Codex file retrieval, written for the fleet after the
2026-10-18 finding that paged `quantum_codex_read` reassembly lost bytes.
Canonical home: Fermata `projects/tools/dev/codex-fetch` (local commit
4a993b1, branch worker/cooper/codex-fetch, ready to push). This installed
copy is byte-identical to the Fermata source at install time; its unit
tests live with the Fermata project (17 tests, all passing 2026-10-19).
