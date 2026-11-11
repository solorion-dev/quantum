#!/usr/bin/env python3
"""evolution-check — catch already-shipped items still open in the backlog.

Read-only, stdlib-only checker for the daily evolution build system.

The system keeps two files:

* a *build log* — one dated line per shipped build:
  ``- YYYY-MM-DD — Title (TRK-####, PR #NNN, merged SHA): ...``
* an *idea backlog* — bullets; shipped items are struck through
  (``~~title~~``).

On 2026-11-09 a backlog item that had already shipped on 2026-11-07
(boot-ref-sweep v3, TRK-0614, PR #358) was still open in the backlog,
which caused a duplicate dispatch.  This tool catches that class of
error before a run starts:

1. STALE (FAIL, exit 1) — an OPEN backlog bullet references a TRK id
   or PR number that appears in any build-log entry, without
   acknowledging that build.
1b. CITED (WARN only) — same shared id, but the bullet itself
   acknowledges the earlier build (a ``built YYYY-MM-DD`` /
   ``shipped YYYY-MM-DD`` clause, an ``after PR #N merges`` /
   ``once ... merges`` condition, or a ``vN:`` extension lead-in
   after the title).  Those are adoption/extension follow-ups, not
   un-struck shipped items — surfaced for a human, never a FAIL.
   (Refinement added 2026-11-11: the literal rule false-flagged 16
   adoption bullets in the real backlog, e.g. "Wire proof-check into
   verdict recording — built 2026-10-27 (TRK-0475, PR #311)".)
2. GAP (WARN only) — calendar gaps between consecutive distinct log
   dates larger than ``--max-gap-days`` (missed runs).
3. INCOMPLETE (exit 2, no verdict) — either file missing/unreadable,
   or zero log entries / zero backlog bullets parsed.  A checker that
   parses nothing must never say CLEAN.

Exit codes: 0 = CLEAN (WARNs allowed), 1 = STALE found, 2 = INCOMPLETE.
The input files are never modified.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Log entry: "- YYYY-MM-DD — ..." ; also accept a plain hyphen separator
# ("- YYYY-MM-DD - ...") and an en dash.
LOG_LINE_RE = re.compile(
    r"^\s*-\s+(\d{4}-\d{2}-\d{2})\s+(?:—|–|-)\s+(.*)$"
)

# Backlog bullet: "- " at any indent (sub-bullets included).
BULLET_RE = re.compile(r"^\s*-\s+(.*)$")

TRK_RE = re.compile(r"\bTRK-(\d+)\b", re.IGNORECASE)

# PR references (see extract_pr_numbers).  A bare ``repo#NNN`` is NOT
# a PR reference on its own — in the real files that shape is usually
# an *issue* (``hub-api#102``) or a cross-reference, and counting it
# produced a false STALE on the still-open "Implement the hub-api#102
# server fix" backlog item.  It counts only in explicit PR context
# (``PR quantum#298``, ``draft PR #298``).
PR_HASH_RE = re.compile(r"\bPR\s*#(\d+)\b", re.IGNORECASE)
PR_REPO_HASH_RE = re.compile(
    r"\bPRs?\s+(?:[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*)#(\d+)\b", re.IGNORECASE
)
BARE_HASH_RE = re.compile(r"(?<![\w#])#(\d+)\b")

# A bullet acknowledges an earlier build when it cites that build as
# already done or as the precondition for new work.  Markers:
#   "built 2026-10-27 (TRK-0475, PR #311)" / "Tool shipped 2026-10-17"
#   "after PR #293 merges:" / "once the PR merges"
#   "**Title** — v2: ..." (an extension of a shipped tool)
ACK_RE = re.compile(
    r"(?:\bbuilt\s+\d{4}-\d{2}-\d{2}"
    r"|\bshipped\s+\d{4}-\d{2}-\d{2}"
    r"|\bafter\s+PR\s*#?\d+\s+merges\b"
    r"|\bonce\b[^.]{0,40}\bmerges\b"
    r"|\*\*\s+—\s+v\d+\s*:)",
    re.IGNORECASE,
)

# A bullet is struck when its title portion is wrapped in ~~...~~.
# Real bullets look like:  - ~~**Title**~~ — DONE ...
# (an optional leading ** before the ~~ is tolerated).
STRUCK_RE = re.compile(r"^(?:\*\*)?~~.+?~~")

# Words that mark a log entry as shipped/merged (informational only;
# every log line is by definition a shipped build).
SHIP_MARKER_RE = re.compile(
    r"\b(merged|squash-merged|shipped|done|closed)\b", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    line_number: int  # 1-based line in the build log
    day: date
    text: str  # entry text after the date separator
    trk_ids: list[str] = field(default_factory=list)  # e.g. ["TRK-0614"]
    pr_numbers: list[int] = field(default_factory=list)  # e.g. [358]
    shipped: bool = True  # a log line *is* a shipped build
    has_merge_marker: bool = False


@dataclass
class BacklogBullet:
    line_number: int  # 1-based line in the backlog
    text: str
    struck: bool
    trk_ids: list[str] = field(default_factory=list)
    pr_numbers: list[int] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return not self.struck


@dataclass
class StaleFinding:
    backlog_line: int
    shared_id: str  # "TRK-0614" or "PR #358"
    kind: str  # "trk" or "pr"
    log_date: str  # ISO date of the log entry that shipped it
    log_line: int
    bullet: str  # bullet excerpt

    def to_dict(self) -> dict:
        return {
            "backlog_line": self.backlog_line,
            "id": self.shared_id,
            "kind": self.kind,
            "log_date": self.log_date,
            "log_line": self.log_line,
            "bullet": self.bullet,
        }


@dataclass
class GapFinding:
    from_date: str
    to_date: str
    gap_days: int
    max_gap_days: int

    def to_dict(self) -> dict:
        return {
            "from": self.from_date,
            "to": self.to_date,
            "gap_days": self.gap_days,
            "max_gap_days": self.max_gap_days,
        }


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def extract_trk_ids(text: str) -> list[str]:
    """All TRK-#### ids in *text*, normalised to upper case, deduped."""
    seen: list[str] = []
    for m in TRK_RE.finditer(text):
        trk = f"TRK-{m.group(1)}"
        if trk not in seen:
            seen.append(trk)
    return seen


def extract_pr_numbers(text: str) -> list[int]:
    """All PR numbers in *text*, deduped, in order of appearance.

    Shapes recognised:
      * ``PR #NNN``            — explicit PR reference
      * ``PR repo#NNN``        — e.g. ``PR quantum#86`` (PR context
                                 required; a bare ``repo#NNN`` is an
                                 issue/cross-reference, not a PR)
      * bare ``#NNN``          — only when the text mentions "PR"
                                 (covers lists like ``PR #293, #294``);
                                 a bare ``#NNN`` with no PR context is
                                 too ambiguous to count on its own.
    """
    found: list[tuple[int, int]] = []  # (position, number)
    for m in PR_HASH_RE.finditer(text):
        found.append((m.start(), int(m.group(1))))
    for m in PR_REPO_HASH_RE.finditer(text):
        found.append((m.start(), int(m.group(1))))
    if PR_HASH_RE.search(text) or re.search(r"\bPRs?\b", text, re.IGNORECASE):
        for m in BARE_HASH_RE.finditer(text):
            found.append((m.start(), int(m.group(1))))
    out: list[int] = []
    for _, num in sorted(found):
        if num not in out:
            out.append(num)
    return out


def is_struck(bullet_text: str) -> bool:
    """True if the bullet's title portion is wrapped in ~~...~~."""
    return bool(STRUCK_RE.match(bullet_text.strip()))


def acknowledges_prior_build(bullet_text: str) -> bool:
    """True if the bullet cites an earlier build as done / a precondition.

    Such a bullet is an adoption or extension follow-up (CITED, WARN),
    not an un-struck shipped item (STALE, FAIL).  Merely *referencing*
    a PR ("follow-up to PR #358") does not acknowledge it — the
    requested work may still be the shipped work itself.
    """
    return bool(ACK_RE.search(bullet_text))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_log_text(text: str) -> list[LogEntry]:
    entries: list[LogEntry] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = LOG_LINE_RE.match(line)
        if not m:
            continue
        try:
            day = date.fromisoformat(m.group(1))
        except ValueError:
            continue  # date-shaped but not a real date: not an entry
        body = m.group(2)
        entries.append(
            LogEntry(
                line_number=lineno,
                day=day,
                text=body,
                trk_ids=extract_trk_ids(body),
                pr_numbers=extract_pr_numbers(body),
                has_merge_marker=bool(SHIP_MARKER_RE.search(body)),
            )
        )
    return entries


def parse_backlog_text(text: str) -> list[BacklogBullet]:
    bullets: list[BacklogBullet] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = BULLET_RE.match(line)
        if not m:
            continue
        body = m.group(1).strip()
        if not body:
            continue
        bullets.append(
            BacklogBullet(
                line_number=lineno,
                text=body,
                struck=is_struck(body),
                trk_ids=extract_trk_ids(body),
                pr_numbers=extract_pr_numbers(body),
            )
        )
    return bullets


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def find_stale(
    entries: list[LogEntry], bullets: list[BacklogBullet]
) -> tuple[list[StaleFinding], list[StaleFinding]]:
    """(stale, cited): OPEN bullets sharing a TRK/PR with a log entry.

    A bullet that acknowledges the earlier build (see
    ``acknowledges_prior_build``) lands in *cited* — WARN only; all
    other shared-id bullets land in *stale* — FAIL.
    """
    # First log entry (in file order) that shipped each id.
    trk_owner: dict[str, LogEntry] = {}
    pr_owner: dict[int, LogEntry] = {}
    for entry in entries:
        for trk in entry.trk_ids:
            trk_owner.setdefault(trk, entry)
        for pr in entry.pr_numbers:
            pr_owner.setdefault(pr, entry)

    stale: list[StaleFinding] = []
    cited: list[StaleFinding] = []
    for bullet in bullets:
        if not bullet.is_open:
            continue  # struck = already handled, never stale
        target = cited if acknowledges_prior_build(bullet.text) else stale
        excerpt = bullet.text if len(bullet.text) <= 140 else bullet.text[:137] + "..."
        for trk in bullet.trk_ids:
            owner = trk_owner.get(trk)
            if owner is not None:
                target.append(
                    StaleFinding(
                        backlog_line=bullet.line_number,
                        shared_id=trk,
                        kind="trk",
                        log_date=owner.day.isoformat(),
                        log_line=owner.line_number,
                        bullet=excerpt,
                    )
                )
        for pr in bullet.pr_numbers:
            owner = pr_owner.get(pr)
            if owner is not None:
                target.append(
                    StaleFinding(
                        backlog_line=bullet.line_number,
                        shared_id=f"PR #{pr}",
                        kind="pr",
                        log_date=owner.day.isoformat(),
                        log_line=owner.line_number,
                        bullet=excerpt,
                    )
                )
    return stale, cited


def find_gaps(entries: list[LogEntry], max_gap_days: int) -> list[GapFinding]:
    """Gaps > max_gap_days between consecutive *distinct* log dates."""
    days = sorted({e.day for e in entries})
    gaps: list[GapFinding] = []
    for prev, cur in zip(days, days[1:]):
        delta = (cur - prev).days
        if delta > max_gap_days:
            gaps.append(
                GapFinding(
                    from_date=prev.isoformat(),
                    to_date=cur.isoformat(),
                    gap_days=delta,
                    max_gap_days=max_gap_days,
                )
            )
    return gaps


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_check(log_path: Path, backlog_path: Path, max_gap_days: int) -> tuple[dict, int]:
    """Return (result_dict, exit_code).  Never writes to the inputs."""
    errors: list[str] = []
    entries: list[LogEntry] = []
    bullets: list[BacklogBullet] = []

    log_text = _read_or_error(log_path, "build log", errors)
    if log_text is not None:
        entries = parse_log_text(log_text)
        if not entries:
            errors.append(f"build log {log_path}: zero log entries parsed")

    backlog_text = _read_or_error(backlog_path, "backlog", errors)
    if backlog_text is not None:
        bullets = parse_backlog_text(backlog_text)
        if not bullets:
            errors.append(f"backlog {backlog_path}: zero backlog bullets parsed")

    counts = {
        "log_entries": len(entries),
        "backlog_open": sum(1 for b in bullets if b.is_open),
        "backlog_struck": sum(1 for b in bullets if b.struck),
    }

    if errors:
        # No verdict on unproven input — a checker that parses nothing
        # must never say CLEAN.
        result = {
            "verdict": "INCOMPLETE",
            "stale": [],
            "cited": [],
            "gaps": [],
            "counts": counts,
            "errors": errors,
        }
        return result, 2

    stale, cited = find_stale(entries, bullets)
    gaps = find_gaps(entries, max_gap_days)
    verdict = "STALE" if stale else "CLEAN"
    result = {
        "verdict": verdict,
        "stale": [f.to_dict() for f in stale],
        "cited": [f.to_dict() for f in cited],
        "gaps": [g.to_dict() for g in gaps],
        "counts": counts,
    }
    return result, 1 if stale else 0


def _read_or_error(path: Path, label: str, errors: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except OSError as exc:
        errors.append(f"{label} {path}: unreadable ({exc.strerror or exc})")
    except UnicodeDecodeError as exc:
        errors.append(f"{label} {path}: unreadable (not valid UTF-8: {exc})")
    return None


def render_human(result: dict) -> str:
    lines = [f"VERDICT: {result['verdict']}"]
    for err in result.get("errors", []):
        lines.append(f"ERROR: {err}")
    for s in result["stale"]:
        lines.append(
            f"STALE backlog line {s['backlog_line']}: {s['id']} "
            f"already shipped in build log on {s['log_date']} "
            f"(log line {s['log_line']}) — {s['bullet']}"
        )
    for s in result.get("cited", []):
        lines.append(
            f"CITED backlog line {s['backlog_line']}: {s['id']} "
            f"shipped {s['log_date']} but the bullet acknowledges "
            f"that build (adoption/extension follow-up, WARN only) "
            f"— {s['bullet']}"
        )
    for g in result["gaps"]:
        lines.append(
            f"WARN GAP: {g['from']} -> {g['to']} is {g['gap_days']} days "
            f"(> max {g['max_gap_days']})"
        )
    c = result["counts"]
    lines.append(
        f"COUNTS: log_entries={c['log_entries']} "
        f"backlog_open={c['backlog_open']} backlog_struck={c['backlog_struck']}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evolution-check",
        description=(
            "Read-only check: flag backlog items that already shipped "
            "(STALE), warn on build-log date gaps, and refuse a verdict "
            "when either file cannot be parsed (INCOMPLETE)."
        ),
    )
    parser.add_argument("--log", required=True, help="path to the build log (Markdown)")
    parser.add_argument("--backlog", required=True, help="path to the idea backlog (Markdown)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--max-gap-days",
        type=int,
        default=4,
        help="warn on log-date gaps larger than this many days (default: 4)",
    )
    args = parser.parse_args(argv)

    result, exit_code = run_check(Path(args.log), Path(args.backlog), args.max_gap_days)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_human(result))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
