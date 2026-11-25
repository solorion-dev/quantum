"""Tests for nebula_vram_guard.py — drives the real CLI in subprocesses."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src", "nebula_vram_guard.py")
EXAMPLES = os.path.join(HERE, "..", "examples")


def run_cli(job_obj=None, job_path=None, extra_args=(), raw=None):
    with tempfile.TemporaryDirectory() as td:
        if job_path is None:
            job_path = os.path.join(td, "job.json")
            with open(job_path, "w", encoding="utf-8") as fh:
                fh.write(raw if raw is not None else json.dumps(job_obj))
        return subprocess.run(
            [sys.executable, SRC, "--job", job_path, *extra_args],
            capture_output=True, text=True)


def allow_job():
    return {"models": [{"name": "sd15.safetensors", "size_mib": 2135}],
            "width": 512, "height": 512, "batch": 1}


class TestVerdicts(unittest.TestCase):
    def test_allow(self):
        r = run_cli(allow_job())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("verdict: ALLOW", r.stdout)

    def test_refuse_oversized(self):
        job = {"models": [{"name": "big.safetensors", "size_mib": 14000}],
               "width": 1024, "height": 1024, "batch": 1, "extra_mib": 120}
        r = run_cli(job)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("verdict: REFUSE", r.stdout)

    def test_refuse_nov22_shape(self):
        # ~15,400 MiB required vs the 8,192 MiB card (2026-11-22 stall).
        job = {"models": [{"name": "wan-huge.safetensors", "size_mib": 14120}],
               "width": 512, "height": 512, "batch": 1}
        r = run_cli(job, extra_args=("--json",))
        self.assertEqual(r.returncode, 1)
        rep = json.loads(r.stdout)
        self.assertAlmostEqual(rep["required_mib"], 15400, delta=1)
        self.assertEqual(rep["budget_mib"], 8192)

    def test_free_mib_override_refuses(self):
        r = run_cli(allow_job(), extra_args=("--free-mib", "2000"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdict: REFUSE", r.stdout)

    def test_free_mib_override_allows(self):
        job = {"models": [{"name": "m.safetensors", "size_mib": 9000}],
               "width": 512, "height": 512}
        self.assertEqual(run_cli(job).returncode, 1)
        r = run_cli(job, extra_args=("--free-mib", "12000"))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_reserve_override(self):
        r = run_cli(allow_job(), extra_args=("--reserve-mib", "9000"))
        self.assertEqual(r.returncode, 1)


class TestIncomplete(unittest.TestCase):
    def test_missing_file(self):
        r = run_cli(job_path="/nonexistent/job.json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("verdict: INCOMPLETE", r.stdout)

    def test_unparseable(self):
        r = run_cli(raw="{not json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("verdict: INCOMPLETE", r.stdout)

    def test_zero_models(self):
        r = run_cli({"models": [], "width": 512, "height": 512})
        self.assertEqual(r.returncode, 2)

    def test_unknown_model_no_size(self):
        r = run_cli({"models": [{"name": "mystery-ckpt.bin"}],
                     "width": 512, "height": 512})
        self.assertEqual(r.returncode, 2)
        self.assertIn("INCOMPLETE", r.stdout)

    def test_nonpositive_dimensions(self):
        for bad in ({"width": 0, "height": 512}, {"width": 512, "height": -8}):
            job = {"models": [{"name": "m", "size_mib": 100}], **bad}
            self.assertEqual(run_cli(job).returncode, 2, bad)

    def test_usage_error_no_verdict_line(self):
        r = subprocess.run([sys.executable, SRC], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("verdict:", r.stdout + r.stderr)


class TestKnownTable(unittest.TestCase):
    def test_known_hit_sdxl(self):
        job = {"models": [{"name": "sd_xl_base_1.0.safetensors"}],
               "width": 512, "height": 512}
        # SDXL fp16 (6,938) + floor activation + default reserve busts
        # 8,192; with a 512 MiB reserve it fits — either way the table hit
        # must resolve the size.
        r = run_cli(job, extra_args=("--json", "--reserve-mib", "512"))
        self.assertEqual(r.returncode, 0, r.stdout)
        rep = json.loads(r.stdout)
        self.assertEqual(rep["models"][0]["size_mib"], 6938)
        self.assertIn("known-table", rep["models"][0]["size_source"])

    def test_known_hit_flux_fp8(self):
        job = {"models": [{"name": "flux1-dev-fp8.safetensors"}],
               "width": 512, "height": 512}
        r = run_cli(job, extra_args=("--json",))
        rep = json.loads(r.stdout)
        self.assertEqual(rep["models"][0]["size_mib"], 11903)
        self.assertEqual(r.returncode, 1)  # fp8 flux alone busts 8 GB

    def test_explicit_size_beats_table(self):
        job = {"models": [{"name": "sdxl-custom.safetensors", "size_mib": 100}],
               "width": 512, "height": 512}
        r = run_cli(job, extra_args=("--json",))
        rep = json.loads(r.stdout)
        self.assertEqual(rep["models"][0]["size_mib"], 100)
        self.assertEqual(rep["models"][0]["size_source"], "explicit")


class TestEstimate(unittest.TestCase):
    def test_batch_scaling(self):
        # Above the 256 MiB floor, activation scales linearly with batch.
        base = {"models": [{"name": "m", "size_mib": 1000}],
                "width": 8192, "height": 8192, "batch": 4}
        a4 = json.loads(run_cli(base, extra_args=("--json",)).stdout)
        a16 = json.loads(run_cli(dict(base, batch=16),
                                 extra_args=("--json",)).stdout)
        self.assertEqual(a4["activation_mib"], 512)
        self.assertAlmostEqual(a16["activation_mib"], a4["activation_mib"] * 4)

    def test_activation_floor(self):
        rep = json.loads(run_cli(allow_job(), extra_args=("--json",)).stdout)
        self.assertEqual(rep["activation_mib"], 256)

    def test_json_shape(self):
        rep = json.loads(run_cli(allow_job(), extra_args=("--json",)).stdout)
        for key in ("verdict", "models", "models_mib", "activation_mib",
                    "estimate_mib", "reserve_mib", "budget_mib",
                    "required_mib", "errors"):
            self.assertIn(key, rep)
        self.assertEqual(rep["verdict"], "ALLOW")
        self.assertEqual(rep["errors"], [])


class TestGuarantees(unittest.TestCase):
    def test_input_unmodified(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "job.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(allow_job(), fh)
            before = (open(p, "rb").read(), os.stat(p).st_mtime_ns)
            run_cli(job_path=p)
            after = (open(p, "rb").read(), os.stat(p).st_mtime_ns)
            self.assertEqual(before, after)

    def test_shipped_examples(self):
        allow = os.path.join(EXAMPLES, "job-allow.json")
        refuse = os.path.join(EXAMPLES, "job-refuse.json")
        self.assertEqual(run_cli(job_path=allow).returncode, 0)
        self.assertEqual(run_cli(job_path=refuse).returncode, 1)
        rep = json.loads(run_cli(job_path=refuse, extra_args=("--json",)).stdout)
        self.assertAlmostEqual(rep["required_mib"], 15400, delta=1)


if __name__ == "__main__":
    unittest.main()
