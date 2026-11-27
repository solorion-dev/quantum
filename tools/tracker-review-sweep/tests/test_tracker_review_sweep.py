"""Tests for tracker-review-sweep (stdlib unittest only).

Every test drives the real CLI in a subprocess so exit codes, human
output, and JSON output are exercised exactly as a run would use them.
Fixtures are written to a temp dir; the tool is read-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "tracker_review_sweep.py"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

NOW = "2026-11-27T12:00:00+00:00"
OLD = "2026-10-01T12:00:00+00:00"      # 57 days before NOW
YOUNG = "2026-11-25T12:00:00+00:00"    # 2 days before NOW
EDGE = "2026-11-13T12:00:00+00:00"     # exactly 14 days before NOW


def rec(rid, status="in_review", updated=OLD, created=None, title=None, **kw):
    r = {
        "id": rid,
        "status": status,
        "title": title if title is not None else f"Title for {rid}",
        "updated_at": updated,
        "created_at": created if created is not None else updated,
    }
    r.update(kw)
    return r


class SweepCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        p = self.dir / name
        p.write_text(content, encoding="utf-8")
        return p

    def snap(self, records, name="snap.json", wrap=None):
        data = {wrap: records} if wrap else records
        return self.write(name, json.dumps(data))

    def run_cli(self, snapshot, *extra):
        return subprocess.run(
            [sys.executable, str(SRC), str(snapshot), "--now", NOW, *extra],
            capture_output=True, text=True, timeout=60,
        )

    def run_json(self, snapshot, *extra):
        proc = self.run_cli(snapshot, "--json", *extra)
        return proc, json.loads(proc.stdout)


class TestVerdicts(SweepCase):
    # 1 — old unlinked in-review record is STALE, exit 1, named with age+title
    def test_stale_flagged(self):
        s = self.snap([rec("TRK-0001")])
        proc = self.run_cli(s)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("STALE", proc.stdout)
        self.assertIn("TRK-0001", proc.stdout)
        self.assertIn("57", proc.stdout)
        self.assertIn("Title for TRK-0001", proc.stdout)

    # 2 — young in-review record is CLEAN
    def test_young_is_clean(self):
        s = self.snap([rec("TRK-0002", updated=YOUNG)])
        proc = self.run_cli(s)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("CLEAN", proc.stdout)

    # 3 — exactly at threshold is NOT stale (strictly greater)
    def test_exactly_at_threshold_is_clean(self):
        s = self.snap([rec("TRK-0003", updated=EDGE)])
        proc = self.run_cli(s)
        self.assertEqual(proc.returncode, 0)

    # 4 — old in-review WITH a github_pr link is not flagged
    def test_linked_via_github_pr_is_clean(self):
        s = self.snap([rec("TRK-0004", github_pr="https://example/pr/1")])
        self.assertEqual(self.run_cli(s).returncode, 0)

    # 5 — old in-review WITH a links list is not flagged
    def test_linked_via_links_list_is_clean(self):
        s = self.snap([rec("TRK-0005", links=[{"kind": "pr", "url": "x"}])])
        self.assertEqual(self.run_cli(s).returncode, 0)

    # 6 — old in-review WITH external_ref (real bridge list shape) is clean
    def test_linked_via_external_ref_is_clean(self):
        s = self.snap([rec("TRK-0006", external_ref="PR #12")])
        self.assertEqual(self.run_cli(s).returncode, 0)

    # 7 — empty-string link fields do NOT count as linked
    def test_empty_link_fields_still_stale(self):
        s = self.snap([rec("TRK-0007", github_pr="", external_ref="", links=[])])
        self.assertEqual(self.run_cli(s).returncode, 1)

    # 8 — non-review statuses are never stale, however old
    def test_non_review_status_ignored(self):
        s = self.snap([rec("TRK-0008", status="open"),
                       rec("TRK-0009", status="done")])
        self.assertEqual(self.run_cli(s).returncode, 0)

    # 9 — status spellings: review / in-review / IN_REVIEW all count
    def test_status_spellings(self):
        for status in ("review", "in-review", "IN_REVIEW", "In Review"):
            s = self.snap([rec("TRK-0010", status=status)])
            self.assertEqual(self.run_cli(s).returncode, 1, status)

    # 10 — created_at fallback when updated_at missing/unparseable
    def test_created_at_fallback(self):
        r = rec("TRK-0011", updated="not-a-date", created=OLD)
        s = self.snap([r])
        self.assertEqual(self.run_cli(s).returncode, 1)

    # 11 — --days override: 57-day-old record is clean at --days 60
    def test_threshold_override(self):
        s = self.snap([rec("TRK-0012")])
        self.assertEqual(self.run_cli(s, "--days", "60").returncode, 0)
        self.assertEqual(self.run_cli(s, "--days", "30").returncode, 1)


class TestIncomplete(SweepCase):
    # 12 — in-review with no parseable timestamp: INCOMPLETE, exit 2, not stale
    def test_no_timestamp_is_incomplete(self):
        r = rec("TRK-0020", updated="", created="garbage")
        s = self.snap([r])
        proc, payload = self.run_json(s)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(payload["verdict"], "INCOMPLETE")
        self.assertEqual(payload["counts"]["stale"], 0)
        self.assertEqual(payload["counts"]["incomplete"], 1)
        self.assertIn("TRK-0020", proc.stdout)

    # 13 — missing file: INCOMPLETE exit 2
    def test_missing_file(self):
        proc = self.run_cli(self.dir / "nope.json")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("INCOMPLETE", proc.stdout)

    # 14 — malformed JSON: INCOMPLETE exit 2
    def test_malformed_json(self):
        s = self.write("bad.json", "{not json")
        proc = self.run_cli(s)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("INCOMPLETE", proc.stdout)

    # 15 — empty list snapshot: INCOMPLETE (a checker that reads nothing
    # must never say CLEAN)
    def test_empty_list_is_incomplete(self):
        s = self.snap([])
        proc = self.run_cli(s)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("INCOMPLETE", proc.stdout)

    # 16 — empty object / wrong shape: INCOMPLETE
    def test_wrong_shape_is_incomplete(self):
        s = self.write("obj.json", json.dumps({"hello": "world"}))
        self.assertEqual(self.run_cli(s).returncode, 2)

    # 17 — duplicate ids: INCOMPLETE, duplicates named
    def test_duplicate_ids_incomplete(self):
        s = self.snap([rec("TRK-0030", updated=YOUNG),
                       rec("TRK-0030", updated=YOUNG)])
        proc, payload = self.run_json(s)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(payload["verdict"], "INCOMPLETE")
        self.assertIn("TRK-0030", proc.stdout)

    # 18 — non-dict record entry: INCOMPLETE
    def test_non_dict_entry_incomplete(self):
        s = self.write("weird.json", json.dumps(["TRK-0031"]))
        self.assertEqual(self.run_cli(s).returncode, 2)

    # 19 — usage error (missing snapshot arg): exit 2, NO verdict line
    def test_usage_error_no_verdict(self):
        proc = subprocess.run([sys.executable, str(SRC)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("CLEAN", combined)
        self.assertNotIn("STALE:", combined)
        self.assertNotIn("INCOMPLETE", combined.split("usage")[-1]
                         if "usage" in combined else combined)

    # 20 — bad --now is a usage error: exit 2, no verdict line
    def test_bad_now_is_usage_error(self):
        s = self.snap([rec("TRK-0032", updated=YOUNG)])
        proc = subprocess.run(
            [sys.executable, str(SRC), str(s), "--now", "banana"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("CLEAN", proc.stdout)


class TestShapesAndDeterminism(SweepCase):
    # 21 — wrapped shapes: items / records / results all parse
    def test_wrapped_shapes(self):
        for wrap in ("items", "records", "results"):
            s = self.snap([rec("TRK-0040")], name=f"{wrap}.json", wrap=wrap)
            self.assertEqual(self.run_cli(s).returncode, 1, wrap)

    # 22 — bridge-shaped snapshot ({"ok": true, "items": [...]}) parses
    def test_bridge_shape(self):
        s = self.write("bridge.json", json.dumps(
            {"ok": True, "items": [rec("TRK-0041", updated=YOUNG)]}))
        self.assertEqual(self.run_cli(s).returncode, 0)

    # 23 — --now determinism: same inputs + same --now => identical output
    def test_now_determinism(self):
        s = self.snap([rec("TRK-0042"), rec("TRK-0043", updated=YOUNG)])
        a = self.run_cli(s, "--json")
        b = self.run_cli(s, "--json")
        self.assertEqual(a.stdout, b.stdout)
        self.assertEqual(a.returncode, 1)

    # 24 — --json shape on STALE: verdict, counts, stale entries with fields
    def test_json_shape(self):
        s = self.snap([rec("TRK-0044")])
        proc, payload = self.run_json(s)
        self.assertEqual(payload["verdict"], "STALE")
        self.assertEqual(payload["counts"]["records"], 1)
        self.assertEqual(payload["counts"]["in_review"], 1)
        self.assertEqual(payload["counts"]["stale"], 1)
        entry = payload["stale"][0]
        self.assertEqual(entry["id"], "TRK-0044")
        self.assertEqual(entry["age_days"], 57.0)
        self.assertIn("title", entry)

    # 25 — input file is never modified (bytes + mtime unchanged)
    def test_input_not_modified(self):
        s = self.snap([rec("TRK-0045")])
        before_bytes = s.read_bytes()
        before_hash = hashlib.sha256(before_bytes).hexdigest()
        before_mtime = os.stat(s).st_mtime_ns
        self.run_cli(s)
        self.assertEqual(hashlib.sha256(s.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(os.stat(s).st_mtime_ns, before_mtime)

    # 26 — shipped examples: clean example is CLEAN, stale example is STALE
    def test_shipped_examples(self):
        clean = EXAMPLES / "clean.json"
        stale = EXAMPLES / "stale.json"
        self.assertTrue(clean.exists())
        self.assertTrue(stale.exists())
        self.assertEqual(self.run_cli(clean).returncode, 0)
        proc = self.run_cli(stale)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("TRK-0901", proc.stdout)


if __name__ == "__main__":
    unittest.main()
