import base64
import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "blob_guard.py"
PY_SOURCE = b"#!/usr/bin/env python3\n" + b"# hello world, this is a real source file with lines\n" * 6 + b"print('done')\n"


def run(*args):
    return subprocess.run([sys.executable, str(SRC), *map(str, args)],
                          capture_output=True, text=True)


def wrapped(data: bytes, width=None) -> bytes:
    enc = base64.b64encode(data)
    if width:
        enc = b"\n".join(enc[i:i + width] for i in range(0, len(enc), width)) + b"\n"
    return enc


def test_clean_python_file(tmp_path):
    f = tmp_path / "ok.py"; f.write_bytes(PY_SOURCE)
    r = run(f); assert r.returncode == 0 and "CLEAN" in r.stdout


def test_wrapped_single_line_detected(tmp_path):
    f = tmp_path / "bad.py"; f.write_bytes(wrapped(PY_SOURCE))
    r = run(f); assert r.returncode == 1 and "WRAPPED" in r.stdout


def test_wrapped_76_col_detected(tmp_path):
    f = tmp_path / "bad.py"; f.write_bytes(wrapped(PY_SOURCE, 76))
    r = run(f); assert r.returncode == 1


def test_wrapped_markdown_detected(tmp_path):
    f = tmp_path / "bad.md"; f.write_bytes(wrapped(b"# Title\n\nSome prose text here.\n" * 8))
    r = run(f); assert r.returncode == 1


def test_wrapped_json_output(tmp_path):
    f = tmp_path / "bad.py"; f.write_bytes(wrapped(PY_SOURCE))
    r = run(f, "--json"); data = json.loads(r.stdout)
    assert r.returncode == 1 and data["verdict"] == "WRAPPED"
    assert data["wrapped"][0]["decoded_size"] == len(PY_SOURCE)
    assert "hello world" in data["wrapped"][0]["decoded_first_line"] or data["wrapped"][0]["decoded_first_line"]


def test_directory_scan_finds_nested(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "bad.js").write_bytes(wrapped(b"const x = 1;\n// comment line here\n" * 8))
    (tmp_path / "good.py").write_bytes(PY_SOURCE)
    r = run(tmp_path); assert r.returncode == 1 and "bad.js" in r.stdout


def test_b64_extension_not_scanned(tmp_path):
    f = tmp_path / "payload.b64"; f.write_bytes(wrapped(PY_SOURCE))
    r = run(tmp_path); assert r.returncode == 2  # zero scanned -> INCOMPLETE


def test_small_file_not_flagged(tmp_path):
    f = tmp_path / "tiny.py"; f.write_bytes(wrapped(b"print(1)\n"))
    r = run(f); assert r.returncode == 0


def test_base64_of_binary_not_flagged(tmp_path):
    f = tmp_path / "bin.py"; f.write_bytes(wrapped(bytes(range(256)) * 2))
    r = run(f); assert r.returncode == 0


def test_embedded_base64_not_flagged(tmp_path):
    content = b'{"img": "' + base64.b64encode(PY_SOURCE) + b'"}\n'
    f = tmp_path / "data.json"; f.write_bytes(content)
    r = run(f); assert r.returncode == 0


def test_plain_text_not_flagged(tmp_path):
    f = tmp_path / "notes.md"; f.write_bytes(b"Normal markdown prose with spaces and punctuation!\n" * 10)
    r = run(f); assert r.returncode == 0


def test_hex_file_not_flagged(tmp_path):
    f = tmp_path / "h.txt"; f.write_bytes(b"deadbeef" * 40 + b"\n")
    r = run(f); assert r.returncode == 0


def test_missing_path_incomplete(tmp_path):
    r = run(tmp_path / "nope"); assert r.returncode == 2 and "INCOMPLETE" in r.stdout


def test_empty_dir_incomplete(tmp_path):
    r = run(tmp_path); assert r.returncode == 2


def test_allow_list_suppresses(tmp_path):
    f = tmp_path / "bad.py"; f.write_bytes(wrapped(PY_SOURCE))
    allow = tmp_path / "allow.txt"; allow.write_text("bad.py  # known fixture\n")
    r = run(tmp_path, "--allow", allow)
    # bad.py allowed; allow.txt itself is a .txt scanned and clean
    assert r.returncode == 0 and "CLEAN" in r.stdout


def test_git_dir_skipped(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "bad.py").write_bytes(wrapped(PY_SOURCE))
    (tmp_path / "ok.py").write_bytes(PY_SOURCE)
    r = run(tmp_path); assert r.returncode == 0


def test_readonly_inputs_unchanged(tmp_path):
    f = tmp_path / "bad.py"; data = wrapped(PY_SOURCE); f.write_bytes(data)
    run(f); assert f.read_bytes() == data


def test_usage_error_no_verdict():
    r = run(); assert r.returncode == 2 and "VERDICT" not in r.stdout


def test_wrapped_sh_detected(tmp_path):
    f = tmp_path / "run.sh"; f.write_bytes(wrapped(b"#!/bin/sh\necho hello world this is a script\n" * 6))
    r = run(f); assert r.returncode == 1
