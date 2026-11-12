"""Tests for settle-check v2 remote claims (Tracker status / GitHub PR).

The remote snapshot is an ordinary file artifact as far as the settle
window is concerned: these tests drive it through the same FakeSnap
two-pass seam the v1 tests use, so no test ever sleeps or touches the
network.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from settle_check import FileSnap, check, load_manifest  # noqa: E402

SNAP_PATH = "/remote-snapshot.json"
FULL_SHA = "0123456789abcdef0123456789abcdef01234567"

SNAPSHOT_DOC = {
    "tracker": {"TRK-0123": {"status": "done"}},
    "github_prs": {
        "solorion-dev/quantum#363": {
            "head_sha": FULL_SHA, "state": "closed", "merged": True,
        },
    },
}


class FakeSnap:
    """Same deterministic two-pass seam as the v1 tests."""

    def __init__(self, rounds, texts=None):
        self.rounds = list(rounds)
        self.texts = texts or {}
        self.calls = 0

    def snapshot(self, path):
        idx = min(self.calls, len(self.rounds) - 1)
        return self.rounds[idx].get(path, FileSnap(path=path, exists=False))

    def advance(self):
        self.calls += 1

    def read_text(self, path):
        return self.texts[path]


def snap_of(path, content: bytes, mtime=1000.0):
    return FileSnap(path=path, exists=True, size=len(content), mtime=mtime,
                    sha256=hashlib.sha256(content).hexdigest())


def fake_for(doc=SNAPSHOT_DOC, rounds=2):
    text = json.dumps(doc)
    body = text.encode()
    return FakeSnap([{SNAP_PATH: snap_of(SNAP_PATH, body)}] * rounds,
                    texts={SNAP_PATH: text})


def run(manifest, fake, now=2000.0):
    return check(manifest, fake, now=now, wait=lambda s: fake.advance())


def manifest_with(claims, **extra):
    m = {"remote_snapshot": SNAP_PATH, "remote_claims": claims}
    m.update(extra)
    return m


class TestTrackerClaims(unittest.TestCase):
    def test_tracker_match_verifies(self):
        m = manifest_with([{"type": "tracker_status", "id": "TRK-0123",
                            "expect_status": "done"}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "verified")
        self.assertEqual(r.exit_code, 0)

    def test_tracker_status_mismatch_fails(self):
        m = manifest_with([{"type": "tracker_status", "id": "TRK-0123",
                            "expect_status": "in_progress"}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.exit_code, 1)

    def test_missing_tracker_entry_is_no_verdict(self):
        m = manifest_with([{"type": "tracker_status", "id": "TRK-9999",
                            "expect_status": "done"}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "error")
        self.assertEqual(r.exit_code, 2)
        self.assertTrue(any("incomplete" in p for p in r.problems))


class TestGithubPrClaims(unittest.TestCase):
    def test_head_sha_prefix_match_verifies(self):
        # 10-char prefix of the snapshot's full head SHA.
        m = manifest_with([{"type": "github_pr", "repo": "solorion-dev/quantum",
                            "number": 363, "expect_head_sha": FULL_SHA[:10]}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "verified")
        self.assertEqual(r.exit_code, 0)

    def test_head_sha_minimum_seven_char_prefix_verifies(self):
        m = manifest_with([{"type": "github_pr", "repo": "solorion-dev/quantum",
                            "number": 363, "expect_head_sha": FULL_SHA[:7]}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "verified")

    def test_head_sha_mismatch_fails(self):
        m = manifest_with([{"type": "github_pr", "repo": "solorion-dev/quantum",
                            "number": 363, "expect_head_sha": "fffffff"}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.exit_code, 1)

    def test_state_and_merged_match_verifies(self):
        m = manifest_with([{"type": "github_pr", "repo": "solorion-dev/quantum",
                            "number": 363, "expect_state": "closed",
                            "expect_merged": True}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "verified")

    def test_merged_mismatch_fails(self):
        m = manifest_with([{"type": "github_pr", "repo": "solorion-dev/quantum",
                            "number": 363, "expect_merged": False}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.exit_code, 1)

    def test_missing_pr_entry_is_no_verdict(self):
        m = manifest_with([{"type": "github_pr", "repo": "solorion-dev/quantum",
                            "number": 999, "expect_merged": True}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "error")
        self.assertEqual(r.exit_code, 2)


class TestSnapshotSettleSemantics(unittest.TestCase):
    def test_snapshot_changing_during_window_is_unsettled(self):
        # The operator re-generates the snapshot mid-window: the remote
        # state is still flushing, so no claim may be judged at all.
        doc_a = json.dumps(SNAPSHOT_DOC).encode()
        changed = dict(SNAPSHOT_DOC, tracker={"TRK-0123": {"status": "open"}})
        text_b = json.dumps(changed)
        fake = FakeSnap(
            [{SNAP_PATH: snap_of(SNAP_PATH, doc_a)},
             {SNAP_PATH: snap_of(SNAP_PATH, text_b.encode())}],
            texts={SNAP_PATH: text_b})
        m = manifest_with([{"type": "tracker_status", "id": "TRK-0123",
                            "expect_status": "done"}], settle_seconds=5)
        r = run(m, fake)
        self.assertEqual(r.status, "unsettled")
        self.assertEqual(r.exit_code, 2)

    def test_missing_snapshot_file_is_no_verdict(self):
        fake = FakeSnap([{}] * 2)  # snapshot path never exists
        m = manifest_with([{"type": "tracker_status", "id": "TRK-0123",
                            "expect_status": "done"}])
        r = run(m, fake)
        self.assertEqual(r.status, "error")
        self.assertEqual(r.exit_code, 2)

    def test_unparseable_snapshot_is_no_verdict(self):
        body = b"this is not json"
        fake = FakeSnap([{SNAP_PATH: snap_of(SNAP_PATH, body)}] * 2,
                        texts={SNAP_PATH: "this is not json"})
        m = manifest_with([{"type": "tracker_status", "id": "TRK-0123",
                            "expect_status": "done"}])
        r = run(m, fake)
        self.assertEqual(r.status, "error")
        self.assertEqual(r.exit_code, 2)

    def test_incomplete_dominates_a_mismatch(self):
        # One claim mismatches AND another has no snapshot entry: the
        # run must record NO VERDICT, not FAILED — it never saw the
        # full claim.
        m = manifest_with([
            {"type": "tracker_status", "id": "TRK-0123",
             "expect_status": "in_progress"},
            {"type": "tracker_status", "id": "TRK-9999",
             "expect_status": "done"},
        ])
        r = run(m, fake_for())
        self.assertEqual(r.status, "error")
        self.assertEqual(r.exit_code, 2)

    def test_remote_claims_combine_with_file_claims(self):
        body = b"payload"
        doc_text = json.dumps(SNAPSHOT_DOC)
        fake = FakeSnap([{"/a.bin": snap_of("/a.bin", body),
                          SNAP_PATH: snap_of(SNAP_PATH, doc_text.encode())}] * 2,
                        texts={"/a.bin": "payload", SNAP_PATH: doc_text})
        m = manifest_with(
            [{"type": "tracker_status", "id": "TRK-0123",
              "expect_status": "done"}],
            files=[{"path": "/a.bin", "min_size": 3}])
        r = run(m, fake)
        self.assertEqual(r.status, "verified")


class TestMalformedRemoteClaims(unittest.TestCase):
    def test_github_pr_without_expect_is_no_verdict_in_check(self):
        m = manifest_with([{"type": "github_pr",
                            "repo": "solorion-dev/quantum", "number": 363}])
        r = run(m, fake_for())
        self.assertEqual(r.status, "error")
        self.assertEqual(r.exit_code, 2)

    def test_github_pr_without_expect_rejected_by_load_manifest(self):
        text = json.dumps({
            "remote_snapshot": "snap.json",
            "remote_claims": [{"type": "github_pr",
                               "repo": "solorion-dev/quantum", "number": 363}],
        })
        with self.assertRaises(ValueError):
            load_manifest(text)

    def test_tracker_without_expect_status_rejected(self):
        text = json.dumps({
            "remote_snapshot": "snap.json",
            "remote_claims": [{"type": "tracker_status", "id": "TRK-0123"}],
        })
        with self.assertRaises(ValueError):
            load_manifest(text)

    def test_unknown_claim_type_rejected(self):
        text = json.dumps({
            "remote_snapshot": "snap.json",
            "remote_claims": [{"type": "carrier_pigeon", "id": "X"}],
        })
        with self.assertRaises(ValueError):
            load_manifest(text)

    def test_short_head_sha_prefix_rejected(self):
        text = json.dumps({
            "remote_snapshot": "snap.json",
            "remote_claims": [{"type": "github_pr",
                               "repo": "solorion-dev/quantum", "number": 363,
                               "expect_head_sha": "abc123"}],
        })
        with self.assertRaises(ValueError):
            load_manifest(text)

    def test_remote_only_manifest_is_valid(self):
        text = json.dumps({
            "remote_snapshot": "snap.json",
            "remote_claims": [{"type": "tracker_status", "id": "TRK-0123",
                               "expect_status": "done"}],
        })
        m = load_manifest(text)
        self.assertEqual(m["remote_snapshot"], "snap.json")

    def test_remote_claims_without_snapshot_path_rejected(self):
        text = json.dumps({
            "remote_claims": [{"type": "tracker_status", "id": "TRK-0123",
                               "expect_status": "done"}],
        })
        with self.assertRaises(ValueError):
            load_manifest(text)

    def test_claims_alias_accepted(self):
        m = {"remote_snapshot": SNAP_PATH,
             "claims": [{"type": "tracker_status", "id": "TRK-0123",
                         "expect_status": "done"}]}
        r = run(m, fake_for())
        self.assertEqual(r.status, "verified")


if __name__ == "__main__":
    unittest.main()
