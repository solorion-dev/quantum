#!/usr/bin/env python3
"""settle-check — verify a delegated-work claim against its settled artifacts.

Born from the Oct 22, 2026 reflection pass (AGENTS.md: "Settle-window
verification for delegated work"). Nineteen reflected failures were one
family: a verdict taken from an interim preview — a summary read before the
worker's writes flushed, a total counted by eye instead of parsed, a
replacement uploaded while the old version was trashed on an unverified ID.

This tool makes that rule executable. Given a JSON manifest describing a
claim (files that must exist, hashes/sizes they must match, and counts that
must be *derived by parsing the source*), it:

  1. Snapshots every named artifact (exists, size, mtime, sha256).
  2. Waits the manifest's settle window and snapshots again. Any change —
     or a file appearing mid-window — means the work is still
     flushing: verdict UNSETTLED, no judgment on the claim itself.
  3. Only on a stable snapshot does it judge: hashes, minimum sizes,
     required substrings, and counts parsed programmatically from JSON /
     CSV / JSONL / plain-text sources (never copied from a summary).
  4. (v2) Remote claims — a Tracker item's status, a GitHub PR's head
     SHA / state / merged flag — are judged from an operator-produced
     JSON snapshot file named by the manifest's `remote_snapshot`. The
     snapshot file is itself snapshotted across the settle window like
     any artifact: if it changes mid-window the run is UNSETTLED, and
     if it is missing, unparseable, or has no entry for a claim, the
     run is NO VERDICT (incomplete) — never a false pass or failure.
     The tool makes no network calls; the snapshot is produced
     beforehand by the operator (e.g. via the hub MCP bridge).

Exit codes (a watcher must never confuse them):
  0  VERIFIED   — settled artifacts match the claim.
  1  FAILED     — settled artifacts contradict the claim.
  2  NO VERDICT — unsettled (still changing / too young) or a bad
                  manifest / unreadable source. Re-run later; do not
                  record a verdict from this run.

Stdlib only, Python 3.10+.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

VERIFIED, FAILED, NO_VERDICT = 0, 1, 2


# --------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------

@dataclass
class FileSnap:
    path: str
    exists: bool
    size: int = 0
    mtime: float = 0.0
    sha256: str = ""

    def signature(self) -> tuple:
        return (self.exists, self.size, self.mtime, self.sha256)


class Snapshotter:
    """Real filesystem snapshotter. Tests inject a fake with the same API."""

    def snapshot(self, path: str) -> FileSnap:
        p = Path(path)
        try:
            st = p.stat()
        except OSError:
            return FileSnap(path=path, exists=False)
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return FileSnap(path=path, exists=True, size=st.st_size,
                        mtime=st.st_mtime, sha256=h.hexdigest())

    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# Count derivation — always by parsing, never by eye
# --------------------------------------------------------------------------

def derive_count(text: str, fmt: str, pointer: str | None) -> int:
    """Return the record count of a source document, parsed programmatically."""
    if fmt == "json":
        data = json.loads(text)
        node = data
        if pointer:
            for part in pointer.split("."):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    raise ValueError(f"pointer {pointer!r} not found at {part!r}")
        if isinstance(node, (list, dict)):
            return len(node)
        raise ValueError(f"pointer {pointer!r} does not resolve to a list/dict")
    if fmt == "jsonl":
        return sum(1 for line in text.splitlines() if line.strip())
    if fmt == "csv":
        rows = [r for r in csv.reader(io.StringIO(text)) if r]
        return max(0, len(rows) - 1)  # minus header
    if fmt == "lines":
        return sum(1 for line in text.splitlines() if line.strip())
    raise ValueError(f"unknown count format: {fmt!r}")


def infer_format(path: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    suffix = Path(path).suffix.lower()
    return {".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl",
            ".csv": "csv"}.get(suffix, "lines")


# --------------------------------------------------------------------------
# Checking
# --------------------------------------------------------------------------

@dataclass
class CheckResult:
    status: str = "verified"          # verified | failed | unsettled | error
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return {"verified": VERIFIED, "failed": FAILED}.get(self.status, NO_VERDICT)


def remote_claims_of(manifest: dict) -> list:
    """Remote (v2) claim entries: `remote_claims`, or its alias `claims`.

    v1's manifest names `files` and `counts` as separate top-level
    lists; v2 follows that style with `remote_claims`. A plain `claims`
    list is accepted as an alias so manifests written against the v2
    brief's wording keep working.
    """
    claims = list(manifest.get("remote_claims") or [])
    claims += list(manifest.get("claims") or [])
    return claims


def validate_remote_claim(entry) -> None:
    """Raise ValueError if a remote claim entry is malformed (v2)."""
    if not isinstance(entry, dict):
        raise ValueError(f"remote claim must be an object: {entry!r}")
    ctype = entry.get("type")
    if ctype == "tracker_status":
        if not entry.get("id"):
            raise ValueError(f"tracker_status claim missing 'id': {entry!r}")
        if "expect_status" not in entry:
            raise ValueError(
                f"tracker_status claim missing 'expect_status': {entry!r}")
    elif ctype == "github_pr":
        if not entry.get("repo") or not entry.get("number"):
            raise ValueError(
                f"github_pr claim needs 'repo' and 'number': {entry!r}")
        expects = [k for k in ("expect_head_sha", "expect_state",
                               "expect_merged") if k in entry]
        if not expects:
            raise ValueError("github_pr claim needs at least one expect_* "
                             f"field: {entry!r}")
        if "expect_head_sha" in entry and len(str(entry["expect_head_sha"])) < 7:
            raise ValueError("expect_head_sha must be at least 7 characters "
                             f"(prefix match): {entry!r}")
    else:
        raise ValueError(f"unknown remote claim type: {ctype!r}")


def load_manifest(text: str) -> dict:
    manifest = json.loads(text)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    files = manifest.get("files", [])
    counts = manifest.get("counts", [])
    remote = remote_claims_of(manifest)
    if not files and not counts and not remote:
        raise ValueError("manifest names no files, no counts and no remote "
                         "claims — nothing to verify")
    for entry in files:
        if "path" not in entry:
            raise ValueError(f"file entry missing 'path': {entry!r}")
    for entry in counts:
        if "path" not in entry or "expect" not in entry:
            raise ValueError(f"count entry needs 'path' and 'expect': {entry!r}")
    for entry in remote:
        validate_remote_claim(entry)
    if remote and not manifest.get("remote_snapshot"):
        raise ValueError("remote claims need a top-level 'remote_snapshot' "
                         "path naming the operator-produced snapshot file")
    return manifest


def _check_remote_claims(remote, remote_path, settled, snap,
                         result: CheckResult) -> bool:
    """Judge v2 remote claims against the settled snapshot document.

    Returns True when the run is INCOMPLETE (no verdict): the snapshot
    file is missing or unparseable, a claim is malformed, or a claim
    has no entry in the snapshot. A present entry whose values mismatch
    the claim's expectations is an ordinary failure (result.problems).
    """
    if not remote_path:
        result.problems.append("remote claims present but manifest names no "
                               "'remote_snapshot' file — incomplete, no verdict")
        return True
    snap_entry = settled.get(remote_path)
    if snap_entry is None or not snap_entry.exists:
        result.problems.append(f"{remote_path}: remote snapshot file does not "
                               "exist — incomplete, no verdict")
        return True
    try:
        doc = json.loads(snap.read_text(remote_path))
    except (ValueError, OSError, KeyError) as exc:
        result.problems.append(f"{remote_path}: remote snapshot unparseable "
                               f"({exc}) — incomplete, no verdict")
        return True
    if not isinstance(doc, dict):
        result.problems.append(f"{remote_path}: remote snapshot is not a JSON "
                               "object — incomplete, no verdict")
        return True

    incomplete = False
    tracker = doc.get("tracker") or {}
    prs = doc.get("github_prs") or {}
    for entry in remote:
        try:
            validate_remote_claim(entry)
        except ValueError as exc:
            result.problems.append(f"malformed remote claim: {exc}")
            incomplete = True
            continue
        if entry["type"] == "tracker_status":
            tid = str(entry["id"])
            label = f"tracker {tid}"
            got = tracker.get(tid)
            if not isinstance(got, dict) or "status" not in got:
                result.problems.append(f"{label}: no entry in remote snapshot "
                                       "— incomplete, no verdict")
                incomplete = True
                continue
            if got["status"] != entry["expect_status"]:
                result.problems.append(
                    f"{label}: status {got['status']!r} != expected "
                    f"{entry['expect_status']!r}")
            else:
                result.notes.append(
                    f"{label}: status {got['status']!r} matches claim")
        else:  # github_pr
            key = f"{entry['repo']}#{entry['number']}"
            label = f"github PR {key}"
            got = prs.get(key)
            if not isinstance(got, dict):
                result.problems.append(f"{label}: no entry in remote snapshot "
                                       "— incomplete, no verdict")
                incomplete = True
                continue
            mismatches = []
            if "expect_head_sha" in entry:
                want = str(entry["expect_head_sha"])
                have = str(got.get("head_sha", ""))
                if not have.startswith(want):
                    mismatches.append(
                        f"head_sha {have[:12]}… does not start with expected "
                        f"prefix {want[:12]}…")
            if "expect_state" in entry and got.get("state") != entry["expect_state"]:
                mismatches.append(f"state {got.get('state')!r} != expected "
                                  f"{entry['expect_state']!r}")
            if ("expect_merged" in entry
                    and got.get("merged") != entry["expect_merged"]):
                mismatches.append(f"merged {got.get('merged')!r} != expected "
                                  f"{entry['expect_merged']!r}")
            if mismatches:
                result.problems.extend(f"{label}: {m}" for m in mismatches)
            else:
                result.notes.append(f"{label}: snapshot entry matches claim")
    return incomplete


def check(manifest: dict, snap: Snapshotter, *,
          now: float, wait=lambda s: None) -> CheckResult:
    """Two-pass settle check. `wait` is injected so tests never sleep."""
    result = CheckResult()
    settle = float(manifest.get("settle_seconds", 0))
    files = manifest.get("files", [])
    counts = manifest.get("counts", [])
    remote = remote_claims_of(manifest)
    remote_path = manifest.get("remote_snapshot") or None
    paths = [e["path"] for e in files] + [e["path"] for e in counts]
    if remote and remote_path and remote_path not in paths:
        # The snapshot file participates in the settle window exactly
        # like a file artifact: any change across the window makes the
        # whole run UNSETTLED before anything is judged.
        paths.append(remote_path)

    first = {p: snap.snapshot(p) for p in paths}

    # Missing artifacts fail fast — absence is a verdict, not unsettledness,
    # unless the file appears during the window (handled by pass 2 compare).
    if settle > 0:
        wait(settle)
        second = {p: snap.snapshot(p) for p in paths}
    else:
        second = first

    # Settled means: identical across one full window. A young file that
    # survives the whole window unchanged IS settled; a file still being
    # written changes signature (size/mtime/sha) between the passes.
    for p in paths:
        a, b = first[p], second[p]
        if a.signature() != b.signature():
            result.status = "unsettled"
            result.problems.append(f"{p}: changed during the settle window "
                                   f"(size {a.size} -> {b.size}) — still flushing")
    if result.status == "unsettled":
        return result
    if settle <= 0:
        result.notes.append("no settle window requested — verdict is "
                            "point-in-time, not settle-verified")

    settled = second
    for entry in files:
        p = entry["path"]
        s = settled[p]
        if not s.exists:
            result.problems.append(f"{p}: does not exist")
            continue
        if "min_size" in entry and s.size < int(entry["min_size"]):
            result.problems.append(f"{p}: size {s.size} < min_size {entry['min_size']}")
        if "sha256" in entry and s.sha256 != entry["sha256"]:
            result.problems.append(f"{p}: sha256 mismatch "
                                   f"(got {s.sha256[:12]}…, want {str(entry['sha256'])[:12]}…)")
        if "contains" in entry:
            if entry["contains"] not in snap.read_text(p):
                result.problems.append(f"{p}: does not contain {entry['contains']!r}")
        else:
            result.notes.append(f"{p}: exists, {s.size} bytes, sha256 {s.sha256[:12]}…")

    for entry in counts:
        p = entry["path"]
        if not settled[p].exists:
            result.problems.append(f"{p}: count source does not exist")
            continue
        fmt = infer_format(p, entry.get("format"))
        try:
            actual = derive_count(snap.read_text(p), fmt, entry.get("pointer"))
        except (ValueError, json.JSONDecodeError) as exc:
            result.status = "error"
            result.problems.append(f"{p}: cannot derive count: {exc}")
            continue
        if actual != int(entry["expect"]):
            result.problems.append(f"{p}: parsed count {actual} != claimed {entry['expect']} "
                                   f"(format {fmt})")
        else:
            result.notes.append(f"{p}: parsed count {actual} matches claim (format {fmt})")

    # --- v2 remote claims, judged only on the settled snapshot ---
    if remote:
        if _check_remote_claims(remote, remote_path, settled, snap, result):
            # Incomplete dominates: a run that could not see every
            # remote claim records NO VERDICT, never a false verdict.
            result.status = "error"

    if result.status != "error":
        result.status = "failed" if result.problems else "verified"
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("manifest", help="path to the claim manifest JSON")
    ap.add_argument("--json", action="store_true", help="emit JSON report")
    args = ap.parse_args(argv)

    manifest_path = Path(args.manifest)
    try:
        manifest = load_manifest(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"settle-check: bad manifest: {exc}", file=sys.stderr)
        return NO_VERDICT

    # v2 convention: a relative `remote_snapshot` path resolves against
    # the manifest file's own directory. (v1 `files`/`counts` paths keep
    # their verbatim meaning — the snapshot reference is the one path a
    # manifest carries about its own neighbourhood.)
    snap_ref = manifest.get("remote_snapshot")
    if snap_ref and not Path(snap_ref).is_absolute():
        manifest["remote_snapshot"] = str(manifest_path.resolve().parent / snap_ref)

    settle = float(manifest.get("settle_seconds", 0))
    result = check(manifest, Snapshotter(), now=time.time(),
                   wait=lambda s: time.sleep(s) if s > 0 else None)

    report = {"claim": manifest.get("claim", ""), "status": result.status,
              "problems": result.problems, "notes": result.notes}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Claim: {report['claim'] or '(unnamed)'}")
        print(f"Verdict: {result.status.upper()}")
        for n in result.notes:
            print(f"  ok      {n}")
        for p in result.problems:
            print(f"  PROBLEM {p}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
