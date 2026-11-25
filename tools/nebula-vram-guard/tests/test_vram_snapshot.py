#!/usr/bin/env python3
"""Tests for vram_snapshot.py (stdlib unittest; also pytest-runnable).

No test needs a real GPU: the command runner is injected everywhere,
and --from-file covers the saved-output path.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import vram_snapshot as vs  # noqa: E402

SNAP = SRC / "vram_snapshot.py"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

NVIDIA_ONE = "0, NVIDIA GeForce RTX 3070, 5200, 8192\n"
NVIDIA_TWO = ("0, NVIDIA GeForce RTX 3070, 5200, 8192\n"
              "1, NVIDIA GeForce RTX 3060, 11264, 12288\n")
ROCM_ONE = (
    "GPU[0] : VRAM Total Memory (B): 8589934592\n"
    "GPU[0] : VRAM Total Used Memory (B): 3145728000\n"
)  # total 8192 MiB, used 3000 MiB -> free 5192 MiB


def runner_returning(mapping):
    """Fake runner: mapping of argv[0] -> (rc, stdout, stderr) or exception."""
    def run(argv):
        outcome = mapping[argv[0]]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return run


def run_cli(*argv):
    return subprocess.run([sys.executable, str(SNAP), *argv],
                          capture_output=True, text=True)


class NvidiaParseTests(unittest.TestCase):
    def test_single_gpu(self):
        snap = vs.collect_snapshot(runner=runner_returning(
            {"nvidia-smi": (0, NVIDIA_ONE, "")}), now_iso="2026-11-25T00:00:00+00:00")
        self.assertEqual(snap["source"], "nvidia-smi")
        self.assertEqual(snap["gpu_index"], 0)
        self.assertEqual(snap["name"], "NVIDIA GeForce RTX 3070")
        self.assertEqual(snap["free_mib"], 5200)
        self.assertEqual(snap["total_mib"], 8192)
        self.assertEqual(snap["observed_at"], "2026-11-25T00:00:00+00:00")

    def test_multi_gpu_default_first_and_selection(self):
        r = runner_returning({"nvidia-smi": (0, NVIDIA_TWO, "")})
        self.assertEqual(vs.collect_snapshot(runner=r)["gpu_index"], 0)
        snap = vs.collect_snapshot(gpu_index=1, runner=r)
        self.assertEqual(snap["name"], "NVIDIA GeForce RTX 3060")
        self.assertEqual(snap["free_mib"], 11264)
        self.assertEqual(snap["total_mib"], 12288)

    def test_unknown_index_incomplete(self):
        r = runner_returning({"nvidia-smi": (0, NVIDIA_ONE, ""),
                              "rocm-smi": (1, "", "no")})
        with self.assertRaises(vs.SnapshotIncomplete):
            vs.collect_snapshot(gpu_index=7, runner=r)


class RocmParseTests(unittest.TestCase):
    def test_rocm_parse_free_is_total_minus_used(self):
        gpus = vs.parse_rocm(ROCM_ONE)
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0]["total_mib"], 8192)
        self.assertEqual(gpus[0]["free_mib"], 5192)

    def test_fallback_when_nvidia_missing(self):
        r = runner_returning({"nvidia-smi": FileNotFoundError("nope"),
                              "rocm-smi": (0, ROCM_ONE, "")})
        snap = vs.collect_snapshot(runner=r)
        self.assertEqual(snap["source"], "rocm-smi")
        self.assertEqual(snap["free_mib"], 5192)

    def test_fallback_when_nvidia_fails(self):
        r = runner_returning({"nvidia-smi": (9, "", "driver error"),
                              "rocm-smi": (0, ROCM_ONE, "")})
        self.assertEqual(vs.collect_snapshot(runner=r)["source"], "rocm-smi")


class FromFileTests(unittest.TestCase):
    def test_from_file_nvidia(self):
        snap = vs.collect_snapshot(from_file=str(EXAMPLES / "nvidia-smi-sample.txt"),
                                   gpu_index=1)
        self.assertEqual(snap["source"], "file")
        self.assertEqual(snap["free_mib"], 11264)

    def test_from_file_rocm_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rocm.txt"
            p.write_text(ROCM_ONE, encoding="utf-8")
            snap = vs.collect_snapshot(from_file=str(p))
            self.assertEqual(snap["source"], "file")
            self.assertEqual(snap["free_mib"], 5192)

    def test_missing_file_incomplete(self):
        with self.assertRaises(vs.SnapshotIncomplete):
            vs.collect_snapshot(from_file="/nonexistent/snap.txt")

    def test_from_file_input_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "snap.txt"
            p.write_text(NVIDIA_TWO, encoding="utf-8")
            before, mtime = p.read_bytes(), os.stat(p).st_mtime_ns
            r = run_cli("--from-file", str(p), "--gpu", "1")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("11,264", r.stdout)
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(os.stat(p).st_mtime_ns, mtime)


class FailureTests(unittest.TestCase):
    def test_both_tools_missing_incomplete(self):
        r = runner_returning({"nvidia-smi": FileNotFoundError(),
                              "rocm-smi": FileNotFoundError()})
        with self.assertRaises(vs.SnapshotIncomplete):
            vs.collect_snapshot(runner=r)

    def test_unparseable_output_incomplete(self):
        r = runner_returning({"nvidia-smi": (0, "garbage,output\n", ""),
                              "rocm-smi": (0, "nothing useful\n", "")})
        with self.assertRaises(vs.SnapshotIncomplete):
            vs.collect_snapshot(runner=r)

    def test_zero_gpus_incomplete(self):
        r = runner_returning({"nvidia-smi": (0, "", ""),
                              "rocm-smi": (0, "", "")})
        with self.assertRaises(vs.SnapshotIncomplete):
            vs.collect_snapshot(runner=r)

    def test_cli_failure_exit2_with_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.txt"
            p.write_text("not a snapshot\n", encoding="utf-8")
            r = run_cli("--from-file", str(p))
            self.assertEqual(r.returncode, 2)
            self.assertIn("INCOMPLETE", r.stdout)
            rj = run_cli("--from-file", str(p), "--json")
            self.assertEqual(rj.returncode, 2)
            self.assertEqual(json.loads(rj.stdout)["verdict"], "INCOMPLETE")
            self.assertIsNone(json.loads(rj.stdout)["free_mib"])

    def test_cli_missing_file_exit2(self):
        r = run_cli("--from-file", "/nonexistent/snap.txt")
        self.assertEqual(r.returncode, 2)
        self.assertIn("INCOMPLETE", r.stdout)

    def test_usage_error_exit2_no_verdict(self):
        r = run_cli("--check")  # --check without --job is a usage error
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("verdict: INCOMPLETE", r.stdout)


class CliAndCheckTests(unittest.TestCase):
    def test_cli_json_snapshot_shape(self):
        r = run_cli("--from-file", str(EXAMPLES / "nvidia-smi-sample.txt"), "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        snap = json.loads(r.stdout)
        self.assertEqual(set(snap), {"source", "gpu_index", "name",
                                     "free_mib", "total_mib", "observed_at"})
        self.assertEqual(snap["free_mib"], 5200)

    def test_check_allow_passthrough(self):
        # Sample GPU 0 free = 5200 MiB; job-allow requires 3,415 -> ALLOW.
        r = run_cli("--from-file", str(EXAMPLES / "nvidia-smi-sample.txt"),
                    "--check", "--job", str(EXAMPLES / "job-allow.json"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ALLOW", r.stdout)

    def test_check_refuse_passthrough(self):
        # job-refuse requires 15,400 MiB > 5,200 free -> REFUSE.
        r = run_cli("--from-file", str(EXAMPLES / "nvidia-smi-sample.txt"),
                    "--check", "--job", str(EXAMPLES / "job-refuse.json"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUSE", r.stdout)

    def test_check_json_includes_guard(self):
        r = run_cli("--from-file", str(EXAMPLES / "nvidia-smi-sample.txt"),
                    "--check", "--job", str(EXAMPLES / "job-allow.json"), "--json")
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertEqual(out["verdict"], "ALLOW")
        self.assertEqual(out["snapshot"]["free_mib"], 5200)
        self.assertEqual(out["guard"]["budget_mib"], 5200)

    def test_check_bad_job_exit2(self):
        r = run_cli("--from-file", str(EXAMPLES / "nvidia-smi-sample.txt"),
                    "--check", "--job", "/nonexistent/job.json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("INCOMPLETE", r.stdout)


if __name__ == "__main__":
    unittest.main()
