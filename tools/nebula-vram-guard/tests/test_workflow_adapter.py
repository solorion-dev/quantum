#!/usr/bin/env python3
"""Tests for workflow_adapter.py (stdlib unittest; also pytest-runnable)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import workflow_adapter as wa  # noqa: E402

ADAPTER = SRC / "workflow_adapter.py"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def run_cli(*argv):
    return subprocess.run([sys.executable, str(ADAPTER), *argv],
                          capture_output=True, text=True)


def write(tmp, name, obj_or_text):
    p = Path(tmp) / name
    if isinstance(obj_or_text, str):
        p.write_text(obj_or_text, encoding="utf-8")
    else:
        p.write_text(json.dumps(obj_or_text), encoding="utf-8")
    return p


API_SD15 = {
    "1": {"class_type": "CheckpointLoaderSimple",
          "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}},
    "2": {"class_type": "EmptyLatentImage",
          "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "3": {"class_type": "KSampler",
          "inputs": {"model": ["1", 0], "latent_image": ["2", 0]}},
}

UI_BASIC = {
    "nodes": [
        {"id": 1, "type": "CheckpointLoaderSimple",
         "widgets_values": ["v1-5-pruned-emaonly.safetensors"],
         "inputs": [{"name": "ckpt_name", "type": "COMBO",
                     "widget": {"name": "ckpt_name"}}]},
        {"id": 2, "type": "EmptyLatentImage", "widgets_values": [768, 512, 2],
         "inputs": [
             {"name": "width", "type": "INT", "widget": {"name": "width"}},
             {"name": "height", "type": "INT", "widget": {"name": "height"}},
             {"name": "batch_size", "type": "INT", "widget": {"name": "batch_size"}}]},
    ],
    "links": [],
}


class ApiFormatTests(unittest.TestCase):
    def test_checkpoint_and_latent_extraction(self):
        job, report = wa.adapt(API_SD15)
        self.assertFalse(report["incomplete"])
        self.assertEqual(report["workflow_format"], "api")
        self.assertEqual([m["name"] for m in job["models"]],
                         ["v1-5-pruned-emaonly.safetensors"])
        self.assertEqual((job["width"], job["height"], job["batch"]), (512, 512, 1))
        self.assertEqual(job["extra_mib"], 0)
        self.assertEqual(job["_adapter"]["model_sources"],
                         {"v1-5-pruned-emaonly.safetensors": "CheckpointLoaderSimple"})
        self.assertNotIn("size_mib", job["models"][0])  # adapter never invents a size

    def test_sampler_link_following(self):
        # Latent dims are links to primitives: not directly obvious, so
        # they are found only by following the sampler's latent_image.
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}},
            "2": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": ["5", 0], "height": ["6", 0], "batch_size": 1}},
            "3": {"class_type": "KSampler",
                  "inputs": {"model": ["1", 0], "latent_image": ["2", 0]}},
            "5": {"class_type": "PrimitiveNode", "inputs": {"value": 640}},
            "6": {"class_type": "PrimitiveNode", "inputs": {"value": 384}},
        }
        job, report = wa.adapt(wf)
        self.assertFalse(report["incomplete"], report)
        self.assertEqual((job["width"], job["height"]), (640, 384))

    def test_unet_dualclip_vae_lora_extraction(self):
        wf = {
            "1": {"class_type": "UNETLoader",
                  "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "default"}},
            "2": {"class_type": "DualCLIPLoader",
                  "inputs": {"clip_name1": "clip_l.safetensors",
                             "clip_name2": "t5xxl_fp16.safetensors", "type": "flux"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "4": {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"lora_name": "detail.safetensors", "strength_model": 0.7}},
            "5": {"class_type": "ControlNetLoader",
                  "inputs": {"control_net_name": "cn-depth.safetensors"}},
            "6": {"class_type": "EmptySD3LatentImage",
                  "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        }
        job, report = wa.adapt(wf)
        self.assertFalse(report["incomplete"], report)
        self.assertEqual([m["name"] for m in job["models"]],
                         ["flux1-dev.safetensors", "clip_l.safetensors",
                          "t5xxl_fp16.safetensors", "ae.safetensors",
                          "detail.safetensors", "cn-depth.safetensors"])
        self.assertEqual(job["_adapter"]["model_sources"]["flux1-dev.safetensors"],
                         "UNETLoader")

    def test_dedupe_identical_filenames(self):
        wf = dict(API_SD15)
        wf["9"] = {"class_type": "CheckpointLoaderSimple",
                   "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}}
        job, _ = wa.adapt(wf)
        self.assertEqual(len(job["models"]), 1)

    def test_multiple_latent_warning_uses_first(self):
        wf = dict(API_SD15)
        wf["8"] = {"class_type": "EmptyLatentImage",
                   "inputs": {"width": 256, "height": 256, "batch_size": 1}}
        job, report = wa.adapt(wf)
        self.assertEqual((job["width"], job["height"]), (512, 512))
        self.assertTrue(any("multiple distinct latent" in w
                            for w in report["warnings"]))
        self.assertTrue(any("256x256" in w for w in report["warnings"]))


class UiFormatTests(unittest.TestCase):
    def test_ui_extraction(self):
        job, report = wa.adapt(UI_BASIC)
        self.assertFalse(report["incomplete"], report)
        self.assertEqual(report["workflow_format"], "ui")
        self.assertEqual([m["name"] for m in job["models"]],
                         ["v1-5-pruned-emaonly.safetensors"])
        self.assertEqual((job["width"], job["height"], job["batch"]), (768, 512, 2))

    def test_ui_positional_fallback(self):
        # No widget metadata on inputs: documented positions are used.
        wf = {"nodes": [
            {"id": 1, "type": "UNETLoader",
             "widgets_values": ["wan2.1-t2v-14b.safetensors", "default"], "inputs": []},
            {"id": 2, "type": "EmptyLatentImage", "widgets_values": [1280, 720, 1],
             "inputs": []},
        ], "links": []}
        job, report = wa.adapt(wf)
        self.assertFalse(report["incomplete"], report)
        self.assertEqual(job["models"][0]["name"], "wan2.1-t2v-14b.safetensors")
        self.assertEqual((job["width"], job["height"]), (1280, 720))


class IncompleteTests(unittest.TestCase):
    def test_no_model_incomplete(self):
        wf = {"1": {"class_type": "EmptyLatentImage",
                    "inputs": {"width": 512, "height": 512, "batch_size": 1}}}
        job, report = wa.adapt(wf)
        self.assertTrue(report["incomplete"])
        self.assertIn("no model loader nodes found", report["errors"])

    def test_no_latent_incomplete(self):
        wf = {"1": {"class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}}}
        job, report = wa.adapt(wf)
        self.assertTrue(report["incomplete"])
        self.assertIn("no latent dimensions found", report["errors"])

    def test_unrecognised_format_incomplete(self):
        job, report = wa.adapt({"hello": "world"})
        self.assertIsNone(job)
        self.assertTrue(report["incomplete"])


class CliTests(unittest.TestCase):
    def test_unparseable_incomplete_exit2(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "bad.json", "{not json")
            r = run_cli("--workflow", str(p))
            self.assertEqual(r.returncode, 2)
            r2 = run_cli("--workflow", str(p), "--json")
            self.assertEqual(r2.returncode, 2)
            self.assertTrue(json.loads(r2.stdout)["incomplete"])

    def test_check_allow_exit0(self):
        r = run_cli("--workflow", str(EXAMPLES / "workflow-api-sd15.json"), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ALLOW", r.stdout)
        self.assertIn("3,415", r.stdout)

    def test_check_refuse_exit1(self):
        r = run_cli("--workflow", str(EXAMPLES / "workflow-api-wan-refuse.json"), "--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUSE", r.stdout)
        self.assertIn("29,280", r.stdout)

    def test_check_json_report(self):
        r = run_cli("--workflow", str(EXAMPLES / "workflow-api-sd15.json"),
                    "--check", "--json")
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertEqual(out["verdict"], "ALLOW")
        self.assertEqual(out["guard"]["required_mib"], 3415)
        self.assertEqual(out["guard"]["budget_mib"], 8192)
        self.assertFalse(out["incomplete"])

    def test_out_file_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "job.json"
            r = run_cli("--workflow", str(EXAMPLES / "workflow-api-sd15.json"),
                        "--out", str(out))
            self.assertEqual(r.returncode, 0)
            job = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(job["width"], 512)
            self.assertIn("_adapter", job)

    def test_input_file_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "wf.json", API_SD15)
            before_bytes = p.read_bytes()
            before_mtime = os.stat(p).st_mtime_ns
            r = run_cli("--workflow", str(p), "--check")
            self.assertEqual(r.returncode, 0)
            self.assertEqual(p.read_bytes(), before_bytes)
            self.assertEqual(os.stat(p).st_mtime_ns, before_mtime)


if __name__ == "__main__":
    unittest.main()
