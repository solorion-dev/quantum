# blob-guard

Read-only, stdlib-only checker that detects **base64-wrapped source
files** in a tree: text files whose entire content is base64 that
decodes to plausible text.

## Why

On 2026-11-25, review of the merged Nebula VRAM guard found four
files from PR #380 sitting on `main` as base64-wrapped text blobs —
the guard source was 11,724 bytes of base64, not runnable Python.
Earlier verification compared the wrapped blobs against each other;
they matched, so the defect passed. **Hash equality proves two copies
are the same bytes; it does not prove those bytes are the source.**
blob-guard is the missing content check. Fix PR #383 replaced the
blobs with plain content.

## Run

```bash
python3 src/blob_guard.py <file-or-dir> [more paths...]
python3 src/blob_guard.py --json <path>
python3 src/blob_guard.py --allow allow.txt <path>
python3 -m pytest tests/ -q   # 19 tests (also runs under unittest-style discovery via pytest)
```

## Detection (strict, whole-file)

A file is WRAPPED only when all hold: text-expected extension
(`.py .js .ts .md .json .yaml .sh …`); size ≥ 100 B; every
non-newline byte is in the base64 alphabet and strict decoding
succeeds; the decoded bytes are ≥95% printable UTF-8 text containing
a newline or space; and re-encoding reproduces the file content.
Base64 embedded in a larger file (data URIs, JSON fields, PEM) is
never whole-file and never flagged. Legitimate whole-file base64
belongs in a `.b64` file (not scanned) or on the `--allow` list.

Directories are scanned recursively, skipping `.git`,
`__pycache__`, `node_modules`, `.pytest_cache`.

## Verdicts

| Exit | Verdict | Meaning |
|---|---|---|
| 0 | CLEAN | Files scanned, none wrapped |
| 1 | WRAPPED | At least one wrapped file (named, with decoded size + first line) |
| 2 | INCOMPLETE | A path missing/unreadable, or zero files scanned — never a pass. Usage errors also exit 2 but print no verdict line |

## Adoption

Run blob-guard over a merged tree (or a PR branch's changed text
files) as part of post-merge verification, next to merge-verify:
merge-verify proves the tree runs its checks; blob-guard proves the
files in it are the plain source those checks were written for.
