"""HTTP API (stdlib). Routes are served under /api; the bare paths (/items...) also work."""
import json, os, re, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from . import db, sync
from .github_mock import MockGraphQLAdapter

class App:
    def __init__(self, conn, adapter=None, webhook_secret=b"", actor_default="board-ui"):
        self.c, self.adapter, self.secret, self.actor_default = conn, adapter or MockGraphQLAdapter(), webhook_secret, actor_default
        self.lock = threading.Lock()

    def handle(self, method, path, query, headers, body):
        """Returns (status, payload). Pure function of inputs + DB; used by the HTTP server and the tests."""
        path = re.sub(r"^/api(?=/)", "", path.rstrip("/") or "/")
        actor = headers.get("X-Actor") or headers.get("x-actor") or self.actor_default
        q = {k: v[0] for k, v in query.items()}
        def js():
            try: return json.loads(body or b"{}")
            except ValueError: raise db.ValidationError("invalid JSON body")
        c = self.c
        with self.lock:
            try:
                if method == "GET" and path == "/health":
                    return 200, {"ok": True, "adapter": type(self.adapter).__name__}
                if method == "GET" and path == "/items":
                    return 200, db.list_items(c, q.get("status"), q.get("kind"), q.get("label"), q.get("assignee"),
                                              q.get("q"), q.get("cursor"), q.get("limit", 50))
                if method == "POST" and path == "/items":
                    return 201, db.create_item(c, _camel_in(js()), actor)
                m = re.fullmatch(r"/items/(TRK-\d+)", path)
                if m and method == "GET":
                    d = db.item_detail(c, m[1]); return (200, d) if d else (404, {"error": "not found"})
                if m and method == "PATCH":
                    item, changed = db.update_item(c, m[1], _camel_in(js()), actor); return 200, {"item": item, "changed": changed}
                m = re.fullmatch(r"/items/(TRK-\d+)/comments", path)
                if m and method == "POST":
                    return 201, db.add_comment(c, m[1], actor, js().get("body"))
                if method == "GET" and path == "/people":
                    return 200, {"people": [{"id": r["handle"], "name": r["name"], "kind": r["kind"],
                                             "githubLogin": r["github"] or None, "active": bool(r["active"])}
                                            for r in c.execute("SELECT * FROM people ORDER BY handle")]}
                if method == "GET" and path == "/labels":
                    return 200, {"labels": [dict(r) for r in c.execute("SELECT name, color FROM tags ORDER BY name")]}
                if method == "GET" and path in ("/suggestions", "/sync/suggestions"):
                    st = q.get("state", "pending"); return 200, {"suggestions": sync.list_suggestions(c, None if st == "all" else st)}
                m = re.fullmatch(r"/(?:sync/)?suggestions/(SUG-\d+|\d+)/(accept|reject)", path)
                if m and method == "POST":
                    return 200, sync.decide(c, m[1], m[2] == "accept", actor, js().get("reason"))
                if method == "GET" and path == "/sync/status":
                    r = c.execute("SELECT COUNT(*) n, SUM(project_item_id IS NOT NULL) m FROM github_links").fetchone()
                    last = c.execute("SELECT at, result FROM sync_log WHERE direction='out' ORDER BY id DESC LIMIT 1").fetchone()
                    pend = c.execute("SELECT COUNT(*) FROM suggested_changes WHERE state='pending'").fetchone()[0]
                    return 200, {"adapter": type(self.adapter).__name__, "linked": r["n"], "mirrored": r["m"] or 0,
                                 "pendingSuggestions": pend, "lastRun": dict(last) if last else None}
                if method == "GET" and path == "/sync/log":
                    return 200, {"log": [dict(r) for r in c.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT ?",
                                                                     (min(int(q.get("limit", 100)), 500),))]}
                if method == "POST" and path == "/sync/run":
                    return 200, sync.run_outbound(c, self.adapter, dry=q.get("dry") in ("1", "true"))
                if method == "POST" and path == "/webhooks/github":
                    return 202, sync.handle_webhook(c, self.adapter, self.secret, headers, body or b"")
                return 404, {"error": "no route"}
            except db.ValidationError as e: return 400, {"error": str(e)}
            except KeyError as e: return 404, {"error": f"not found: {e}"}
            except sync.WebhookError as e: return e.status, {"error": str(e)}

CAMEL = {"assigneeId": "assignee_id", "dueAt": "due_at", "parentId": "parent_id"}
def _camel_in(d): return {CAMEL.get(k, k): v for k, v in d.items()}

def make_handler(app, cors_origin):
    class H(BaseHTTPRequestHandler):
        def _go(self, method):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            status, payload = app.handle(method, u.path, parse_qs(u.query), dict(self.headers.items()), body)
            out = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
            self._cors(); self.end_headers(); self.wfile.write(out)
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Actor")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        def do_OPTIONS(self): self.send_response(204); self._cors(); self.end_headers()
        def do_GET(self): self._go("GET")
        def do_POST(self): self._go("POST")
        def do_PATCH(self): self._go("PATCH")
        def log_message(self, fmt, *a): pass  # never log bodies/headers (signatures)
    return H

def main():
    import argparse
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Tracker API (local SQLite copy + mock GitHub)")
    ap.add_argument("--db", default=os.environ.get("TRACKER_DB", os.path.join(here, "data", "tracker-local.db")))
    ap.add_argument("--fixture", default=os.path.join(here, "fixtures", "items.json"))
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 7655)))
    ap.add_argument("--reset", action="store_true", help="delete and reseed the local DB")
    ap.add_argument("--cors", default=os.environ.get("CORS_ORIGIN", "http://localhost:5173"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.db)), exist_ok=True)
    if a.reset and os.path.exists(a.db): os.remove(a.db)
    fresh = not os.path.exists(a.db)
    c = db.connect(a.db); db.migrate(c)
    if fresh: print(f"seeded {db.seed(c, a.fixture)} fixture items into {a.db}")
    # Fake local secret by default; a real one only ever comes from Tritium env (Scotty's install).
    secret = os.environ.get("TRACKER_WEBHOOK_SECRET", "local-dev-fake-secret").encode()
    app = App(c, MockGraphQLAdapter(), secret)
    print(f"tracker-api on http://{a.host}:{a.port}/api  (adapter=mock, db={a.db})")
    ThreadingHTTPServer((a.host, a.port), make_handler(app, a.cors)).serve_forever()

if __name__ == "__main__":
    main()
