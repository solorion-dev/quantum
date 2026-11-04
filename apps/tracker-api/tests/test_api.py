import json, threading, unittest, urllib.request
from http.server import ThreadingHTTPServer
from tracker_api.server import make_handler
from tests.helpers import app, hook

class Routes(unittest.TestCase):
    def setUp(self): self.a = app()
    def call(self, m, p, body=None, q=None, actor="pixel"):
        return self.a.handle(m, p, q or {}, {"X-Actor": actor}, json.dumps(body).encode() if body is not None else b"")

    def test_list_and_flags(self):
        st, out = self.call("GET", "/api/items", q={"limit": ["50"]})
        self.assertEqual((st, len(out["items"])), (200, 20))
        self.assertTrue({"stale", "needsTriage", "sync", "github"} <= set(out["items"][0]))

    def test_bare_paths_also_work(self):
        self.assertEqual(self.call("GET", "/items/TRK-9001")[0], 200)

    def test_detail(self):
        st, d = self.call("GET", "/api/items/TRK-9001")
        self.assertEqual(st, 200); self.assertIn("statusHistory", d); self.assertIn("githubLink", d)
        self.assertEqual(self.call("GET", "/api/items/TRK-0000")[0], 404)

    def test_create_patch_comment(self):
        st, it = self.call("POST", "/api/items", {"title": "From UI", "priority": "high", "assigneeId": "pixel"})
        self.assertEqual((st, it["assigneeId"]), (201, "pixel"))
        st, out = self.call("PATCH", f"/api/items/{it['id']}", {"status": "planned", "labels": ["ui"]})
        self.assertEqual((st, sorted(out["changed"])), (200, ["labels", "status"]))
        st, cm = self.call("POST", f"/api/items/{it['id']}/comments", {"body": "hi"})
        self.assertEqual((st, cm["actor"]), (201, "pixel"))
        self.assertEqual(self.call("PATCH", f"/api/items/{it['id']}", {"status": "bogus"})[0], 400)
        self.assertEqual(self.call("PATCH", f"/api/items/{it['id']}", {"assigneeId": "stranger"})[0], 400)

    def test_registries_and_sync(self):
        self.assertEqual(len(self.call("GET", "/api/people")[1]["people"]), 5)
        self.assertIn("ui", [l["name"] for l in self.call("GET", "/api/labels")[1]["labels"]])
        self.assertEqual(self.call("POST", "/api/sync/run", q={"dry": ["1"]})[1]["dry"], True)
        self.assertEqual(self.call("POST", "/api/sync/run")[1]["added"], 7)
        self.assertEqual(self.call("GET", "/api/sync/status")[1]["mirrored"], 7)
        self.assertTrue(self.call("GET", "/api/sync/log")[1]["log"])

    def test_suggestions_flow(self):
        hook(self.a, "issues", {"action": "closed", "issue": {"number": 103},
             "repository": {"full_name": "solorion-dev/sandbox"}}, "d-x")
        st, out = self.call("GET", "/api/suggestions", q={"state": ["pending"]})
        sid = out["suggestions"][0]["id"]
        st, r = self.call("POST", f"/api/suggestions/{sid}/reject", {"reason": "nope"})
        self.assertEqual((st, r["suggestion"]["state"]), (200, "rejected"))
        self.assertEqual(self.call("POST", f"/api/suggestions/{sid}/accept", {})[0], 400)
        self.assertEqual(len(self.call("GET", "/api/suggestions", q={"state": ["all"]})[1]["suggestions"]), 1)

class Http(unittest.TestCase):
    """Real socket round-trip on an ephemeral port (in-memory DB)."""
    def test_http_roundtrip_and_cors(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app(), "http://localhost:5173"))
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        try:
            base = f"http://127.0.0.1:{srv.server_port}"
            with urllib.request.urlopen(base + "/api/items/TRK-9002") as r:
                self.assertEqual(r.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
                self.assertEqual(json.load(r)["item"]["id"], "TRK-9002")
            req = urllib.request.Request(base + "/api/items/TRK-9002", method="PATCH",
                                         data=json.dumps({"priority": "low"}).encode(),
                                         headers={"Content-Type": "application/json", "X-Actor": "pixel"})
            with urllib.request.urlopen(req) as r: self.assertEqual(json.load(r)["item"]["priority"], "low")
        finally:
            srv.shutdown()

if __name__ == "__main__": unittest.main()

class Config(unittest.TestCase):
    def test_missing_webhook_secret_refuses_to_start(self):
        from tracker_api.server import load_webhook_secret, ConfigError
        for env in ({}, {"TRACKER_WEBHOOK_SECRET": ""}, {"TRACKER_WEBHOOK_SECRET": "  "}):
            with self.assertRaises(ConfigError) as cm: load_webhook_secret(env)
            self.assertIn("refusing to start", str(cm.exception.code))
        self.assertEqual(load_webhook_secret({"TRACKER_WEBHOOK_SECRET": "test-only-fake"}), b"test-only-fake")
    def test_main_exits_nonzero_without_secret(self):
        import os, subprocess, sys, tempfile
        env = {k: v for k, v in os.environ.items() if k != "TRACKER_WEBHOOK_SECRET"}
        db = os.path.join(tempfile.mkdtemp(), "x.db")
        p = subprocess.run([sys.executable, "-m", "tracker_api", "--db", db, "--port", "0"], env=env,
                           capture_output=True, text=True, timeout=20)
        self.assertNotEqual(p.returncode, 0); self.assertIn("TRACKER_WEBHOOK_SECRET", p.stderr)
        self.assertFalse(os.path.exists(db))
    def test_no_hardcoded_default_secret(self):
        import inspect, tracker_api.server as s
        self.assertNotIn("local-dev-fake-secret", inspect.getsource(s))

class Delete(unittest.TestCase):
    def test_delete_is_501_with_message(self):
        st, out = app().handle("DELETE", "/api/items/TRK-9001", {}, {}, b"")
        self.assertEqual(st, 501); self.assertIn("cancelled", out["error"])
