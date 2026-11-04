import json, unittest
from tracker_api import db, sync
from tracker_api.github_mock import MockGraphQLAdapter
from tests.helpers import fresh, sign, FAKE_SECRET, hook, app

LINKED = ["TRK-9001", "TRK-9004", "TRK-9007", "TRK-9010", "TRK-9013", "TRK-9016", "TRK-9019"]

class Outbound(unittest.TestCase):
    def setUp(self): self.c, self.gh = fresh(), MockGraphQLAdapter()

    def test_first_run_mirrors_linked_items(self):
        s = sync.run_outbound(self.c, self.gh)
        self.assertEqual((s["added"], s["errors"]), (7, 0))
        pid = self.c.execute("SELECT project_item_id FROM github_links WHERE item_id='TRK-9001'").fetchone()[0]
        f = self.gh.items[pid]["fields"]
        self.assertEqual((f["TRK"], f["Status"], f["Priority"]), ("TRK-9001", "Backlog", "critical"))

    def test_idempotent_rerun(self):
        sync.run_outbound(self.c, self.gh); n = len(self.gh.calls)
        s = sync.run_outbound(self.c, self.gh)
        self.assertEqual((s["added"], s["updatedFields"], s["unchanged"]), (0, 0, 7))
        mutations = [x for x in self.gh.calls[n:] if x[0] != "node(ProjectV2Item)"]
        self.assertEqual(mutations, [])
        self.assertEqual(len(self.gh.items), 7)

    def test_upsert_keyed_by_trk_after_lost_link(self):
        sync.run_outbound(self.c, self.gh)
        self.c.execute("UPDATE github_links SET project_item_id=NULL WHERE item_id='TRK-9001'")
        sync.run_outbound(self.c, self.gh)
        self.assertEqual(len(self.gh.items), 7)   # no duplicate Project item

    def test_local_change_pushes_only_that_field(self):
        sync.run_outbound(self.c, self.gh); n = len(self.gh.calls)
        db.update_item(self.c, "TRK-9001", {"status": "in_progress"}, "volt")
        s = sync.run_outbound(self.c, self.gh)
        self.assertEqual(s["updatedFields"], 1)
        muts = [x for x in self.gh.calls[n:] if x[0] == "updateProjectV2ItemFieldValue"]
        self.assertEqual([(m[2], m[3]) for m in muts], [("Status", "In Progress")])
        self.assertEqual(db.get_item(self.c, "TRK-9001")["sync"]["state"], "synced")

    def test_conflict_becomes_suggestion_not_overwrite(self):
        sync.run_outbound(self.c, self.gh)
        pid = self.c.execute("SELECT project_item_id FROM github_links WHERE item_id='TRK-9001'").fetchone()[0]
        self.gh.remote_edit(pid, "Priority", "low")
        db.update_item(self.c, "TRK-9001", {"priority": "high"}, "volt")
        s = sync.run_outbound(self.c, self.gh)
        self.assertEqual(s["conflicts"], 1)
        self.assertEqual(self.gh.items[pid]["fields"]["Priority"], "low")          # not clobbered
        self.assertEqual(db.get_item(self.c, "TRK-9001")["priority"], "high")       # DB still truth
        self.assertEqual(sync.list_suggestions(self.c)[0]["proposedValue"], "low")
        sync.run_outbound(self.c, self.gh)                                          # no duplicate suggestion
        self.assertEqual(len(sync.list_suggestions(self.c)), 1)

    def test_dry_run_changes_nothing(self):
        s = sync.run_outbound(self.c, self.gh, dry=True)
        self.assertEqual((s["added"], len(self.gh.items)), (7, 0))
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM sync_log").fetchone()[0], 0)

    def test_dry_run_plans_same_counts_as_real_run(self):
        d = sync.run_outbound(self.c, self.gh, dry=True)
        r = sync.run_outbound(self.c, self.gh)
        self.assertGreater(r["updatedFields"], 0)
        for k in ("added", "updatedFields", "unchanged", "conflicts", "errors"):
            self.assertEqual(d[k], r[k], k)
        d2 = sync.run_outbound(self.c, self.gh, dry=True)             # after a real run, dry re-run plans nothing
        self.assertEqual((d2["added"], d2["updatedFields"]), (0, 0))

    def test_error_isolated_per_item(self):
        self.gh.fail_on.add("NODE_solorion-dev/sandbox#100")
        s = sync.run_outbound(self.c, self.gh)
        self.assertEqual((s["errors"], s["added"]), (1, 6))
        self.assertEqual(db.get_item(self.c, "TRK-9001")["sync"]["state"], "error")

class Webhooks(unittest.TestCase):
    def setUp(self): self.a = app(); self.c = self.a.c

    def test_signature(self):
        self.assertTrue(sync.verify_signature(FAKE_SECRET, b"x", sign(b"x")))
        self.assertFalse(sync.verify_signature(FAKE_SECRET, b"x", sign(b"y")))
        self.assertFalse(sync.verify_signature(FAKE_SECRET, b"x", None))
        self.assertFalse(sync.verify_signature(b"", b"x", sign(b"x", b"")))
        self.assertFalse(sync.verify_signature(FAKE_SECRET, b"x", sign(b"x", b"other-fake")))

    def test_bad_signature_rejected_and_not_recorded(self):
        st, _ = hook(self.a, "issues", {"action": "closed"}, "d-1", sig="sha256=deadbeef")
        self.assertEqual(st, 401)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM webhook_deliveries").fetchone()[0], 0)

    def _close(self, delivery, number=100):
        return hook(self.a, "issues", {"action": "closed", "issue": {"number": number},
                    "repository": {"full_name": "solorion-dev/sandbox"}, "sender": {"login": "someone-fake"}}, delivery)

    def test_close_creates_suggestion_only(self):
        st, out = self._close("d-2")
        self.assertEqual((st, out["suggestions"]), (202, 1))
        self.assertEqual(db.get_item(self.c, "TRK-9001")["status"], "backlog")   # unchanged
        s = sync.list_suggestions(self.c)[0]
        self.assertEqual((s["itemId"], s["field"], s["proposedValue"], s["state"]), ("TRK-9001", "status", "done", "pending"))

    def test_delivery_dedupe(self):
        self._close("d-3"); st, out = self._close("d-3")
        self.assertTrue(out["duplicate"]); self.assertEqual(len(sync.list_suggestions(self.c)), 1)

    def test_unlinked_issue_ignored(self):
        _, out = self._close("d-4", number=999); self.assertEqual(out["suggestions"], 0)

    def test_assignee_via_people_table(self):
        p = {"action": "assigned", "issue": {"number": 100}, "repository": {"full_name": "solorion-dev/sandbox"},
             "assignee": {"login": "pixel-fake-gh"}}
        hook(self.a, "issues", p, "d-5")
        s = sync.list_suggestions(self.c)[0]
        self.assertEqual((s["field"], s["proposedValue"]), ("assignee_id", "pixel"))
        p["assignee"] = {"login": "not-in-people"}
        _, out = hook(self.a, "issues", p, "d-6"); self.assertEqual(out["suggestions"], 0)

    def test_project_item_edit(self):
        sync.run_outbound(self.c, self.a.adapter)
        pid = self.c.execute("SELECT project_item_id FROM github_links WHERE item_id='TRK-9004'").fetchone()[0]
        self.a.adapter.remote_edit(pid, "Status", "Done")
        _, out = hook(self.a, "projects_v2_item", {"action": "edited", "projects_v2_item": {"node_id": pid}}, "d-7")
        self.assertEqual(out["suggestions"], 1)
        self.assertEqual(sync.list_suggestions(self.c)[0]["proposedValue"], "done")

class Suggestions(unittest.TestCase):
    def setUp(self):
        self.a = app(); self.c = self.a.c
        hook(self.a, "issues", {"action": "closed", "issue": {"number": 100},
             "repository": {"full_name": "solorion-dev/sandbox"}}, "d-a")

    def test_accept_applies_and_logs_history(self):
        sid = sync.list_suggestions(self.c)[0]["id"]
        out = sync.decide(self.c, sid, True, "coda")
        self.assertEqual(out["item"]["status"], "done")
        h = self.c.execute("SELECT to_status, actor, source FROM status_history WHERE item_id='TRK-9001' ORDER BY id DESC").fetchone()
        self.assertEqual(tuple(h), ("done", "coda", "github-suggest"))
        self.assertEqual(sync.list_suggestions(self.c), [])
        with self.assertRaises(db.ValidationError): sync.decide(self.c, sid, True, "coda")

    def test_reject_with_reason(self):
        sid = sync.list_suggestions(self.c)[0]["id"]
        out = sync.decide(self.c, sid, False, "coda", "still open on our side")
        self.assertEqual((out["suggestion"]["state"], out["suggestion"]["decisionReason"]), ("rejected", "still open on our side"))
        self.assertEqual(db.get_item(self.c, "TRK-9001")["status"], "backlog")

if __name__ == "__main__": unittest.main()
