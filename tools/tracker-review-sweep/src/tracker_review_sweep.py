#!/usr/bin/env python3
"""tracker-review-sweep — surface stale in-review Tracker records.

Read-only, stdlib-only auditor for an OPERATOR-PRODUCED snapshot of
Tracker records (JSON exported via the hub bridge
``quantum_tracker_list`` / ``quantum_tracker_get`` tools).  This tool
makes NO network calls; the snapshot is a file an operator hands it.

Origin: on 2026-11-25 the Tracker board held 737 records with 75 in
review.  The scarce resource is not work — it is deciding.  Records
sit ``in_review`` waiting for a decision, and the longer they sit
without even a linked PR or issue, the more likely the decision has
been forgotten rather than merely delayed.  This tool names them.

What counts as STALE:

* ``status`` is in-review (``in_review``, ``review`` or ``in-review``,
  case-insensitive), AND
* age — ``now`` minus ``updated_at`` (falling back to ``created_at``)
  — is strictly greater than the threshold (default 14 days,
  ``--days N``), AND
* the record carries no linked PR/issue (see link fields below).

An in-review record WITH a link, or younger than the threshold, is
not flagged.  An in-review record with NO parseable timestamp is an
INCOMPLETE finding for that record: it is never silently passed and
never counted stale, because its age cannot be proven.

Record fields read (liberal — extra fields are ignored):

* ``id`` — e.g. ``TRK-0123`` (required; missing/duplicate ids make the
  snapshot INCOMPLETE).
* ``status``, ``title``.
* ``updated_at`` / ``created_at`` — ISO 8601.
* Link fields — any of: ``github_pr``, ``github_issue``, ``pr_url``,
  ``issue_url``, ``external_ref`` (non-empty string/number), or
  ``links`` (non-empty list/dict, or non-empty string).  These cover
  the real bridge shapes: ``quantum_tracker_list`` items carry
  ``external_ref``; ``quantum_tracker_get`` items additionally carry a
  ``links`` list.

Snapshot shapes accepted: a bare JSON list of records, or a JSON
object with an ``items``, ``records`` or ``results`` list (the bridge
list response is ``{"ok": true, "items": [...]}``).

Verdicts / exit codes:

* 0 CLEAN — snapshot read, no stale records, no incomplete findings.
* 1 STALE — at least one stale record; each is named with id, age in
  days, and title.
* 2 INCOMPLETE — snapshot missing/unreadable/unparseable, empty (zero
  records), duplicate ids, or at least one in-review record whose age
  cannot be determined.  No trustworthy verdict exists.
  Argparse usage errors also exit 2 but print NO verdict line
  (sibling discipline, shared with settle-check / hub-catalogue-guard).

The input file is never modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REVIEW_STATUSES = {"in-review", "review"}
LINK_SCALAR_FIELDS = ("github_pr", "github_issue", "pr_url", "issue_url",
                      "external_ref")
LIST_KEYS = ("items", "records", "results")


class SnapshotError(Exception):
    """Raised when a snapshot cannot be read or parsed."""


def parse_timestamp(value) -> datetime | None:
    """Parse an ISO 8601 timestamp; return an aware datetime or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_review_status(status) -> bool:
    if not isinstance(status, str):
        return False
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    return normalized in REVIEW_STATUSES


def has_link(record: dict) -> bool:
    """True when the record carries any linked PR/issue reference."""
    for field in LINK_SCALAR_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (int, float)) and value:
            return True
        if isinstance(value, dict) and value:
            return True
    links = record.get("links")
    if isinstance(links, str) and links.strip():
        return True
    if isinstance(links, (list, tuple, dict)) and len(links) > 0:
        # A list of only empty placeholders is not a link.
        if isinstance(links, dict):
            return True
        return any(bool(entry) for entry in links)
    return False


def load_snapshot(path: Path) -> list[dict]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SnapshotError(f"{path}: unreadable ({exc})") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SnapshotError(f"{path}: not valid UTF-8 ({exc})") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"{path}: unparseable JSON ({exc})") from exc
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = None
        for key in LIST_KEYS:
            if isinstance(data.get(key), list):
                records = data[key]
                break
        if records is None:
            raise SnapshotError(
                f"{path}: unparseable snapshot shape "
                f"(no list under any of {', '.join(LIST_KEYS)})"
            )
    else:
        raise SnapshotError(f"{path}: unparseable snapshot shape")
    for entry in records:
        if not isinstance(entry, dict):
            raise SnapshotError(
                f"{path}: unparseable record entry: {entry!r}"
            )
    return records


def audit(records: list[dict], now: datetime, threshold_days: float):
    """Return (stale, incomplete, errors).

    stale: list of dicts {id, title, age_days, stamp_field, stamp}
    incomplete: list of strings (per-record findings)
    errors: list of strings (snapshot-level problems)
    """
    errors: list[str] = []
    incomplete: list[str] = []
    stale: list[dict] = []

    seen: set[str] = set()
    dupes: set[str] = set()
    for record in records:
        rid = record.get("id")
        if not isinstance(rid, str) or not rid.strip():
            errors.append(f"record without a usable id: {record!r:.120}")
            continue
        if rid in seen:
            dupes.add(rid)
        seen.add(rid)
    if dupes:
        errors.append(f"duplicate record ids: {', '.join(sorted(dupes))}")
    if errors:
        return stale, incomplete, errors

    for record in records:
        if not is_review_status(record.get("status")):
            continue
        rid = record["id"]
        title = record.get("title") if isinstance(record.get("title"), str) else ""
        stamp = parse_timestamp(record.get("updated_at"))
        stamp_field = "updated_at"
        if stamp is None:
            stamp = parse_timestamp(record.get("created_at"))
            stamp_field = "created_at"
        if stamp is None:
            incomplete.append(
                f"{rid}: in-review but no parseable timestamp "
                f"(updated_at/created_at) — age cannot be determined"
            )
            continue
        if has_link(record):
            continue
        age_days = (now - stamp).total_seconds() / 86400.0
        if age_days > threshold_days:
            stale.append({
                "id": rid,
                "title": title,
                "age_days": round(age_days, 1),
                "stamp_field": stamp_field,
                "stamp": record.get(stamp_field),
            })
    stale.sort(key=lambda s: (-s["age_days"], s["id"]))
    return stale, incomplete, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tracker_review_sweep.py",
        description="Audit a Tracker snapshot for stale in-review records.",
    )
    parser.add_argument("snapshot", help="Snapshot JSON file (operator-produced)")
    parser.add_argument("--days", type=float, default=14.0,
                        help="Staleness threshold in days (default 14)")
    parser.add_argument("--now", default=None,
                        help="ISO 8601 'now' override (deterministic runs/tests)")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    if args.days < 0:
        parser.error("--days must be >= 0")
    if args.now is not None:
        now = parse_timestamp(args.now)
        if now is None:
            parser.error(f"--now is not a parseable ISO 8601 timestamp: {args.now}")
    else:
        now = datetime.now(timezone.utc)

    errors: list[str] = []
    records: list[dict] = []
    try:
        records = load_snapshot(Path(args.snapshot))
    except SnapshotError as exc:
        errors.append(str(exc))

    stale: list[dict] = []
    incomplete: list[str] = []
    in_review = 0
    if not errors:
        if not records:
            errors.append(f"{args.snapshot}: empty snapshot (zero records)")
        else:
            in_review = sum(1 for r in records if is_review_status(r.get("status")))
            stale, incomplete, audit_errors = audit(records, now, args.days)
            errors.extend(audit_errors)

    if errors or incomplete:
        verdict, exit_code = "INCOMPLETE", 2
    elif stale:
        verdict, exit_code = "STALE", 1
    else:
        verdict, exit_code = "CLEAN", 0

    counts = {
        "records": len(records),
        "in_review": in_review,
        "stale": len(stale),
        "incomplete": len(incomplete),
    }
    if args.json:
        payload = {
            "verdict": verdict,
            "counts": counts,
            "threshold_days": args.days,
            "now": now.isoformat(),
            "stale": stale,
            "incomplete": incomplete,
            "errors": errors,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(verdict)
        print(
            "records {records}, in_review {in_review}, stale {stale}, "
            "incomplete {incomplete} (threshold {threshold} days)".format(
                threshold=args.days, **counts)
        )
        for entry in stale:
            print(f"STALE: {entry['id']} — {entry['age_days']} days — "
                  f"{entry['title']}")
        for finding in incomplete:
            print(f"INCOMPLETE: {finding}")
        for err in errors:
            print(f"ERROR: {err}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
