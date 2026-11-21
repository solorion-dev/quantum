#!/usr/bin/env python3
"""decision-queue-check — audit Scotty's decision queue for silent rot.

Read-only, stdlib-only checker for the pending-decisions queue
(~/workspace/decisions/queue.md). It answers three questions:

1. Is any AWAITING item past its stated deadline? (Under the Oct 13,
   2026 decision-timeout rule an unanswered item past its deadline is
   one Cooper may auto-decide — an overdue awaiting item that nobody
   noticed is how a decision gets made by default without a report.)
2. Is any FENCED-class open item missing its fence marker? (Fenced
   items — money, messages to others, health/leave, deletions,
   credentials, irreversible — NEVER auto-decide. The fence marker in
   the row is what stops a timeout run from treating the item as
   decidable; a fenced item without one is an accident queued up.)
3. Is any AUTO-DECIDED item (or full-handoff batch item — the
   TRK-0343 review class) older than 14 days with no outcome line?
   (Auto-decisions get a 14-day outcome review; the Nov 1, 2026
   TRK-0343 pass wrote the first ones by hand. This is that review
   class as code.)

Deadline discipline: deadlines in the real file are heterogeneous
prose ("window-start +24h", "Wed Oct 14, 2026 ~01:44 EDT",
"none — fenced"). A deadline the parser cannot resolve to a concrete
instant is classified UNPARSEABLE and makes the run INCOMPLETE —
never guessed, never silently treated as "no deadline". The relative
"window-start +Nh" form resolves only against the anchor the file
itself states ("First clocks started <date>"); no anchor, no verdict.

Verdicts / exit codes:

* 0 CLEAN — no findings and every open item's deadline parsed.
* 1 FINDINGS — at least one overdue / fence / outcome finding.
* 2 INCOMPLETE — the queue file is missing, unreadable, not UTF-8,
  or contains no parseable decision rows; OR at least one open
  item's deadline is unparseable (findings from the other checks are
  still reported — INCOMPLETE means the overdue audit could not be
  completed, not that nothing was found). Argparse usage errors also
  exit 2 but print no verdict line.

The input file is never modified. This tool makes NO network calls.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    HOME_TZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - zoneinfo is stdlib on 3.9+
    HOME_TZ = timezone(timedelta(hours=-5))

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

KNOWN_TZ = {"EDT", "EST", "ET", "UTC", "GMT"}

DATE_LONG_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"(\d{1,2}),\s*(\d{4})",
    re.IGNORECASE,
)
TIME_AFTER_RE = re.compile(r"\s*~?\s*(\d{1,2}):(\d{2})(?:\s+([A-Za-z]{2,5}))?")
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
REL_DEADLINE_RE = re.compile(r"window-start\s*\+\s*(\d+)\s*h", re.IGNORECASE)
OUTCOME_RE = re.compile(r"Outcome\s+\d{4}-\d{2}-\d{2}")

FENCE_MARKER_RES = [
    re.compile(r"fenced", re.IGNORECASE),
    re.compile(r"never\s+auto-decides?", re.IGNORECASE),
    re.compile(r"does\s*n[o']t\s+auto-decide", re.IGNORECASE),
    re.compile(r"not\s+auto-decide", re.IGNORECASE),
    re.compile(r"no\s+auto-decide", re.IGNORECASE),
]

# Fence categories from the queue's own header: money, messages to
# others, health/leave, deletions, credentials, irreversible. An open
# item whose decision/recommended text matches one of these is
# fence-class and must carry a fence marker.
FENCE_CLASS_RES = [
    ("credential", re.compile(r"credential", re.IGNORECASE)),
    ("credential", re.compile(r"password", re.IGNORECASE)),
    ("credential", re.compile(r"\bkey\s?ids?\b", re.IGNORECASE)),
    ("credential", re.compile(r"api[ -]?key", re.IGNORECASE)),
    ("credential", re.compile(r"\bsecret\b", re.IGNORECASE)),
    ("money", re.compile(r"payment", re.IGNORECASE)),
    ("money", re.compile(r"invoice", re.IGNORECASE)),
    ("money", re.compile(r"\$\s?\d", re.IGNORECASE)),
    ("health/leave", re.compile(r"medical\s+leave", re.IGNORECASE)),
    ("health/leave", re.compile(r"\bpfml\b", re.IGNORECASE)),
    ("health/leave", re.compile(r"\bfmla\b", re.IGNORECASE)),
    ("health/leave", re.compile(r"leave[ -]period", re.IGNORECASE)),
    ("health/leave", re.compile(r"\bhealth\b", re.IGNORECASE)),
    ("deletion", re.compile(r"\bdelete\b", re.IGNORECASE)),
    ("deletion", re.compile(r"\bdeletion\b", re.IGNORECASE)),
    ("deletion", re.compile(r"\bwipe\b", re.IGNORECASE)),
    ("message-to-others", re.compile(r"send\s+(a\s+|an\s+)?(message|email|text)\b", re.IGNORECASE)),
    ("message-to-others", re.compile(r"(message|email)\s+to\b", re.IGNORECASE)),
]


class QueueError(Exception):
    """Raised when the queue file cannot be read at all."""


def _mk_dt(year, month, day, hh=None, mm=None, tz_token=None):
    """Build an aware datetime, or return None if the date is invalid.

    Times without a timezone token are read in the queue's home
    timezone (America/New_York) — the file's own convention. A date
    with no time is due at end of day.
    """
    try:
        if hh is None:
            naive = datetime.combine(
                datetime(year, month, day).date(), time(23, 59, 59)
            )
        else:
            naive = datetime(year, month, day, hh, mm)
    except ValueError:
        return None
    if tz_token and tz_token.upper() in ("UTC", "GMT"):
        return naive.replace(tzinfo=timezone.utc)
    return naive.replace(tzinfo=HOME_TZ)


def _date_from_match(m, text_after):
    """Given a DATE_LONG_RE match and the text right after it, build
    the deadline datetime (honouring an optional ~HH:MM TZ suffix)."""
    month = MONTHS[m.group(1).lower()[:3]]
    day = int(m.group(2))
    year = int(m.group(3))
    tm = TIME_AFTER_RE.match(text_after)
    if tm:
        hh, mm = int(tm.group(1)), int(tm.group(2))
        tz = tm.group(3)
        if hh > 23 or mm > 59:
            return None
        if tz and tz.upper() not in KNOWN_TZ:
            return None  # unknown timezone token — never guess
        return _mk_dt(year, month, day, hh, mm, tz)
    return _mk_dt(year, month, day)


def find_anchor(text):
    """The 'window-start' anchor the file states for itself:
    'First clocks started <date>'. Returns an aware datetime or None.
    """
    idx = text.lower().find("first clocks started")
    if idx < 0:
        return None
    rest = text[idx:]
    m = DATE_LONG_RE.search(rest)
    if not m:
        return None
    return _date_from_match(m, rest[m.end():m.end() + 24])


def parse_deadline(cell, anchor):
    """Resolve a deadline cell.

    Returns ("none", None) for an explicit no-deadline cell,
    ("instant", datetime) for a resolved deadline, or
    ("unparseable", None) — never a guess.
    """
    s = cell.strip()
    if not s:
        return ("unparseable", None)
    if s.lower().startswith("none"):
        return ("none", None)
    rel = REL_DEADLINE_RE.search(s)
    if rel:
        if anchor is None:
            return ("unparseable", None)
        return ("instant", anchor + timedelta(hours=int(rel.group(1))))
    iso = ISO_DATE_RE.search(s)
    if iso:
        dt = _mk_dt(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        return ("instant", dt) if dt else ("unparseable", None)
    m = DATE_LONG_RE.search(s)
    if m:
        dt = _date_from_match(m, s[m.end():m.end() + 24])
        return ("instant", dt) if dt else ("unparseable", None)
    return ("unparseable", None)


def classify_status(status):
    """Map a status cell to a class per the file's own legend:
    awaiting / emailed / auto-decided / decided-by-scotty / dropped,
    plus the DONE/DECIDED shorthands the real rows use."""
    s = status.strip().lower()
    if s.startswith("auto-decided"):
        return "auto_decided"
    if s.startswith("done"):
        return "done"
    if s.startswith("decided"):
        return "decided"
    if "awaiting" in s:
        return "awaiting"
    if "emailed" in s:
        return "awaiting"
    if "decided-by-scotty" in s:
        return "decided"
    if s.startswith("dropped"):
        return "dropped"
    return "other"


def parse_rows(text):
    """Parse the decisions table into item dicts.

    A row is a pipe line whose first cell is a bare number and which
    carries at least the six table columns (#, Decision, Asked,
    Deadline, Recommended, Status). Header and separator rows are
    skipped. Prose outside the table (e.g. the below-table #12
    bullet) is not a queue row and is not parsed.
    """
    items = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        if not re.fullmatch(r"\d+", cells[0]):
            continue
        items.append({
            "num": int(cells[0]),
            "decision": cells[1],
            "asked": cells[2],
            "deadline": cells[3],
            "recommended": cells[4],
            "status": cells[5],
            "line": lineno,
        })
    return items


def has_fence_marker(item):
    hay = item["deadline"] + " " + item["status"]
    return any(r.search(hay) for r in FENCE_MARKER_RES)


def fence_class(item):
    """Return the fence category name if the item is fence-class."""
    hay = item["decision"] + " " + item["recommended"]
    for name, r in FENCE_CLASS_RES:
        if r.search(hay):
            return name
    return None


def outcome_items(text):
    """Item numbers that have an outcome line anywhere in the file:
    a line carrying both '#N' (exact, not a prefix of a longer
    number) and 'Outcome <ISO date>'."""
    found = set()
    for line in text.splitlines():
        if not OUTCOME_RE.search(line):
            continue
        for m in re.finditer(r"#\s?(\d+)(?!\d)", line):
            found.add(int(m.group(1)))
    return found


def parse_now(raw):
    """Parse --now: an ISO date or datetime. Naive values are read in
    the queue's home timezone. Returns None if unparseable."""
    if raw is None:
        return datetime.now(HOME_TZ)
    s = raw.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            d = datetime.strptime(s, "%Y-%m-%d")
            return d.replace(hour=23, minute=59, second=59, tzinfo=HOME_TZ)
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=HOME_TZ)
    return dt


def audit(text, now):
    items = parse_rows(text)
    anchor = find_anchor(text)
    outcomes = outcome_items(text)
    findings = {"overdue": [], "fence": [], "outcome": []}
    unparseable = []
    counts = {"items": len(items), "awaiting": 0, "auto_decided": 0,
              "decided": 0, "done": 0, "dropped": 0, "other": 0}

    for item in items:
        cls = classify_status(item["status"])
        counts[cls] = counts.get(cls, 0) + 1
        excerpt = item["decision"][:100]

        if cls == "awaiting":
            kind, instant = parse_deadline(item["deadline"], anchor)
            if kind == "unparseable":
                unparseable.append({
                    "item": item["num"], "line": item["line"],
                    "deadline": item["deadline"][:80], "excerpt": excerpt,
                })
            elif kind == "instant" and instant < now:
                findings["overdue"].append({
                    "item": item["num"], "line": item["line"],
                    "deadline": instant.isoformat(), "excerpt": excerpt,
                })
            cat = fence_class(item)
            if cat and not has_fence_marker(item):
                findings["fence"].append({
                    "item": item["num"], "line": item["line"],
                    "category": cat, "excerpt": excerpt,
                })

        # The TRK-0343 review class: auto-decisions plus the
        # full-handoff batch (the queue's own Outcome-lines header
        # names both).
        review_class = cls == "auto_decided" or "full handoff" in item["status"].lower()
        if review_class:
            dm = ISO_DATE_RE.search(item["status"])
            if not dm:
                unparseable.append({
                    "item": item["num"], "line": item["line"],
                    "deadline": "(no decision date in status)",
                    "excerpt": excerpt,
                })
            else:
                decided = datetime(
                    int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                ).date()
                age = (now.date() - decided).days
                if age > 14 and item["num"] not in outcomes:
                    findings["outcome"].append({
                        "item": item["num"], "line": item["line"],
                        "decided": decided.isoformat(), "age_days": age,
                        "excerpt": excerpt,
                    })

    if unparseable:
        verdict, code = "INCOMPLETE", 2
    elif any(findings[k] for k in findings):
        verdict, code = "FINDINGS", 1
    else:
        verdict, code = "CLEAN", 0
    return {
        "verdict": verdict, "exit": code, "counts": counts,
        "findings": findings, "unparseable": unparseable, "errors": [],
    }


def run(queue_path, now):
    try:
        raw = Path(queue_path).read_bytes()
    except OSError as exc:
        raise QueueError(f"cannot read queue file {queue_path}: {exc}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise QueueError(f"queue file {queue_path} is not valid UTF-8: {exc}")
    result = audit(text, now)
    if result["counts"]["items"] == 0:
        result["verdict"] = "INCOMPLETE"
        result["exit"] = 2
        result["errors"].append("no decision rows parsed from the table")
    return result


def print_human(r):
    print(f"VERDICT: {r['verdict']}")
    for f in r["findings"]["overdue"]:
        print(f"OVERDUE #{f['item']} (line {f['line']}): awaiting past "
              f"deadline {f['deadline']} — {f['excerpt']}")
    for f in r["findings"]["fence"]:
        print(f"FENCE #{f['item']} (line {f['line']}): {f['category']} "
              f"item without a fence marker — {f['excerpt']}")
    for f in r["findings"]["outcome"]:
        print(f"OUTCOME #{f['item']} (line {f['line']}): decided "
              f"{f['decided']}, {f['age_days']} days old, no outcome "
              f"line — {f['excerpt']}")
    for u in r["unparseable"]:
        print(f"UNPARSEABLE #{u['item']} (line {u['line']}): deadline "
              f"{u['deadline']!r} could not be parsed — classified "
              f"INCOMPLETE, not guessed")
    for e in r["errors"]:
        print(f"ERROR: {e}")
    c = r["counts"]
    n_find = sum(len(r["findings"][k]) for k in r["findings"])
    print(f"COUNTS: items={c['items']} awaiting={c['awaiting']} "
          f"auto_decided={c['auto_decided']} decided={c['decided']} "
          f"done={c['done']} dropped={c['dropped']} other={c['other']} "
          f"findings={n_find} unparseable={len(r['unparseable'])}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Audit the pending-decisions queue (read-only).")
    ap.add_argument("--queue", required=True, help="path to queue.md")
    ap.add_argument("--now", default=None,
                    help="ISO date/datetime to audit against "
                         "(default: now, America/New_York)")
    ap.add_argument("--json", action="store_true",
                    help="emit the JSON verdict instead of human lines")
    args = ap.parse_args(argv)

    now = parse_now(args.now)
    if now is None:
        print(f"ERROR: --now value {args.now!r} is not an ISO date/datetime")
        return 2
    try:
        result = run(args.queue, now)
    except QueueError as exc:
        result = {
            "verdict": "INCOMPLETE", "exit": 2,
            "counts": {"items": 0, "awaiting": 0, "auto_decided": 0,
                       "decided": 0, "done": 0, "dropped": 0, "other": 0},
            "findings": {"overdue": [], "fence": [], "outcome": []},
            "unparseable": [], "errors": [str(exc)],
        }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_human(result)
    return result["exit"]


if __name__ == "__main__":
    sys.exit(main())
