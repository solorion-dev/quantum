"""Tests for decision-queue-check (stdlib + pytest only).

Every test drives the real CLI in a subprocess so exit codes, human
output, and JSON output are exercised exactly as a run would use them.
Fixtures are written to pytest's tmp_path; the tool is read-only.
All runs pin --now so verdicts are deterministic.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "decision_queue_check.py"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

NOW = "2026-11-21"  # a Saturday; end-of-day America/New_York

HEADER = """# Pending decisions queue

Fenced items (money, messages to others, health/leave, deletions,
credentials, irreversible) NEVER auto-decide.

Status legend: awaiting / emailed / auto-decided / decided-by-scotty / dropped

| # | Decision | Asked | Deadline | Recommended | Status |
|---|----------|-------|----------|-------------|--------|
"""

NOTES = """
Notes:
- Deadline scale: 1h / 4h / 8h / 12h / 24h tiers, 48h hard cap. First clocks started Oct 13, 2026 ~01:44 EDT.
"""


def queue(tmp_path: Path, rows: str, extra: str = "", name="queue.md") -> Path:
    p = tmp_path / name
    p.write_text(HEADER + rows + extra + NOTES, encoding="utf-8")
    return p


def run_cli(q, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SRC), "--queue", str(q), "--now", NOW, *extra],
        capture_output=True, text=True, timeout=60,
    )


def run_json(q, *extra: str):
    proc = run_cli(q, "--json", *extra)
    return proc, json.loads(proc.stdout)


def row(num, decision, deadline, status, recommended="Do it", asked="2026-11-01 09:00"):
    return (f"| {num} | {decision} | {asked} | {deadline} | "
            f"{recommended} | {status} |\n")


# 1 — a clean queue (fenced item WITH marker, future deadline) is CLEAN
def test_clean_queue(tmp_path):
    q = queue(tmp_path,
              row(1, "Tune the cache size?", "Fri Nov 27, 2026 ~09:00 EST (24h)", "awaiting")
              + row(2, "Clear dangling worker keyIds?",
                    "none — credential-adjacent, FENCED, never auto-decides",
                    "awaiting (fenced: his call)"))
    proc = run_cli(q)
    assert proc.returncode == 0
    assert "VERDICT: CLEAN" in proc.stdout


# 2 — NEGATIVE PROBE: an awaiting item past its deadline must flag
def test_overdue_awaiting_flags(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "Mon Nov 2, 2026 ~09:00 EST (24h)", "awaiting"))
    proc, data = run_json(q)
    assert proc.returncode == 1
    assert data["verdict"] == "FINDINGS"
    assert [f["item"] for f in data["findings"]["overdue"]] == [1]


# 3 — an awaiting item with a future deadline does not flag
def test_future_deadline_no_flag(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "Fri Nov 27, 2026 ~09:00 EST (24h)", "awaiting"))
    proc = run_cli(q)
    assert proc.returncode == 0


# 4 — an explicit 'none' deadline is never overdue
def test_none_deadline_never_overdue(tmp_path):
    q = queue(tmp_path,
              row(1, "A branding call?", "none — creative, his call", "awaiting"))
    proc = run_cli(q)
    assert proc.returncode == 0


# 5 — NEGATIVE PROBE: a fenced-class item without its marker must flag
def test_fenced_without_marker_flags(tmp_path):
    q = queue(tmp_path,
              row(1, "Rotate the hub worker API key?",
                  "Fri Nov 27, 2026 ~09:00 EST (24h)", "awaiting"))
    proc, data = run_json(q)
    assert proc.returncode == 1
    fence = data["findings"]["fence"]
    assert [f["item"] for f in fence] == [1]
    assert fence[0]["category"] == "credential"


# 6 — a fenced-class item WITH its marker does not flag
def test_fenced_with_marker_clean(tmp_path):
    q = queue(tmp_path,
              row(1, "Rotate the hub worker API key?",
                  "none — credential-adjacent, FENCED, never auto-decides",
                  "awaiting (fenced: his call)"))
    proc = run_cli(q)
    assert proc.returncode == 0


# 7 — a non-fence open item needs no marker
def test_nonfence_without_marker_clean(tmp_path):
    q = queue(tmp_path,
              row(1, "Pick a tile style?", "Fri Nov 27, 2026 ~09:00 EST (24h)", "awaiting"))
    proc = run_cli(q)
    assert proc.returncode == 0


# 8 — auto-decided >14 days with no outcome line flags
def test_old_auto_decided_no_outcome_flags(tmp_path):
    q = queue(tmp_path,
              row(1, "Switch the archive pool?", "Fri Oct 2, 2026 ~10:00 EDT (24h)",
                  "AUTO-DECIDED 2026-10-01 ~10:30 EDT — Cooper: switched"))
    proc, data = run_json(q)
    assert proc.returncode == 1
    out = data["findings"]["outcome"]
    assert [f["item"] for f in out] == [1]
    assert out[0]["age_days"] > 14


# 9 — auto-decided >14 days WITH an outcome line does not flag
def test_old_auto_decided_with_outcome_clean(tmp_path):
    extra = ("\n## Outcome lines — 14-day reviews\n\n"
             "- **#1 (auto-decided 2026-10-01) — Outcome 2026-11-01: HELD UP.** Fine.\n")
    q = queue(tmp_path,
              row(1, "Switch the archive pool?", "Fri Oct 2, 2026 ~10:00 EDT (24h)",
                  "AUTO-DECIDED 2026-10-01 ~10:30 EDT — Cooper: switched"),
              extra=extra)
    proc = run_cli(q)
    assert proc.returncode == 0


# 10 — auto-decided within 14 days owes no outcome yet
def test_recent_auto_decided_clean(tmp_path):
    q = queue(tmp_path,
              row(1, "Switch the archive pool?", "Wed Nov 18, 2026 ~10:00 EST (24h)",
                  "AUTO-DECIDED 2026-11-18 ~10:30 EST — Cooper: switched"))
    proc = run_cli(q)
    assert proc.returncode == 0


# 11 — the full-handoff batch is in the review class too
def test_full_handoff_batch_in_review_class(tmp_path):
    q = queue(tmp_path,
              row(1, "SSO duplicate epics: close #60?", "window-start +24h",
                  "DONE 2026-10-13 — Cooper (full handoff): #60 closed"))
    proc, data = run_json(q)
    assert proc.returncode == 1
    assert [f["item"] for f in data["findings"]["outcome"]] == [1]


# 12 — a Scotty-decided item is outside the review class
def test_scotty_decided_not_in_review_class(tmp_path):
    q = queue(tmp_path,
              row(1, "Approve the plan?", "Wed Oct 14, 2026 ~01:44 EDT (24h)",
                  "DECIDED 2026-10-14 — Scotty approved directly"))
    proc = run_cli(q)
    assert proc.returncode == 0


# 13 — NEGATIVE PROBE: an unparseable deadline is INCOMPLETE, never guessed
def test_unparseable_deadline_incomplete(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "when the batch feels right", "awaiting"))
    proc, data = run_json(q)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert [u["item"] for u in data["unparseable"]] == [1]
    assert data["findings"]["overdue"] == []


# 14 — an unparseable deadline on a CLOSED item is never evaluated
def test_unparseable_deadline_on_closed_item_ignored(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "when the batch felt right",
                  "DECIDED 2026-10-14 — Scotty approved directly"))
    proc = run_cli(q)
    assert proc.returncode == 0


# 15 — the relative window-start form resolves against the file's anchor
def test_relative_deadline_with_anchor_overdue(tmp_path):
    q = queue(tmp_path,
              row(1, "Merge order call?", "window-start +24h", "awaiting"))
    proc, data = run_json(q)
    assert proc.returncode == 1
    assert [f["item"] for f in data["findings"]["overdue"]] == [1]


# 16 — the relative form without an anchor in the file is INCOMPLETE
def test_relative_deadline_without_anchor_incomplete(tmp_path):
    p = tmp_path / "queue.md"
    p.write_text(HEADER + row(1, "Merge order call?", "window-start +24h", "awaiting"),
                 encoding="utf-8")
    proc, data = run_json(p)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"


# 17 — a missing queue file is INCOMPLETE
def test_missing_file_incomplete(tmp_path):
    proc = run_cli(tmp_path / "nope.md")
    assert proc.returncode == 2
    assert "VERDICT: INCOMPLETE" in proc.stdout


# 18 — a file with no decision rows is INCOMPLETE (parses nothing)
def test_no_rows_incomplete(tmp_path):
    p = tmp_path / "queue.md"
    p.write_text("# Notes\n\nNo table here.\n", encoding="utf-8")
    proc, data = run_json(p)
    assert proc.returncode == 2
    assert data["counts"]["items"] == 0


# 19 — a non-UTF-8 file is INCOMPLETE
def test_non_utf8_incomplete(tmp_path):
    p = tmp_path / "queue.md"
    p.write_bytes(b"\xff\xfe\x00bad")
    proc = run_cli(p)
    assert proc.returncode == 2
    assert "VERDICT: INCOMPLETE" in proc.stdout


# 20 — read-only guarantee: input bytes and mtime unchanged after a run
def test_read_only(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "Mon Nov 2, 2026 ~09:00 EST (24h)", "awaiting"))
    before_bytes = q.read_bytes()
    before_mtime = os.stat(q).st_mtime_ns
    proc = run_cli(q)
    assert proc.returncode == 1
    assert q.read_bytes() == before_bytes
    assert os.stat(q).st_mtime_ns == before_mtime


# 21 — the JSON form carries verdict, counts, all finding lists
def test_json_shape(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "Mon Nov 2, 2026 ~09:00 EST (24h)", "awaiting"))
    proc, data = run_json(q)
    assert proc.returncode == 1
    for key in ("verdict", "counts", "findings", "unparseable", "errors"):
        assert key in data
    for key in ("overdue", "fence", "outcome"):
        assert key in data["findings"]
    assert data["counts"]["items"] == 1
    assert data["counts"]["awaiting"] == 1


# 22 — shipped examples: clean / findings / incomplete
def test_shipped_examples():
    clean = subprocess.run(
        [sys.executable, str(SRC), "--queue", str(EXAMPLES / "queue-clean.md"),
         "--now", NOW], capture_output=True, text=True, timeout=60)
    assert clean.returncode == 0
    assert "VERDICT: CLEAN" in clean.stdout

    findings = subprocess.run(
        [sys.executable, str(SRC), "--queue", str(EXAMPLES / "queue-findings.md"),
         "--now", NOW, "--json"], capture_output=True, text=True, timeout=60)
    assert findings.returncode == 1
    data = json.loads(findings.stdout)
    assert [f["item"] for f in data["findings"]["overdue"]] == [1]
    assert [f["item"] for f in data["findings"]["fence"]] == [2]
    assert [f["item"] for f in data["findings"]["outcome"]] == [3]

    incomplete = subprocess.run(
        [sys.executable, str(SRC), "--queue", str(EXAMPLES / "queue-incomplete.md"),
         "--now", NOW], capture_output=True, text=True, timeout=60)
    assert incomplete.returncode == 2
    assert "VERDICT: INCOMPLETE" in incomplete.stdout


# 23 — a usage error exits 2 with NO verdict line (overloaded exit code)
def test_usage_error_no_verdict():
    proc = subprocess.run(
        [sys.executable, str(SRC)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert "VERDICT" not in proc.stdout
    assert "VERDICT" not in proc.stderr


# 24 — an invalid calendar date is INCOMPLETE, never a guessed instant
def test_invalid_calendar_date_incomplete(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "Tue Feb 30, 2026 ~09:00 EST (24h)", "awaiting"))
    proc, data = run_json(q)
    assert proc.returncode == 2
    assert [u["item"] for u in data["unparseable"]] == [1]


# 25 — the ~HH:MM suffix parses to the stated instant, not end-of-day
# (regression: the shipped v1 pattern required the tilde before any
# whitespace, so "2026 ~09:00 EST" silently fell back to 23:59:59)
def test_tilde_time_parses_to_stated_instant(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "Mon Nov 2, 2026 ~09:00 EST (24h)", "awaiting"))
    proc, data = run_json(q)
    assert proc.returncode == 1
    assert data["findings"]["overdue"][0]["deadline"] == "2026-11-02T09:00:00-05:00"


# 26 — same-day boundary: due 09:00, audited at noon -> overdue
# (with the end-of-day fallback this read as not-yet-due)
def test_same_day_time_boundary(tmp_path):
    q = queue(tmp_path,
              row(1, "Reorder the render queue?", "Sat Nov 21, 2026 ~09:00 EST (24h)", "awaiting"))
    proc = subprocess.run(
        [sys.executable, str(SRC), "--queue", str(q),
         "--now", "2026-11-21T12:00:00", "--json"],
        capture_output=True, text=True, timeout=60)
    data = json.loads(proc.stdout)
    assert proc.returncode == 1
    assert [f["item"] for f in data["findings"]["overdue"]] == [1]


# 27 — an outcome line for #14 does not satisfy item #1 (exact-number match)
def test_outcome_number_boundary(tmp_path):
    extra = ("\n## Outcome lines — 14-day reviews\n\n"
             "- **#14 (auto-decided 2026-10-16) — Outcome 2026-11-01: HELD UP.** Fine.\n")
    rows = (row(1, "SSO duplicate epics: close #60?", "window-start +24h",
                "DONE 2026-10-13 — Cooper (full handoff): #60 closed")
            + row(14, "Branding call?", "Fri Oct 16, 2026 ~14:34 EDT (24h)",
                  "AUTO-DECIDED 2026-10-16 ~14:42 EDT — Cooper: merged"))
    q = queue(tmp_path, rows, extra=extra)
    proc, data = run_json(q)
    assert proc.returncode == 1
    assert [f["item"] for f in data["findings"]["outcome"]] == [1]
