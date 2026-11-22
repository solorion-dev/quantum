"""Tests for codex-lint-drift (stdlib + pytest only).

Every test drives the real CLI in a subprocess so exit codes, human
output, and JSON output are exercised exactly as a run would use them.
Fixtures are written to pytest's tmp_path; the tool is read-only.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "codex_lint_drift.py"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

TEXT = "line one\nline two\nline three\n"


def write(tmp_path: Path, name: str, content) -> Path:
    p = tmp_path / name
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    return p


def run_cli(installed, canonical, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SRC), "--installed", str(installed),
         "--canonical", str(canonical), *extra],
        capture_output=True, text=True, timeout=60,
    )


def run_json(installed, canonical, *extra: str):
    proc = run_cli(installed, canonical, "--json", *extra)
    return proc, json.loads(proc.stdout)


# 1 — identical files MATCH exit 0
def test_identical_match(tmp_path):
    a = write(tmp_path, "a.py", TEXT)
    b = write(tmp_path, "b.py", TEXT)
    proc = run_cli(a, b)
    assert proc.returncode == 0
    assert "MATCH" in proc.stdout
    assert hashlib.sha256(TEXT.encode()).hexdigest() in proc.stdout
    assert str(len(TEXT.encode())) in proc.stdout


# 2 — differing content DRIFT exit 1 with differing line reported
def test_differing_content_drift_line(tmp_path):
    a = write(tmp_path, "a.py", TEXT)
    b = write(tmp_path, "b.py", "line one\nCHANGED\nline three\n")
    proc = run_cli(a, b)
    assert proc.returncode == 1
    assert "DRIFT" in proc.stdout
    assert "first differing line: 2" in proc.stdout


# 3 — extra trailing line: first differing line is the first extra line
def test_extra_line_drift_line(tmp_path):
    a = write(tmp_path, "a.py", TEXT)
    b = write(tmp_path, "b.py", TEXT + "line four\n")
    proc, payload = run_json(a, b)
    assert proc.returncode == 1
    assert payload["verdict"] == "DRIFT"
    assert payload["first_differing_line"] == 4


# 4 — size-only difference (trailing newline) is DRIFT
def test_size_only_difference_drift(tmp_path):
    a = write(tmp_path, "a.py", "hello\nworld\n")
    b = write(tmp_path, "b.py", "hello\nworld")
    proc, payload = run_json(a, b)
    assert proc.returncode == 1
    assert payload["verdict"] == "DRIFT"
    assert payload["installed"]["size"] != payload["canonical"]["size"]
    assert payload["installed"]["sha256"] != payload["canonical"]["sha256"]


# 5 — missing installed is INCOMPLETE exit 2
def test_missing_installed_incomplete(tmp_path):
    b = write(tmp_path, "b.py", TEXT)
    proc = run_cli(tmp_path / "nope.py", b)
    assert proc.returncode == 2
    assert "INCOMPLETE" in proc.stdout


# 6 — missing canonical is INCOMPLETE exit 2
def test_missing_canonical_incomplete(tmp_path):
    a = write(tmp_path, "a.py", TEXT)
    proc = run_cli(a, tmp_path / "nope.py")
    assert proc.returncode == 2
    assert "INCOMPLETE" in proc.stdout


# 7 — empty file is INCOMPLETE exit 2 (never MATCH, even both empty)
def test_empty_file_incomplete(tmp_path):
    a = write(tmp_path, "a.py", "")
    b = write(tmp_path, "b.py", "")
    proc = run_cli(a, b)
    assert proc.returncode == 2
    assert "INCOMPLETE" in proc.stdout
    assert "MATCH" not in proc.stdout.splitlines()[0]


# 8 — --json shape carries every documented key
def test_json_shape(tmp_path):
    a = write(tmp_path, "a.py", TEXT)
    b = write(tmp_path, "b.py", TEXT)
    proc, payload = run_json(a, b)
    assert proc.returncode == 0
    for key in ("verdict", "installed", "canonical",
                "first_differing_line", "errors"):
        assert key in payload
    for side in ("installed", "canonical"):
        for key in ("path", "size", "sha256"):
            assert key in payload[side]
    assert payload["installed"]["sha256"] == hashlib.sha256(
        TEXT.encode()).hexdigest()
    assert payload["first_differing_line"] is None
    assert payload["errors"] == []


# 9 — --json INCOMPLETE shape: missing side is null, errors named
def test_json_incomplete_shape(tmp_path):
    b = write(tmp_path, "b.py", TEXT)
    proc, payload = run_json(tmp_path / "nope.py", b)
    assert proc.returncode == 2
    assert payload["verdict"] == "INCOMPLETE"
    assert payload["installed"] is None
    assert payload["canonical"]["size"] == len(TEXT.encode())
    assert payload["errors"]


# 10 — read-only guarantee: input bytes and mtimes unchanged
def test_read_only_guarantee(tmp_path):
    a = write(tmp_path, "a.py", TEXT)
    b = write(tmp_path, "b.py", "line one\nCHANGED\nline three\n")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (a, b)}
    proc = run_cli(a, b)
    assert proc.returncode == 1
    for p, (data, mtime) in before.items():
        assert p.read_bytes() == data
        assert p.stat().st_mtime_ns == mtime


# 11 — binary drift: DRIFT with no differing line claimed
def test_binary_drift_no_line(tmp_path):
    a = write(tmp_path, "a.bin", b"\x00\x01\x02\xff")
    b = write(tmp_path, "b.bin", b"\x00\x01\x03\xff")
    proc, payload = run_json(a, b)
    assert proc.returncode == 1
    assert payload["verdict"] == "DRIFT"
    assert payload["first_differing_line"] is None


# 12 — shipped examples run: same exits 0, drift exits 1 at line 2
def test_examples_run():
    same = run_cli(EXAMPLES / "installed.txt", EXAMPLES / "canonical-same.txt")
    assert same.returncode == 0
    drift = run_cli(EXAMPLES / "installed.txt", EXAMPLES / "canonical-drift.txt")
    assert drift.returncode == 1
    assert "first differing line: 2" in drift.stdout


# 13 — usage error exits 2 with NO verdict line
def test_usage_error_no_verdict_line():
    proc = subprocess.run(
        [sys.executable, str(SRC), "--installed"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2
    combined = proc.stdout + proc.stderr
    for verdict in ("MATCH", "DRIFT", "INCOMPLETE"):
        assert verdict not in combined
