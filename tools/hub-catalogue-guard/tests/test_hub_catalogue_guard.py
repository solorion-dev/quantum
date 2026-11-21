"""Tests for hub-catalogue-guard (stdlib + pytest only).

Every test drives the real CLI in a subprocess so exit codes, human
output, and JSON output are exercised exactly as a run would use them.
Fixtures are written to pytest's tmp_path; the tool is read-only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "hub_catalogue_guard.py"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

BASE = ["alpha_tool", "beta_tool", "quantum_skills_find",
        "quantum_skills_get", "quantum_skills_list"]


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def run_cli(base, candidate, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SRC), "--base", str(base),
         "--candidate", str(candidate), *extra],
        capture_output=True, text=True, timeout=60,
    )


def run_json(base, candidate, *extra: str):
    proc = run_cli(base, candidate, "--json", *extra)
    return proc, json.loads(proc.stdout)


def json_list(tmp_path, name, names):
    return write(tmp_path, name, json.dumps(names))


# 1 — JSON list form parses and identical snapshots are SAFE
def test_json_list_form_safe(tmp_path):
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(b, c)
    assert proc.returncode == 0
    assert "SAFE" in proc.stdout


# 2 — tools-object form (entries as objects with name)
def test_tools_object_form(tmp_path):
    b = write(tmp_path, "b.json", json.dumps(
        {"tools": [{"name": n} for n in BASE]}))
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(b, c)
    assert proc.returncode == 0


# 3 — tools/list nested form
def test_tools_list_nested_form(tmp_path):
    b = write(tmp_path, "b.json", json.dumps(
        {"result": {"tools": [{"name": n} for n in BASE]}}))
    c = write(tmp_path, "c.json", json.dumps(
        {"result": {"tools": [n for n in BASE]}}))
    proc = run_cli(b, c)
    assert proc.returncode == 0


# 4 — TOOL_DEFS JSON-object form
def test_tool_defs_json_form(tmp_path):
    b = write(tmp_path, "b.json", json.dumps({"TOOL_DEFS": BASE}))
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(b, c)
    assert proc.returncode == 0


# 5 — TOOL_DEFS JS extraction
def test_tool_defs_js_extraction(tmp_path):
    js = "const TOOL_DEFS = [\n" + ",\n".join(
        f"  {{ name: '{n}', description: 'x' }}" for n in BASE) + "\n];\n"
    b = write(tmp_path, "b.js", js)
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(b, c)
    assert proc.returncode == 0


# 6 — name entries BEFORE TOOL_DEFS are ignored
def test_names_before_tool_defs_ignored(tmp_path):
    js = ("const OTHER = [{ name: 'ghost_tool' }];\n"
          "const TOOL_DEFS = [\n"
          + ",\n".join(f"  {{ name: \"{n}\" }}" for n in BASE) + "\n];\n")
    b = write(tmp_path, "b.js", js)
    c = json_list(tmp_path, "c.json", BASE)
    proc, payload = run_json(b, c)
    assert proc.returncode == 0
    assert payload["counts"]["base"] == len(BASE)


# 7 — txt form (one per line, comments and blanks skipped)
def test_txt_form(tmp_path):
    b = write(tmp_path, "b.txt", "# comment\n\n" + "\n".join(BASE) + "\n")
    c = write(tmp_path, "c.txt", "\n".join(BASE) + "\n")
    proc = run_cli(b, c)
    assert proc.returncode == 0


# 8 — added-only is SAFE and reports the addition
def test_added_only_safe(tmp_path):
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", BASE + ["new_tool"])
    proc, payload = run_json(b, c)
    assert proc.returncode == 0
    assert payload["verdict"] == "SAFE"
    assert payload["added"] == ["new_tool"]


# 9 — removal is DEREGISTER exit 1 naming the tools
def test_removal_deregister(tmp_path):
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", [n for n in BASE if n != "beta_tool"])
    proc = run_cli(b, c)
    assert proc.returncode == 1
    assert "DEREGISTER" in proc.stdout
    assert "beta_tool" in proc.stdout


# 10 — PR #133 fixture: exactly the three skills tools missing
def test_pr133_fixture(tmp_path):
    missing = ["quantum_skills_find", "quantum_skills_get", "quantum_skills_list"]
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", [n for n in BASE if n not in missing])
    proc, payload = run_json(b, c)
    assert proc.returncode == 1
    assert payload["verdict"] == "DEREGISTER"
    assert payload["removed"] == sorted(missing)


# 11 — allowlisted removal (via --allow) is SAFE and reported
def test_allowlisted_removal_safe(tmp_path):
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", [n for n in BASE if n != "beta_tool"])
    proc, payload = run_json(b, c, "--allow", "beta_tool")
    assert proc.returncode == 0
    assert payload["verdict"] == "SAFE"
    assert payload["allowed_removals"] == ["beta_tool"]
    assert payload["removed"] == []


# 12 — allowlisted removal via --allow-removal file
def test_allow_removal_file(tmp_path):
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", [n for n in BASE if n != "beta_tool"])
    allow = write(tmp_path, "allow.json", json.dumps(["beta_tool"]))
    proc, payload = run_json(b, c, "--allow-removal", str(allow))
    assert proc.returncode == 0
    assert payload["allowed_removals"] == ["beta_tool"]


# 13 — stale allowance is a warning, verdict unchanged
def test_stale_allowance_warning(tmp_path):
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", BASE)
    proc, payload = run_json(b, c, "--allow", "never_removed_tool")
    assert proc.returncode == 0
    assert payload["stale_allowances"] == ["never_removed_tool"]


# 14 — duplicate names are INCOMPLETE and named
def test_duplicate_names_incomplete(tmp_path):
    b = json_list(tmp_path, "b.json", BASE + ["alpha_tool"])
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(b, c)
    assert proc.returncode == 2
    assert "INCOMPLETE" in proc.stdout
    assert "alpha_tool" in proc.stdout


# 15 — empty snapshot is INCOMPLETE (never SAFE)
def test_empty_snapshot_incomplete(tmp_path):
    b = json_list(tmp_path, "b.json", [])
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(b, c)
    assert proc.returncode == 2
    assert "INCOMPLETE" in proc.stdout


# 16 — missing file is INCOMPLETE
def test_missing_file_incomplete(tmp_path):
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(tmp_path / "nope.json", c)
    assert proc.returncode == 2
    assert "INCOMPLETE" in proc.stdout


# 17 — unparseable input is INCOMPLETE
def test_unparseable_incomplete(tmp_path):
    b = write(tmp_path, "b.json", "{not json at all,,,")
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(b, c)
    assert proc.returncode == 2
    assert "INCOMPLETE" in proc.stdout


# 18 — JS without TOOL_DEFS is INCOMPLETE
def test_js_without_tool_defs_incomplete(tmp_path):
    b = write(tmp_path, "b.js", "const x = [{ name: 'alpha_tool' }];\n")
    c = json_list(tmp_path, "c.json", BASE)
    proc = run_cli(b, c)
    assert proc.returncode == 2
    assert "INCOMPLETE" in proc.stdout


# 19 — case sensitivity: Quantum_X differs from quantum_x
def test_case_sensitivity(tmp_path):
    b = json_list(tmp_path, "b.json", ["quantum_x"])
    c = json_list(tmp_path, "c.json", ["Quantum_X"])
    proc, payload = run_json(b, c)
    assert proc.returncode == 1
    assert payload["removed"] == ["quantum_x"]
    assert payload["added"] == ["Quantum_X"]


# 20 — read-only guarantee: input bytes and mtimes unchanged
def test_read_only_guarantee(tmp_path):
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", BASE + ["new_tool"])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (b, c)}
    proc = run_cli(b, c)
    assert proc.returncode == 0
    for p, (data, mtime) in before.items():
        assert p.read_bytes() == data
        assert p.stat().st_mtime_ns == mtime


# 21 — --json shape carries every documented key
def test_json_shape(tmp_path):
    b = json_list(tmp_path, "b.json", BASE)
    c = json_list(tmp_path, "c.json", BASE)
    proc, payload = run_json(b, c)
    assert proc.returncode == 0
    for key in ("verdict", "counts", "added", "removed",
                "allowed_removals", "stale_allowances"):
        assert key in payload
    for key in ("base", "candidate", "added", "removed", "allowed"):
        assert key in payload["counts"]
    assert payload["counts"]["base"] == len(BASE)


# 22 — shipped examples run: safe exits 0, deregister exits 1
def test_examples_run():
    safe = run_cli(EXAMPLES / "base.json", EXAMPLES / "candidate-safe.json")
    assert safe.returncode == 0
    dereg = run_cli(EXAMPLES / "base.json",
                    EXAMPLES / "candidate-deregister.json")
    assert dereg.returncode == 1
    assert "quantum_skills_list" in dereg.stdout


# 23 — usage error exits 2 with NO verdict line
def test_usage_error_no_verdict_line():
    proc = subprocess.run(
        [sys.executable, str(SRC), "--base", "only.json"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2
    combined = proc.stdout + proc.stderr
    assert "INCOMPLETE" not in combined
    assert "DEREGISTER" not in combined
