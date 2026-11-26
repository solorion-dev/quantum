#!/usr/bin/env python3
"""blob-guard — detect base64-wrapped source files in a tree.

Read-only, stdlib-only checker. It scans text-expected files and flags
any whose ENTIRE content is base64 that decodes to plausible text —
the shape of a source file that was transferred or committed in its
base64 transport form instead of its plain form.

Origin: on 2026-11-25, review of the merged Nebula VRAM guard found
four files from PR #380 sitting on main as base64-wrapped text blobs
(the guard source was 11,724 bytes of base64 — not runnable Python).
Prior verification had compared the wrapped blobs against each other;
they matched, so the defect passed. Hash equality proves two copies
are the same bytes — it does not prove those bytes are the source.
This tool is the missing content check.

Detection is deliberately strict (whole file, no exceptions):
  * the file has a text-expected extension (see TEXT_EXTS);
  * size >= MIN_SIZE bytes (smaller files are too ambiguous);
  * every non-newline byte is in the base64 alphabet, the stripped
    length is a multiple of 4, and strict base64 decoding succeeds;
  * the decoded bytes are UTF-8 text (>=95% printable / whitespace)
    containing at least one newline or space — i.e. real text, not
    random binary that happens to encode cleanly.

A legitimate whole-file base64 payload belongs in a .b64 / .base64
file (not scanned) or on the --allow list with a reason. Base64
embedded inside a larger file (data URIs, JSON fields, PEM blocks)
is never whole-file, so it is never flagged.

Verdicts / exit codes:
  * 0 CLEAN      — files scanned, none wrapped.
  * 1 WRAPPED    — at least one wrapped file found.
  * 2 INCOMPLETE — a path is missing/unreadable, or zero files were
                   scanned. A checker that scanned nothing must never
                   say CLEAN. Argparse usage errors also exit 2 but
                   print no verdict line.

The scanned files are never modified. No network calls.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
from pathlib import Path

TEXT_EXTS = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh",
    ".bash", ".zsh", ".md", ".markdown", ".txt", ".rst", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".css", ".scss",
    ".html", ".htm", ".xml", ".svg", ".csv", ".sql", ".java",
    ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".rb", ".php",
}
MIN_SIZE = 100
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".pytest_cache"}


def is_wrapped(raw: bytes) -> dict | None:
    """Return detection detail if raw is a whole-file base64 wrap of text."""
    if len(raw) < MIN_SIZE:
        return None
    if b"\x00" in raw:
        return None
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    compact = "".join(text.split())
    if len(compact) < MIN_SIZE or len(compact) % 4 != 0:
        return None
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(decoded) < 40:
        return None
    try:
        dtext = decoded.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "\n" not in dtext and " " not in dtext:
        return None
    printable = sum(1 for ch in dtext if ch.isprintable() or ch in "\n\r\t")
    if printable / max(len(dtext), 1) < 0.95:
        return None
    # Re-encoding the decoded bytes must reproduce the compact form
    # (modulo line wrapping) — pins canonical base64, rejects
    # coincidental alphabets.
    if base64.b64encode(decoded).decode("ascii") != compact.rstrip("=") + "=" * (
        len(compact) - len(compact.rstrip("="))
    ):
        # Padding-normalised comparison: compare decoded round-trip.
        if base64.b64encode(decoded) != compact.encode("ascii"):
            return None
    first_line = dtext.splitlines()[0] if dtext.splitlines() else ""
    return {
        "decoded_size": len(decoded),
        "decoded_first_line": first_line[:120],
    }


def load_allow(path: Path | None) -> list[str]:
    if path is None:
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return entries


def allowed(rel_or_abs: str, allow: list[str]) -> bool:
    return any(rel_or_abs == a or rel_or_abs.endswith("/" + a) or rel_or_abs.endswith(a) for a in allow)


def collect(paths: list[Path]) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    errors: list[str] = []
    for p in paths:
        if not p.exists():
            errors.append(f"missing: {p}")
            continue
        if p.is_file():
            if p.suffix.lower() in TEXT_EXTS:
                files.append(p)
            continue
        for child in sorted(p.rglob("*")):
            if any(part in SKIP_DIRS for part in child.parts):
                continue
            if child.is_file() and child.suffix.lower() in TEXT_EXTS:
                files.append(child)
    return files, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Detect base64-wrapped source files.")
    ap.add_argument("paths", nargs="+", help="Files or directories to scan.")
    ap.add_argument("--allow", type=Path, default=None,
                    help="File of path suffixes to allow (one per line, # comments).")
    ap.add_argument("--json", action="store_true", help="Emit JSON.")
    args = ap.parse_args(argv)

    try:
        allow = load_allow(args.allow)
    except OSError as exc:
        print(f"INCOMPLETE: allow file unreadable: {exc}")
        return 2

    files, errors = collect([Path(p) for p in args.paths])
    wrapped = []
    scanned = 0
    for f in files:
        if allowed(str(f), allow):
            continue
        try:
            raw = f.read_bytes()
        except OSError as exc:
            errors.append(f"unreadable: {f}: {exc}")
            continue
        scanned += 1
        detail = is_wrapped(raw)
        if detail:
            wrapped.append({"path": str(f), "size": len(raw), **detail})

    if errors or scanned == 0:
        verdict, code = "INCOMPLETE", 2
    elif wrapped:
        verdict, code = "WRAPPED", 1
    else:
        verdict, code = "CLEAN", 0

    if args.json:
        print(json.dumps({
            "verdict": verdict, "scanned": scanned,
            "wrapped": wrapped, "errors": errors,
        }, indent=2))
    else:
        print(f"VERDICT: {verdict}")
        for w in wrapped:
            print(f"WRAPPED {w['path']} ({w['size']} B -> decoded "
                  f"{w['decoded_size']} B, first line: {w['decoded_first_line']!r})")
        for e in errors:
            print(f"ERROR {e}")
        print(f"COUNTS: scanned={scanned} wrapped={len(wrapped)} errors={len(errors)}")
    return code


if __name__ == "__main__":
    sys.exit(main())
