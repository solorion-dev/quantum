"""Tests for evolution-check (stdlib + pytest only).

Every test drives the real CLI in a subprocess so exit codes, human
output, and JSON output are all exercised exactly as a run would use
them.  Fixtures are written to pytest's tmp_path; the tool itself is
read-only and never touches them beyond reading.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "evolution_check.py"

# The 2026-11-09 incident, as fixtures: boot-ref-sweep v3 shipped
# 2026-11-07 (TRK-0614, PR #358) but its backlog item stayed open,
# causing a duplicate dispatch two days later.
NOV9_LOG = """\
# Evolution build log

- 2026-11-07 — boot-ref-sweep v3: live-device mode (TRK-0614, solorion-dev/quantum PR #358, merged head d9cdc16): `--live-device /dev/sdX` runs lsblk itself (read-only).
- 2026-11-08 — CollabScreen createGoal() error surfacing (TRK-0616, solorion-dev/quantum PR #359, squash-merged d235d73): dedicated createError state inside the New Goal dialog.
"""

NOV9_BACKLOG_OPEN = """\
# Evolution idea backlog

- **boot-ref-sweep v3: live-device mode** — add `--live-device` so the operator does not need a separate harvest step (TRK-0614, PR #358).
- **Something unrelated** — a brand-new idea with no history.
"""

NOV9_BACKLOG_STRUCK = """\
# Evolution idea backlog

- ~~**boot-ref-sweep v3: live-device mode**~~ — DONE 2026-11-07 (TRK-0614, PR #358 merged, head d9cdc16).
- **Something unrelated** — a brand-new idea with no history.
"""


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def run_cli(log: Path, backlog: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SRC), "--log", str(log), "--backlog", str(backlog), *extra],
        capture_output=True,
        text=True,
        timeout=60,
    )


def run_json(log: Path, backlog: Path, *extra: str):
    proc = run_cli(log, backlog, "--json", *extra)
    return proc, json.loads(proc.stdout)


# --- STALE: the Nov 9 reproduction ---------------------------------------


def test_nov9_reproduction_open_item_is_stale(tmp_path):
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", NOV9_BACKLOG_OPEN)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 1
    assert data["verdict"] == "STALE"
    ids = {s["id"] for s in data["stale"]}
    assert "TRK-0614" in ids  # the finding names the shipped TRK id
    trk_finding = next(s for s in data["stale"] if s["id"] == "TRK-0614")
    assert trk_finding["log_date"] == "2026-11-07"
    assert trk_finding["backlog_line"] == 3


def test_nov9_human_output_reports_stale(tmp_path):
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", NOV9_BACKLOG_OPEN)
    proc = run_cli(log, backlog)
    assert proc.returncode == 1
    assert "VERDICT: STALE" in proc.stdout
    assert "TRK-0614" in proc.stdout


def test_nov9_struck_item_is_clean(tmp_path):
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", NOV9_BACKLOG_STRUCK)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["verdict"] == "CLEAN"
    assert data["stale"] == []
    assert data["counts"]["backlog_struck"] == 1
    assert data["counts"]["backlog_open"] == 1


def test_stale_via_pr_number_only(tmp_path):
    # Backlog bullet carries no TRK id — the shared PR number alone
    # must be enough to flag it.
    backlog_text = (
        "# Backlog\n\n"
        "- **Live-device mode for the sweep tool** — follow-up to PR #358.\n"
    )
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 1
    assert data["verdict"] == "STALE"
    assert [s["id"] for s in data["stale"]] == ["PR #358"]
    assert data["stale"][0]["log_date"] == "2026-11-07"


def test_stale_via_pr_prefixed_repo_hash(tmp_path):
    # "PR repo#NNN" counts — the PR word supplies the context.
    backlog_text = "# Backlog\n\n- **Sweep follow-up** — see PR quantum#358.\n"
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 1
    assert "PR #358" in {s["id"] for s in data["stale"]}


def test_bare_repo_hash_is_not_a_pr_reference(tmp_path):
    # A bare repo#NNN is an issue/cross-reference, not a PR: the real
    # backlog's "Implement the hub-api#102 server fix" item was
    # false-flagged when repo#NNN counted as a shipped PR.
    log_text = (
        "# Log\n\n"
        "- 2026-11-07 — Thing shipped; server bug filed as hub-api#102.\n"
        "- 2026-11-08 — Other thing (TRK-0614, PR #358).\n"
    )
    backlog_text = (
        "# Backlog\n\n"
        "- **Implement the hub-api#102 server fix** — pick one offset semantics.\n"
        "- **Unrelated** — see quantum#358 for context.\n"
    )
    log = write(tmp_path, "log.md", log_text)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["stale"] == []


# --- CITED (acknowledged prior build: WARN, never FAIL) --------------------


def test_built_clause_is_cited_not_stale(tmp_path):
    # The real adoption shape: "Wire X into ... — built <date> (TRK, PR)".
    backlog_text = (
        "# Backlog\n\n"
        "- **Wire the sweep tool into the checklist** — built 2026-11-07 "
        "(TRK-0614, draft PR #358). Once merged: run it before every wipe.\n"
    )
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["verdict"] == "CLEAN"
    assert data["stale"] == []
    assert {c["id"] for c in data["cited"]} == {"TRK-0614", "PR #358"}


def test_after_merges_condition_is_cited(tmp_path):
    backlog_text = (
        "# Backlog\n\n"
        "- **Wire settle-check into verification** — after PR #358 merges: "
        "handoff manifests get checked before verdicts.\n"
    )
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["stale"] == []
    assert [c["id"] for c in data["cited"]] == ["PR #358"]


def test_version_extension_leadin_is_cited(tmp_path):
    backlog_text = (
        "# Backlog\n\n"
        "- **sweep tool: remote claim types** — v2: manifest entries that "
        "verify a PR's head SHA (done by hand today for PR #358).\n"
    )
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["stale"] == []
    assert [c["id"] for c in data["cited"]] == ["PR #358"]


def test_struck_bullet_with_logged_trk_is_not_stale(tmp_path):
    # Explicitly: struck + in the log = already handled, NOT stale.
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", NOV9_BACKLOG_STRUCK)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert all(s["id"] != "TRK-0614" for s in data["stale"])


# --- CLEAN -----------------------------------------------------------------


def test_clean_backlog_with_unrelated_open_items(tmp_path):
    log_text = (
        "# Log\n\n"
        "- 2026-11-10 — Some shipped thing (TRK-0700, PR #400, merged abc1234).\n"
        "- 2026-11-11 — Another shipped thing (TRK-0701, PR #401).\n"
    )
    backlog_text = (
        "# Backlog\n\n"
        "- **Fresh idea one** — nothing shipped yet (TRK-0800).\n"
        "- **Fresh idea two** — also new, PR #999 someday.\n"
        "  - sub-bullet with a detail and no ids\n"
    )
    log = write(tmp_path, "log.md", log_text)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["verdict"] == "CLEAN"
    assert data["counts"] == {
        "log_entries": 2,
        "backlog_open": 3,  # the indented sub-bullet counts too
        "backlog_struck": 0,
    }


def test_hyphen_separator_log_lines_parse(tmp_path):
    # The "- YYYY-MM-DD - " variant must parse as a log entry.
    log = write(tmp_path, "log.md", "# Log\n\n- 2026-11-07 - Thing (TRK-0614, PR #358).\n")
    backlog = write(tmp_path, "backlog.md", NOV9_BACKLOG_OPEN)
    proc, data = run_json(log, backlog)
    assert data["counts"]["log_entries"] == 1
    assert proc.returncode == 1  # and the stale check still bites


# --- GAP (WARN only) --------------------------------------------------------


def test_gap_five_days_apart_warns_but_stays_clean(tmp_path):
    log_text = (
        "# Log\n\n"
        "- 2026-11-01 — First build (TRK-0600, PR #340).\n"
        "- 2026-11-06 — Second build (TRK-0601, PR #341).\n"
    )
    log = write(tmp_path, "log.md", log_text)
    backlog = write(tmp_path, "backlog.md", "# Backlog\n\n- **Unrelated open idea**.\n")
    proc, data = run_json(log, backlog)  # default --max-gap-days 4
    assert proc.returncode == 0  # WARN never fails the run
    assert data["verdict"] == "CLEAN"
    assert len(data["gaps"]) == 1
    assert data["gaps"][0]["from"] == "2026-11-01"
    assert data["gaps"][0]["to"] == "2026-11-06"
    assert data["gaps"][0]["gap_days"] == 5


def test_gap_within_limit_and_custom_limit(tmp_path):
    log_text = (
        "# Log\n\n"
        "- 2026-11-01 — First build.\n"
        "- 2026-11-06 — Second build.\n"
    )
    log = write(tmp_path, "log.md", log_text)
    backlog = write(tmp_path, "backlog.md", "# Backlog\n\n- **Unrelated open idea**.\n")
    proc, data = run_json(log, backlog, "--max-gap-days", "7")
    assert proc.returncode == 0
    assert data["gaps"] == []


def test_duplicate_log_dates_do_not_create_gaps(tmp_path):
    # Two builds on one day + one the next: distinct dates are 1 apart.
    log_text = (
        "# Log\n\n"
        "- 2026-11-01 — Morning build.\n"
        "- 2026-11-01 — Evening build.\n"
        "- 2026-11-02 — Next build.\n"
    )
    log = write(tmp_path, "log.md", log_text)
    backlog = write(tmp_path, "backlog.md", "# Backlog\n\n- **Unrelated open idea**.\n")
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["gaps"] == []
    assert data["counts"]["log_entries"] == 3


# --- INCOMPLETE (exit 2, no verdict) ---------------------------------------


def test_missing_log_file_is_incomplete(tmp_path):
    backlog = write(tmp_path, "backlog.md", NOV9_BACKLOG_OPEN)
    proc, data = run_json(tmp_path / "does-not-exist.md", backlog)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["errors"]


def test_missing_backlog_file_is_incomplete(tmp_path):
    log = write(tmp_path, "log.md", NOV9_LOG)
    proc = run_cli(log, tmp_path / "nope.md")
    assert proc.returncode == 2
    assert "VERDICT: INCOMPLETE" in proc.stdout


def test_empty_log_is_incomplete(tmp_path):
    log = write(tmp_path, "log.md", "# Evolution build log\n\nNothing here yet.\n")
    backlog = write(tmp_path, "backlog.md", NOV9_BACKLOG_OPEN)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["counts"]["log_entries"] == 0


def test_unparseable_backlog_is_incomplete(tmp_path):
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", "Prose only, no bullets at all.\n")
    proc, data = run_json(log, backlog)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"


# --- Read-only guarantee -----------------------------------------------------


def test_inputs_are_never_modified(tmp_path):
    log = write(tmp_path, "log.md", NOV9_LOG)
    backlog = write(tmp_path, "backlog.md", NOV9_BACKLOG_OPEN)
    before = (log.read_bytes(), backlog.read_bytes())
    run_cli(log, backlog)
    run_cli(log, backlog, "--json")
    assert (log.read_bytes(), backlog.read_bytes()) == before


# --- v2: per-id acknowledgment (segments) ----------------------------------
# v1 judged acknowledgment per bullet: one marker anywhere cited every
# shared id in the bullet.  v2 judges per shared id: an id is CITED
# only when an occurrence of that id lies inside an acknowledged
# segment (or the bullet carries the vN lead-in exception).

V2_LOG = """\
# Evolution build log

- 2026-11-07 — Alpha tool (TRK-1001, PR #501, merged aaa1111).
- 2026-11-08 — Beta tool (TRK-1002, PR #502, merged bbb2222).
"""


def test_v2_mixed_bullet_trk_cited_and_stale(tmp_path):
    # (1) The built clause cites TRK-1001 in its own segment; TRK-1002
    # sits in a later plain segment and must STALE on its own.
    backlog_text = (
        "# Backlog\n\n"
        "- **Adoption notes** — Alpha built 2026-11-07 (TRK-1001). "
        "Beta is also listed here (TRK-1002) with no acknowledgment.\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 1
    assert data["verdict"] == "STALE"
    assert [c["id"] for c in data["cited"]] == ["TRK-1001"]
    assert [s["id"] for s in data["stale"]] == ["TRK-1002"]


def test_v2_mixed_bullet_pr_cited_and_stale(tmp_path):
    # (2) Same per-id split for PR numbers.
    backlog_text = (
        "# Backlog\n\n"
        "- **Adoption notes** — Alpha built 2026-11-07 (PR #501). "
        "Beta is re-listed here (PR #502) plainly.\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 1
    assert data["verdict"] == "STALE"
    assert [c["id"] for c in data["cited"]] == ["PR #501"]
    assert [s["id"] for s in data["stale"]] == ["PR #502"]


def test_v2_second_occurrence_in_acknowledged_segment_cites(tmp_path):
    # (3) The first occurrence is plain; a second occurrence inside an
    # acknowledged segment still cites the id.
    backlog_text = (
        "# Backlog\n\n"
        "- **Notes** — Beta (TRK-1002) is listed here. "
        "It was built 2026-11-08 (TRK-1002) as the Beta tool.\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["verdict"] == "CLEAN"
    assert data["stale"] == []
    assert [c["id"] for c in data["cited"]] == ["TRK-1002"]


def test_v2_merges_list_segment_cites_each_listed_pr(tmp_path):
    # (4) The list-governing shape from the real backlog: PRs listed
    # in one segment governed by "as each merges" are all cited.
    backlog_text = (
        "# Backlog\n\n"
        "- **Wire the tools into the workflow** — pending PR queue "
        "(#501, #502) as each merges; ad-hoc checks until then.\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["stale"] == []
    assert {c["id"] for c in data["cited"]} == {"PR #501", "PR #502"}


def test_v2_is_now_done_note_segment_cites_id_after_emdash(tmp_path):
    # (5) A NOTE sentence asserting "is now done" cites its id, even
    # when the id sits after an em-dash in the same sentence (an
    # em-dash is not a segment boundary).
    backlog_text = (
        "# Backlog\n\n"
        "- **Wire the audit tool** — follow-ups still pending. "
        "NOTE 2026-11-16: the discoverability half of this adoption "
        "is now done — use the skill (TRK-1001) for the procedure.\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["stale"] == []
    assert [c["id"] for c in data["cited"]] == ["TRK-1001"]


def test_v2_segment_isolation_built_clause_does_not_leak(tmp_path):
    # (6) A built clause in sentence 1 (carrying no id) does NOT cite
    # an id that only appears in sentence 2.
    backlog_text = (
        "# Backlog\n\n"
        "- **Notes** — Alpha built 2026-11-07. "
        "Beta (TRK-1002) is re-listed here.\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 1
    assert data["verdict"] == "STALE"
    assert data["cited"] == []
    assert [s["id"] for s in data["stale"]] == ["TRK-1002"]


def test_v2_leadin_cites_all_ids_in_bullet(tmp_path):
    # (7) The one bullet-level exception kept from v1: a vN lead-in
    # cites every shared id in the bullet, across all segments.
    backlog_text = (
        "# Backlog\n\n"
        "- **Alpha tool: remote claims** — v2: extend the manifest "
        "(TRK-1001, PR #501). Also re-check Beta (TRK-1002, PR #502) "
        "later with no acknowledgment clause.\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 0
    assert data["stale"] == []
    assert {c["id"] for c in data["cited"]} == {
        "TRK-1001",
        "TRK-1002",
        "PR #501",
        "PR #502",
    }
    assert all(c["acknowledged_via"] == "lead-in" for c in data["cited"])


def test_v2_done_date_label_alone_is_stale(tmp_path):
    # (8) Nov 15, 2026 regression pin: a bare "DONE <date> (… TRK-…)"
    # progress label matches no acknowledgment marker — still STALE.
    backlog_text = (
        "# Backlog\n\n"
        "- **Backfill progress** — DONE 2026-11-07 (Alpha build, TRK-1001).\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 1
    assert data["verdict"] == "STALE"
    assert data["cited"] == []
    assert [s["id"] for s in data["stale"]] == ["TRK-1001"]


def test_v2_json_cited_findings_carry_acknowledged_via(tmp_path):
    # (9) JSON contract is additive only: cited findings gain
    # acknowledged_via ("segment" here); stale findings are unchanged
    # (no acknowledged_via key).
    backlog_text = (
        "# Backlog\n\n"
        "- **Adoption notes** — Alpha built 2026-11-07 (TRK-1001). "
        "Beta is also listed here (TRK-1002) with no acknowledgment.\n"
    )
    log = write(tmp_path, "log.md", V2_LOG)
    backlog = write(tmp_path, "backlog.md", backlog_text)
    proc, data = run_json(log, backlog)
    assert proc.returncode == 1
    assert data["cited"][0]["acknowledged_via"] == "segment"
    assert "acknowledged_via" not in data["stale"][0]
