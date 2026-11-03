"""Tests for proof-check.

Writes real manifest JSON files to temp dirs and runs the tool as
a subprocess, so exit codes and --json output are exercised
exactly as in the field.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = TOOL_DIR / "src" / "proof_check.py"
EXAMPLE = TOOL_DIR / "proof-check.example.json"


# ---------------------------------------------------------------- helpers

def write_manifest(tmp_path: Path, data, name="manifest.json") -> Path:
    p = tmp_path / name
    if isinstance(data, str):
        p.write_text(data, encoding="utf-8")
    else:
        p.write_text(json.dumps(data), encoding="utf-8")
    return p


def claim(cid, ctype, evidence, statement="a claim"):
    return {"id": cid, "type": ctype, "statement": statement, "evidence": evidence}


def ev(kind, detail="some evidence", **extra):
    item = {"kind": kind, "detail": detail}
    item.update(extra)
    return item


def run_tool(manifest: Path, use_json=True):
    cmd = [sys.executable, str(SCRIPT), str(manifest)]
    if use_json:
        cmd.append("--json")
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = None
    if use_json and result.stdout.strip():
        try:
            data = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception:
            data = None
    return result, data


def single(tmp_path, ctype, evidence):
    manifest = write_manifest(tmp_path, {"claims": [claim("c1", ctype, evidence)]})
    return run_tool(manifest)


# ------------------------------------------------- supported at exact level

@pytest.mark.parametrize("ctype,kind,level", [
    ("received", "receipt", 1),
    ("exists", "existence", 2),
    ("complete", "content_read", 3),
    ("copied", "delta_compare", 3),
    ("absent", "source_search", 3),
    ("identity", "hard_identifier", 3),
    ("works", "real_session", 4),
    ("fixed", "public_path", 4),
    ("healthy", "endtoend_run", 4),
])
def test_supported_at_exact_level(tmp_path, ctype, kind, level):
    proc, data = single(tmp_path, ctype, [ev(kind)])
    assert data is not None, proc.stdout + proc.stderr
    assert proc.returncode == 0
    assert data["verdict"] == "SUPPORTED"
    assert data["exit_code"] == 0
    got = data["claims"][0]
    assert got["verdict"] == "SUPPORTED"
    assert got["required_level"] == level
    assert got["best_level"] == level


def test_complete_also_supported_by_delta_compare(tmp_path):
    proc, data = single(tmp_path, "complete", [ev("delta_compare")])
    assert proc.returncode == 0
    assert data["claims"][0]["verdict"] == "SUPPORTED"


def test_copied_also_supported_by_content_read(tmp_path):
    proc, data = single(tmp_path, "copied", [ev("content_read")])
    assert proc.returncode == 0
    assert data["claims"][0]["verdict"] == "SUPPORTED"


def test_stronger_evidence_than_required_supports(tmp_path):
    # a level-4 real session more than covers an exists claim
    proc, data = single(tmp_path, "exists", [ev("real_session")])
    assert proc.returncode == 0
    assert data["claims"][0]["verdict"] == "SUPPORTED"
    assert data["claims"][0]["best_level"] == 4


# ------------------------------------------------------- the origin failures

def test_receipt_does_not_prove_complete(tmp_path):
    proc, data = single(tmp_path, "complete", [ev("receipt"), ev("status_report")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 1
    assert got["required_level"] == 3


def test_probe_does_not_prove_works(tmp_path):
    proc, data = single(tmp_path, "works", [ev("probe")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 2
    assert got["required_level"] == 4


def test_progress_does_not_prove_copied(tmp_path):
    proc, data = single(tmp_path, "copied", [ev("progress_output")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 1


def test_agent_report_capped_at_receipt_even_for_works(tmp_path):
    # an agent's say-so is level 1 no matter how strong the claim is
    proc, data = single(tmp_path, "works", [ev("agent_report")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 1
    assert got["best_level_name"] == "receipt"


def test_absent_with_surface_evidence_but_no_source_search_overclaimed(tmp_path):
    proc, data = single(tmp_path, "absent", [ev("search_snippet")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert "source_search" in got["reason"]


def test_absent_kind_rule_beats_level(tmp_path):
    # content_read meets the level (3) but a negative still needs a
    # source search — the kind requirement decides on its own
    proc, data = single(tmp_path, "absent", [ev("content_read")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 3
    assert got["required_level"] == 3
    assert "source_search" in got["reason"]


def test_identity_with_content_read_but_no_hard_identifier_overclaimed(tmp_path):
    proc, data = single(tmp_path, "identity", [ev("content_read")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 3
    assert got["required_level"] == 3
    assert "hard_identifier" in got["reason"]


def test_complete_with_level_but_wrong_kind_overclaimed(tmp_path):
    # output_file_read is level 3, but complete names content_read
    # or delta_compare specifically
    proc, data = single(tmp_path, "complete", [ev("output_file_read")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 3


def test_works_with_content_but_no_endtoend_kind_overclaimed(tmp_path):
    proc, data = single(tmp_path, "healthy", [ev("content_read"), ev("delta_compare")])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 3
    assert got["required_level"] == 4


# ------------------------------------------------------------- unsupported

def test_discounted_evidence_ignored_gives_unsupported(tmp_path):
    proc, data = single(tmp_path, "works", [
        ev("real_session", discounted=True, discount_reason="foreign session id"),
    ])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "UNSUPPORTED"
    assert got["best_level"] == 0
    # the discounted item is still reported, marked as not counted
    assert got["evidence"][0]["discounted"] is True
    assert got["evidence"][0]["counted"] is False


def test_discounted_plus_countable_still_counts_the_countable(tmp_path):
    proc, data = single(tmp_path, "received", [
        ev("real_session", discounted=True, discount_reason="untrusted delivery"),
        ev("receipt"),
    ])
    assert proc.returncode == 0
    got = data["claims"][0]
    assert got["verdict"] == "SUPPORTED"
    assert got["best_level"] == 1


def test_no_evidence_unsupported(tmp_path):
    proc, data = single(tmp_path, "exists", [])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "UNSUPPORTED"
    assert got["best_level"] == 0
    assert got["best_level_name"] == "none"


# -------------------------------------------------------------- incomplete

def test_invalid_json_incomplete(tmp_path):
    manifest = write_manifest(tmp_path, "{not valid json")
    proc, data = run_tool(manifest)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["exit_code"] == 2
    assert data["claims"] == []
    assert data["errors"]


def test_empty_claims_incomplete(tmp_path):
    manifest = write_manifest(tmp_path, {"claims": []})
    proc, data = run_tool(manifest)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["claims"] == []


def test_missing_claims_key_incomplete(tmp_path):
    manifest = write_manifest(tmp_path, {"something_else": True})
    proc, data = run_tool(manifest)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"


def test_unknown_claim_type_incomplete(tmp_path):
    manifest = write_manifest(tmp_path, {"claims": [claim("c1", "proven", [ev("receipt")])]})
    proc, data = run_tool(manifest)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["claims"] == []
    assert any("unknown claim type" in e for e in data["errors"])


def test_unknown_evidence_kind_incomplete(tmp_path):
    manifest = write_manifest(tmp_path, {"claims": [claim("c1", "received", [ev("vibes")])]})
    proc, data = run_tool(manifest)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["claims"] == []
    assert any("unknown evidence kind" in e for e in data["errors"])


def test_missing_fields_incomplete(tmp_path):
    # claim missing 'statement'
    bad_claim = {"id": "c1", "type": "received", "evidence": [ev("receipt")]}
    manifest = write_manifest(tmp_path, {"claims": [bad_claim]})
    proc, data = run_tool(manifest)
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"

    # evidence missing 'detail'
    bad_ev = {"id": "c2", "type": "received", "statement": "s",
              "evidence": [{"kind": "receipt"}]}
    manifest2 = write_manifest(tmp_path, {"claims": [bad_ev]}, name="m2.json")
    proc2, data2 = run_tool(manifest2)
    assert proc2.returncode == 2
    assert data2["verdict"] == "INCOMPLETE"


def test_missing_manifest_file_incomplete(tmp_path):
    proc, data = run_tool(tmp_path / "does-not-exist.json")
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["claims"] == []


# ------------------------------------------------------- output and overall

def test_json_output_shape(tmp_path):
    proc, data = single(tmp_path, "complete", [ev("content_read")])
    assert proc.returncode == 0
    assert data is not None
    for key in ("verdict", "exit_code", "manifest", "claims", "errors"):
        assert key in data
    got = data["claims"][0]
    for key in ("id", "type", "statement", "verdict", "required_level",
                "required_level_name", "best_level", "best_level_name",
                "reason", "evidence"):
        assert key in got
    ev0 = got["evidence"][0]
    for key in ("kind", "level", "level_name", "detail", "discounted", "counted"):
        assert key in ev0
    assert isinstance(data["errors"], list)


def test_mixed_manifest_overall_exit_1(tmp_path):
    manifest = write_manifest(tmp_path, {"claims": [
        claim("good", "received", [ev("receipt")]),
        claim("bad", "works", [ev("probe")]),
        claim("ugly", "exists", []),
    ]})
    proc, data = run_tool(manifest)
    assert proc.returncode == 1
    assert data["exit_code"] == 1
    verdicts = {c["id"]: c["verdict"] for c in data["claims"]}
    assert verdicts == {"good": "SUPPORTED", "bad": "OVERCLAIMED", "ugly": "UNSUPPORTED"}
    # overall verdict is the weakest claim's verdict
    assert data["verdict"] == "UNSUPPORTED"


def test_all_supported_exit_0(tmp_path):
    manifest = write_manifest(tmp_path, {"claims": [
        claim("a", "received", [ev("status_report")]),
        claim("b", "identity", [ev("hard_identifier")]),
        claim("c", "fixed", [ev("public_path")]),
    ]})
    proc, data = run_tool(manifest)
    assert proc.returncode == 0
    assert data["verdict"] == "SUPPORTED"
    assert all(c["verdict"] == "SUPPORTED" for c in data["claims"])


def test_human_output_lines(tmp_path):
    manifest = write_manifest(tmp_path, {"claims": [
        claim("ok-one", "received", [ev("receipt")]),
        claim("weak-one", "works", [ev("probe")]),
    ]})
    proc, data = run_tool(manifest, use_json=False)
    assert proc.returncode == 1
    out = proc.stdout
    assert "proof-check:" in out
    assert "ok-one: SUPPORTED" in out
    assert "weak-one: OVERCLAIMED" in out
    assert "required level 4 (endtoend)" in out
    assert "best evidence level 2 (surface)" in out
    assert "exit: 1" in out


def test_example_manifest_all_weak(tmp_path):
    # the shipped example encodes the six Oct 26-27 incidents in
    # their original weak-evidence form: none may come out SUPPORTED
    proc, data = run_tool(EXAMPLE)
    assert proc.returncode == 1
    assert len(data["claims"]) == 6
    for c in data["claims"]:
        assert c["verdict"] in ("OVERCLAIMED", "UNSUPPORTED"), c
    by_id = {c["id"]: c["verdict"] for c in data["claims"]}
    assert by_id["aflac-employer-verification-complete"] == "OVERCLAIMED"
    assert by_id["sunshine-streaming-works"] == "OVERCLAIMED"
    assert by_id["downloads-trash-copy-complete"] == "OVERCLAIMED"
    assert by_id["hive-entries-filed"] == "UNSUPPORTED"
    assert by_id["sweetser-never-admitted"] == "OVERCLAIMED"
    assert by_id["dp4-display-identity"] == "OVERCLAIMED"


# =============================================================== v2 tests
# Freshness (observed_at / stale / invalid / --now) and auto-evidence
# (--evidence-from settle-check / merge-verify artifacts).

import os
from datetime import datetime, timezone

NOW = "2026-11-03T12:00:00+00:00"
ART_MTIME = datetime(2026, 11, 3, 11, 30, tzinfo=timezone.utc)


def run_args(manifest: Path, extra, use_json=True):
    cmd = [sys.executable, str(SCRIPT), str(manifest)]
    cmd.extend(extra)
    if use_json:
        cmd.append("--json")
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = None
    if use_json and result.stdout.strip():
        try:
            data = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception:
            data = None
    return result, data


def write_artifact(tmp_path: Path, data, name="artifact.json", mtime=ART_MTIME) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    ts = mtime.timestamp()
    os.utime(p, (ts, ts))
    return p


def settle_artifact(status="verified", **extra):
    # REAL settle-check --json shape (src/settle_check.py, read
    # 2026-11-03): {"claim", "status", "problems", "notes"} — the
    # verdict word is the lowercase `status`; no timestamp field.
    art = {"claim": "a delegated claim", "status": status,
           "problems": [], "notes": ["settled and checked"]}
    art.update(extra)
    return art


def merge_artifact(verdict="VERIFIED", **extra):
    # REAL merge-verify --json shape (src/merge_verify.py, read
    # 2026-11-03): {"verdict", "exit_code", "repo", "head", ...,
    # "checks": [...], "errors", "config_source", "discovered"} —
    # no timestamp field.
    art = {"verdict": verdict, "exit_code": 0, "repo": "/repo",
           "head": "abc1234", "expect_head_ok": True,
           "expect_ancestor_ok": None, "tree_clean_before": True,
           "tree_clean_after": True,
           "checks": [{"name": "test", "exit_code": 0, "duration_s": 1.0,
                       "timed_out": False, "tail": ""}],
           "errors": [], "config_source": "file", "discovered": []}
    art.update(extra)
    return art


def dated(kind, observed_at, **extra):
    return ev(kind, observed_at=observed_at, **extra)


# ------------------------------------------------------------- freshness

def test_fresh_evidence_within_window_supports(tmp_path):
    proc, data = run_args(
        write_manifest(tmp_path, {"claims": [claim("c1", "works", [
            dated("real_session", "2026-11-03T11:00:00+00:00")])]}),
        ["--now", NOW])
    assert proc.returncode == 0
    got = data["claims"][0]
    assert got["verdict"] == "SUPPORTED"
    ev0 = got["evidence"][0]
    assert ev0["freshness"] == "fresh"
    assert ev0["counted"] is True
    assert ev0["age_seconds"] == 3600
    assert ev0["max_age_seconds"] == 24 * 3600


def test_stale_works_evidence_does_not_count(tmp_path):
    # works claims allow only 24h: a real session from 25h ago is stale
    proc, data = run_args(
        write_manifest(tmp_path, {"claims": [claim("c1", "works", [
            dated("real_session", "2026-11-02T11:00:00+00:00")])]}),
        ["--now", NOW])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "UNSUPPORTED"
    assert got["best_level"] == 0
    assert "stale" in got["reason"]
    ev0 = got["evidence"][0]
    assert ev0["freshness"] == "stale"
    assert ev0["stale"] is True
    assert ev0["counted"] is False
    assert ev0["age_seconds"] == 25 * 3600


def test_freshness_boundary_exact_max_age_is_fresh(tmp_path):
    proc, data = run_args(
        write_manifest(tmp_path, {"claims": [claim("c1", "works", [
            dated("real_session", "2026-11-02T12:00:00+00:00")])]}),
        ["--now", NOW])
    assert proc.returncode == 0
    assert data["claims"][0]["evidence"][0]["freshness"] == "fresh"
    assert data["claims"][0]["verdict"] == "SUPPORTED"


def test_freshness_boundary_one_second_over_is_stale(tmp_path):
    proc, data = run_args(
        write_manifest(tmp_path, {"claims": [claim("c1", "works", [
            dated("real_session", "2026-11-02T11:59:59+00:00")])]}),
        ["--now", NOW])
    assert proc.returncode == 1
    assert data["claims"][0]["evidence"][0]["freshness"] == "stale"
    assert data["claims"][0]["evidence"][0]["counted"] is False


@pytest.mark.parametrize("bad", ["2026-11-03T11:00:00", "not-a-date", "2026-13-40T99:99:99+00:00"])
def test_invalid_observed_at_never_counts_and_never_crashes(tmp_path, bad):
    # naive (no timezone) and unparseable values: that one entry is
    # INVALID — reported, never counted — and the run still verdicts
    proc, data = run_args(
        write_manifest(tmp_path, {"claims": [claim("c1", "complete", [
            dated("content_read", bad)])]}),
        ["--now", NOW])
    assert proc.returncode == 1  # a verdict, not exit 2 / a crash
    got = data["claims"][0]
    assert got["verdict"] == "UNSUPPORTED"
    ev0 = got["evidence"][0]
    assert ev0["freshness"] == "invalid"
    assert ev0["counted"] is False
    assert ev0["invalid_reason"]
    assert "invalid" in got["reason"]


def test_manifest_cannot_extend_max_age(tmp_path):
    # manifest tries to grant itself a year, at top level and on the
    # claim: the tool-owned 24h table wins and the attempts are flagged
    manifest = {"max_age_days": 365, "claims": [
        {"id": "c1", "type": "works", "statement": "s", "max_age_seconds": 999999999,
         "evidence": [dated("real_session", "2026-11-01T12:00:00+00:00")]}]}
    proc, data = run_args(write_manifest(tmp_path, manifest), ["--now", NOW])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["evidence"][0]["freshness"] == "stale"
    assert got["verdict"] == "UNSUPPORTED"
    assert any("max_age" in f for f in data["ignored_fields"])


def test_stale_strong_plus_fresh_weak_is_overclaimed(tmp_path):
    # the stale content_read must not lift the claim; only the fresh
    # receipt counts, and a receipt does not prove "complete"
    proc, data = run_args(
        write_manifest(tmp_path, {"claims": [claim("c1", "complete", [
            dated("content_read", "2026-10-20T12:00:00+00:00"),
            dated("receipt", "2026-11-03T11:00:00+00:00")])]}),
        ["--now", NOW])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "OVERCLAIMED"
    assert got["best_level"] == 1


def test_undated_evidence_still_counts_and_is_listed_undated(tmp_path):
    # v1 behaviour, no regression: no observed_at -> counts, "undated"
    proc, data = run_args(
        write_manifest(tmp_path, {"claims": [claim("c1", "complete", [ev("content_read")])]}),
        ["--now", NOW])
    assert proc.returncode == 0
    ev0 = data["claims"][0]["evidence"][0]
    assert ev0["freshness"] == "undated"
    assert ev0["counted"] is True
    assert ev0["age_seconds"] is None


def test_now_flag_is_deterministic_and_overrides_manifest_now(tmp_path):
    # manifest `now` is a week later (evidence would be stale);
    # the --now flag wins, so the same manifest supports
    manifest = {"now": "2026-11-10T12:00:00+00:00", "claims": [
        claim("c1", "complete", [dated("content_read", "2026-11-03T11:00:00+00:00")])]}
    p = write_manifest(tmp_path, manifest)
    proc_flag, data_flag = run_args(p, ["--now", NOW])
    assert proc_flag.returncode == 0
    assert data_flag["claims"][0]["verdict"] == "SUPPORTED"
    assert data_flag["now"].startswith("2026-11-03T12:00:00")
    # and without the flag the manifest `now` applies: stale
    proc_man, data_man = run_args(p, [])
    assert proc_man.returncode == 1
    assert data_man["claims"][0]["evidence"][0]["freshness"] == "stale"


def test_invalid_now_is_usage_error_exit_2(tmp_path):
    p = write_manifest(tmp_path, {"claims": [claim("c1", "received", [ev("receipt")])]})
    proc, data = run_args(p, ["--now", "yesterday-ish"])
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["claims"] == []
    bad_manifest = write_manifest(tmp_path, {"now": "2026-11-03 12:00",
                                              "claims": [claim("c1", "received", [ev("receipt")])]},
                                  name="m2.json")
    proc2, data2 = run_args(bad_manifest, [])
    assert proc2.returncode == 2
    assert data2["verdict"] == "INCOMPLETE"


def test_complete_max_age_is_seven_days(tmp_path):
    fresh = write_manifest(tmp_path, {"claims": [claim("c1", "complete", [
        dated("content_read", "2026-10-28T12:00:00+00:00")])]}, name="a.json")
    proc, data = run_args(fresh, ["--now", NOW])
    assert proc.returncode == 0  # 6 days old: fresh for a complete claim
    old = write_manifest(tmp_path, {"claims": [claim("c1", "complete", [
        dated("content_read", "2026-10-26T12:00:00+00:00")])]}, name="b.json")
    proc2, data2 = run_args(old, ["--now", NOW])
    assert proc2.returncode == 1  # 8 days old: stale
    assert data2["claims"][0]["evidence"][0]["freshness"] == "stale"


def test_absent_max_age_is_thirty_days(tmp_path):
    p = write_manifest(tmp_path, {"claims": [claim("c1", "absent", [
        dated("source_search", "2026-10-14T12:00:00+00:00")])]})
    proc, data = run_args(p, ["--now", NOW])
    assert proc.returncode == 0  # 20 days old: still fresh for absent
    assert data["claims"][0]["verdict"] == "SUPPORTED"


# ---------------------------------------------------------- auto-evidence

def test_settle_verified_derives_content_read(tmp_path):
    art = write_artifact(tmp_path, settle_artifact("verified"))
    p = write_manifest(tmp_path, {"claims": [claim("c1", "complete", [])]})
    proc, data = run_args(p, ["--now", NOW, "--evidence-from", str(art)])
    assert proc.returncode == 0, data
    got = data["claims"][0]
    assert got["verdict"] == "SUPPORTED"
    assert len(got["evidence"]) == 1
    ev0 = got["evidence"][0]
    assert ev0["kind"] == "content_read"
    assert ev0["level"] == 3
    assert ev0["derived"] is True
    assert "settle-check" in ev0["source"]
    # settle-check JSON has no timestamp field -> file mtime (UTC)
    assert ev0["observed_at"].startswith("2026-11-03T11:30:00")
    assert data["derived_evidence"][0]["outcome"] == "derived"


@pytest.mark.parametrize("status", ["failed", "unsettled", "error"])
def test_settle_non_verified_derives_nothing(tmp_path, status):
    art = write_artifact(tmp_path, settle_artifact(status))
    p = write_manifest(tmp_path, {"claims": [claim("c1", "complete", [])]})
    proc, data = run_args(p, ["--now", NOW, "--evidence-from", str(art)])
    assert proc.returncode == 1
    got = data["claims"][0]
    assert got["verdict"] == "UNSUPPORTED"
    assert got["evidence"] == []
    skipped = data["derived_evidence"][0]
    assert skipped["outcome"] == "skipped"
    assert status in skipped["reason"]


def test_merge_verified_derives_endtoend_run(tmp_path):
    art = write_artifact(tmp_path, merge_artifact("VERIFIED"))
    p = write_manifest(tmp_path, {"claims": [claim("c1", "works", [])]})
    proc, data = run_args(p, ["--now", NOW, "--evidence-from", str(art)])
    assert proc.returncode == 0, data
    got = data["claims"][0]
    assert got["verdict"] == "SUPPORTED"
    ev0 = got["evidence"][0]
    assert ev0["kind"] == "endtoend_run"
    assert ev0["level"] == 4
    assert ev0["derived"] is True
    assert "merge-verify" in ev0["source"]


@pytest.mark.parametrize("verdict", ["FAILED", "INCOMPLETE"])
def test_merge_non_verified_derives_nothing(tmp_path, verdict):
    art = write_artifact(tmp_path, merge_artifact(verdict))
    p = write_manifest(tmp_path, {"claims": [claim("c1", "works", [])]})
    proc, data = run_args(p, ["--now", NOW, "--evidence-from", str(art)])
    assert proc.returncode == 1
    assert data["claims"][0]["verdict"] == "UNSUPPORTED"
    assert data["claims"][0]["evidence"] == []
    assert data["derived_evidence"][0]["outcome"] == "skipped"
    assert verdict in data["derived_evidence"][0]["reason"]


def test_claim_id_linkage_targets_only_the_named_claim(tmp_path):
    art = write_artifact(tmp_path, merge_artifact("VERIFIED", claim_id="c2"))
    p = write_manifest(tmp_path, {"claims": [
        claim("c1", "works", []),
        claim("c2", "works", []),
    ]})
    proc, data = run_args(p, ["--now", NOW, "--evidence-from", str(art)])
    assert proc.returncode == 1  # c1 still unsupported -> overall exit 1
    by_id = {c["id"]: c["verdict"] for c in data["claims"]}
    assert by_id == {"c1": "UNSUPPORTED", "c2": "SUPPORTED"}
    assert data["derived_evidence"][0]["claim_id"] == "c2"


def test_ambiguous_multi_claim_without_claim_id_exit_2(tmp_path):
    art = write_artifact(tmp_path, merge_artifact("VERIFIED"))
    p = write_manifest(tmp_path, {"claims": [
        claim("c1", "works", []),
        claim("c2", "works", []),
    ]})
    proc, data = run_args(p, ["--now", NOW, "--evidence-from", str(art)])
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["claims"] == []
    assert any("claim_id" in e for e in data["errors"])


def test_claim_id_with_no_matching_claim_exit_2(tmp_path):
    art = write_artifact(tmp_path, merge_artifact("VERIFIED", claim_id="nope"))
    p = write_manifest(tmp_path, {"claims": [claim("c1", "works", [])]})
    proc, data = run_args(p, ["--now", NOW, "--evidence-from", str(art)])
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert any("nope" in e for e in data["errors"])


def test_repeatable_evidence_from_and_artifact_timestamp_field_wins(tmp_path):
    # two artifacts, two claims, linked by claim_id; the merge
    # artifact carries its own checked_at, which must be used
    # instead of its (ancient) file mtime
    settle = write_artifact(tmp_path, settle_artifact("verified", claim_id="done"),
                            name="settle.json")
    merge = write_artifact(
        tmp_path,
        merge_artifact("VERIFIED", claim_id="works",
                       checked_at="2026-11-03T11:45:00+00:00"),
        name="merge.json",
        mtime=datetime(2020, 1, 1, tzinfo=timezone.utc))
    p = write_manifest(tmp_path, {"claims": [
        claim("done", "complete", []),
        claim("works", "works", []),
    ]})
    proc, data = run_args(p, ["--now", NOW,
                              "--evidence-from", str(settle),
                              "--evidence-from", str(merge)])
    assert proc.returncode == 0, data
    by_id = {c["id"]: c for c in data["claims"]}
    assert by_id["done"]["verdict"] == "SUPPORTED"
    assert by_id["works"]["verdict"] == "SUPPORTED"
    assert by_id["works"]["evidence"][0]["observed_at"] == "2026-11-03T11:45:00+00:00"
    assert len(data["derived_evidence"]) == 2


def test_missing_evidence_file_exit_2(tmp_path):
    p = write_manifest(tmp_path, {"claims": [claim("c1", "works", [])]})
    proc, data = run_args(p, ["--now", NOW,
                              "--evidence-from", str(tmp_path / "nope.json")])
    assert proc.returncode == 2
    assert data["verdict"] == "INCOMPLETE"
    assert data["errors"]
