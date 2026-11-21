#!/usr/bin/env python3
"""hub-catalogue-guard — catch silent tool deregistration before merge.

Read-only, stdlib-only checker that diffs two hub tool-catalogue
snapshots (a base, usually main, and a candidate, usually a PR branch)
and fails when the candidate drops tools the base has.

Origin incidents:

* 2026-11-13 — hub-api PR #133 was cut before a tools deploy and would
  have silently deregistered quantum_skills_list, quantum_skills_find
  and quantum_skills_get on merge, while GitHub showed it clean and
  mergeable.  A catalogue diff would have caught it mechanically.
* 2026-11-20 — the hub catalogue count was settled at exactly 142
  TOOL_DEFS, with the six a2a_* tools INSIDE the 142.  A claim of 150
  double-counted them.  Duplicate names inside one snapshot therefore
  make the count unreliable and are reported as INCOMPLETE here.

Snapshots are operator-produced (settle-check style): this tool makes
NO network calls.  See README.md for how an operator produces them.

Verdicts / exit codes:

* 0 SAFE — the candidate removes nothing from the base, or every
  removal is allowlisted.  Added tools are reported, never a failure.
* 1 DEREGISTER — the candidate is missing at least one base tool that
  is not allowlisted.  Each missing name is reported.
* 2 INCOMPLETE — either input missing/unreadable/unparseable, either
  snapshot EMPTY (zero tools — a checker that parses nothing must
  never say SAFE), or DUPLICATE names within one snapshot.
  Argparse usage errors also exit 2 but print no verdict line.

Tool names are case-sensitive exact strings.  The input files are
never modified.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"""name\s*:\s*['"]([^'"]+)['"]""")


class SnapshotError(Exception):
    """Raised when a snapshot cannot be read or parsed."""


def _names_from_entries(entries, source: str) -> list[str]:
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            names.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
        else:
            raise SnapshotError(f"{source}: unparseable tool entry: {entry!r}")
    return names


def _names_from_json(data, source: str) -> list[str]:
    if isinstance(data, list):
        return _names_from_entries(data, source)
    if isinstance(data, dict):
        if isinstance(data.get("tools"), list):
            return _names_from_entries(data["tools"], source)
        if isinstance(data.get("TOOL_DEFS"), list):
            return _names_from_entries(data["TOOL_DEFS"], source)
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            return _names_from_entries(result["tools"], source)
    raise SnapshotError(f"{source}: unparseable JSON snapshot shape")


def parse_snapshot_text(text: str, path: Path) -> list[str]:
    """Parse snapshot text into a list of tool names.

    Raises SnapshotError when the text is unparseable.
    """
    stripped = text.strip()
    # JSON first: list / tools object / tools-list shape / TOOL_DEFS object.
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if data is not None:
            return _names_from_json(data, str(path))
        # Fall through: a JS file may also start with a brace/bracket.
    if "TOOL_DEFS" in text:
        idx = text.index("TOOL_DEFS")
        tail = text[idx:]
        names = NAME_RE.findall(tail)
        if not names:
            raise SnapshotError(
                f"{path}: TOOL_DEFS found but no name entries after it"
            )
        return names
    if path.suffix.lower() == ".txt":
        names = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line)
        return names
    raise SnapshotError(f"{path}: unparseable snapshot")


def load_snapshot(path: Path) -> list[str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SnapshotError(f"{path}: unreadable ({exc})") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SnapshotError(f"{path}: not valid UTF-8 ({exc})") from exc
    return parse_snapshot_text(text, path)


def load_allowlist(path: Path) -> list[str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SnapshotError(f"{path}: unreadable allowlist ({exc})") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SnapshotError(f"{path}: allowlist not valid UTF-8 ({exc})") from exc
    stripped = text.strip()
    if stripped.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SnapshotError(f"{path}: unparseable allowlist ({exc})") from exc
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise SnapshotError(f"{path}: allowlist must be a JSON list of strings")
        return list(data)
    names = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


def find_duplicates(names: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for name in names:
        if name in seen:
            dupes.add(name)
        seen.add(name)
    return sorted(dupes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hub_catalogue_guard.py",
        description="Diff two hub tool-catalogue snapshots and fail on "
        "silent tool deregistration.",
    )
    parser.add_argument("--base", required=True, help="Base snapshot file")
    parser.add_argument("--candidate", required=True, help="Candidate snapshot file")
    parser.add_argument(
        "--allow-removal",
        dest="allow_removal",
        default=None,
        help="File listing allowlisted removals (JSON list or one per line)",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="NAME",
        help="Allowlist a single removal (repeatable)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    errors: list[str] = []
    duplicates: dict[str, list[str]] = {}
    base_names: list[str] = []
    cand_names: list[str] = []
    allow_names: list[str] = list(args.allow)

    try:
        base_names = load_snapshot(Path(args.base))
    except SnapshotError as exc:
        errors.append(str(exc))
    try:
        cand_names = load_snapshot(Path(args.candidate))
    except SnapshotError as exc:
        errors.append(str(exc))
    if args.allow_removal:
        try:
            allow_names.extend(load_allowlist(Path(args.allow_removal)))
        except SnapshotError as exc:
            errors.append(str(exc))

    if not errors:
        if not base_names:
            errors.append(f"{args.base}: empty snapshot (zero tools parsed)")
        if not cand_names:
            errors.append(f"{args.candidate}: empty snapshot (zero tools parsed)")
        base_dupes = find_duplicates(base_names)
        cand_dupes = find_duplicates(cand_names)
        if base_dupes:
            duplicates["base"] = base_dupes
            errors.append(
                f"{args.base}: duplicate tool names: {', '.join(base_dupes)}"
            )
        if cand_dupes:
            duplicates["candidate"] = cand_dupes
            errors.append(
                f"{args.candidate}: duplicate tool names: {', '.join(cand_dupes)}"
            )

    if errors:
        if args.json:
            payload = {
                "verdict": "INCOMPLETE",
                "counts": {
                    "base": len(base_names),
                    "candidate": len(cand_names),
                    "added": 0,
                    "removed": 0,
                    "allowed": 0,
                },
                "added": [],
                "removed": [],
                "allowed_removals": [],
                "stale_allowances": [],
                "duplicates": duplicates,
                "errors": errors,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("INCOMPLETE")
            for err in errors:
                print(f"ERROR: {err}")
        return 2

    base_set = set(base_names)
    cand_set = set(cand_names)
    allow_set = set(allow_names)
    removed_all = sorted(base_set - cand_set)
    added = sorted(cand_set - base_set)
    allowed_removals = sorted(n for n in removed_all if n in allow_set)
    removed = sorted(n for n in removed_all if n not in allow_set)
    stale_allowances = sorted(a for a in allow_set if a not in set(removed_all))

    verdict = "DEREGISTER" if removed else "SAFE"
    exit_code = 1 if removed else 0
    counts = {
        "base": len(base_set),
        "candidate": len(cand_set),
        "added": len(added),
        "removed": len(removed),
        "allowed": len(allowed_removals),
    }

    if args.json:
        payload = {
            "verdict": verdict,
            "counts": counts,
            "added": added,
            "removed": removed,
            "allowed_removals": allowed_removals,
            "stale_allowances": stale_allowances,
            "duplicates": duplicates,
            "errors": [],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(verdict)
        print(
            "base {base}, candidate {candidate}, added {added}, "
            "removed {removed}, allowed {allowed}".format(**counts)
        )
        for name in removed:
            print(f"REMOVED: {name}")
        for name in added:
            print(f"ADDED: {name}")
        for name in allowed_removals:
            print(f"ALLOWED: {name}")
        for name in stale_allowances:
            print(f"STALE-ALLOWANCE: {name}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
