#!/usr/bin/env python3
"""codex-lint-drift — detect drift between installed and canonical copies.

Read-only, stdlib-only checker that compares two local files — by
default the installed copy of the Codex linter
(~/workspace/custom-skills/local-codex-bookkeeper/scripts/codex_lint.py)
and an operator-supplied verified canonical copy — by sha256 and size.

Origin: on 2026-10-18 the canonical codex_lint.py (13,179 bytes,
sha256 f8b5cd34f88346408e9df4a62d14e05e0bb8a0c80c922b918a159c061e19c6f7)
was restored verbatim into the local-codex-bookkeeper skill, fixing a
dead reference skill-audit found. Nothing mechanically checked that
the installed copy still matched the canonical Codex copy
(Skills/codex-bookkeeper/scripts/codex_lint.py in the Codex vault)
afterwards. This tool is that check.

Operator-snapshot style (like settle-check / hub-catalogue-guard):
this tool makes NO network calls. Obtaining a trustworthy canonical
copy is the operator's step — see the local-codex-fetch skill: a
canonical hash derived from a naive paged read of the Codex is NOT
trustworthy (hub-api#102 paging bug); use a checksum-verified fetch
and place the verified file locally, then run this tool on it.

Verdicts / exit codes:

* 0 MATCH — both files read, non-empty, identical sha256 (and size).
* 1 DRIFT — both files read, non-empty, sha256 differs. The first
  differing line number is reported when both files decode as text.
* 2 INCOMPLETE — either file missing / unreadable / empty. A checker
  that read nothing must never say MATCH. Argparse usage errors also
  exit 2 but print no verdict line.

The input files are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_INSTALLED = (
    Path.home()
    / "workspace/custom-skills/local-codex-bookkeeper/scripts/codex_lint.py"
)
DEFAULT_CANONICAL = (
    Path.home() / "workspace/codex-lint-drift/canonical/codex_lint.py"
)


def file_info(path: Path) -> dict:
    """Return {path, size, sha256} for path, or raise OSError."""
    raw = path.read_bytes()
    return {
        "path": str(path),
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "_raw": raw,
    }


def first_differing_line(a: bytes, b: bytes):
    """1-based first differing line if both decode as UTF-8, else None."""
    try:
        ta = a.decode("utf-8")
        tb = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    la = ta.splitlines()
    lb = tb.splitlines()
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return i + 1
    if len(la) != len(lb):
        return min(len(la), len(lb)) + 1
    # Same lines but different bytes (e.g. trailing newline): no line
    # number honestly names the difference.
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codex_lint_drift.py",
        description="Compare an installed file against its canonical "
        "copy and report MATCH / DRIFT / INCOMPLETE.",
    )
    parser.add_argument(
        "--installed",
        default=str(DEFAULT_INSTALLED),
        help="Installed copy path (default: %(default)s)",
    )
    parser.add_argument(
        "--canonical",
        default=str(DEFAULT_CANONICAL),
        help="Canonical copy path — a checksum-verified local copy "
        "(default: %(default)s)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    errors: list[str] = []
    infos: dict[str, dict | None] = {}
    for label, raw_path in (
        ("installed", args.installed),
        ("canonical", args.canonical),
    ):
        path = Path(raw_path).expanduser()
        try:
            info = file_info(path)
        except OSError as exc:
            errors.append(f"{label} {path}: unreadable ({exc})")
            infos[label] = None
            continue
        if info["size"] == 0:
            errors.append(f"{label} {path}: empty file")
            infos[label] = None
            continue
        infos[label] = info

    def public(info):
        if info is None:
            return None
        return {
            "path": info["path"],
            "size": info["size"],
            "sha256": info["sha256"],
        }

    if errors:
        if args.json:
            print(json.dumps({
                "verdict": "INCOMPLETE",
                "installed": public(infos["installed"]),
                "canonical": public(infos["canonical"]),
                "first_differing_line": None,
                "errors": errors,
            }, indent=2, sort_keys=True))
        else:
            print("INCOMPLETE")
            for label in ("installed", "canonical"):
                if infos[label] is not None:
                    print(f"{label}: {infos[label]['path']} "
                          f"size {infos[label]['size']} "
                          f"sha256 {infos[label]['sha256']}")
            for err in errors:
                print(f"ERROR: {err}")
        return 2

    inst = infos["installed"]
    can = infos["canonical"]
    assert inst is not None and can is not None
    match = inst["sha256"] == can["sha256"] and inst["size"] == can["size"]
    verdict = "MATCH" if match else "DRIFT"
    diff_line = None if match else first_differing_line(inst["_raw"], can["_raw"])

    if args.json:
        print(json.dumps({
            "verdict": verdict,
            "installed": public(inst),
            "canonical": public(can),
            "first_differing_line": diff_line,
            "errors": [],
        }, indent=2, sort_keys=True))
    else:
        print(verdict)
        print(f"installed: {inst['path']} size {inst['size']} "
              f"sha256 {inst['sha256']}")
        print(f"canonical: {can['path']} size {can['size']} "
              f"sha256 {can['sha256']}")
        if not match and diff_line is not None:
            print(f"first differing line: {diff_line}")
    return 0 if match else 1


if __name__ == "__main__":
    sys.exit(main())
