import hashlib, hmac, json, os
from tracker_api import db
from tracker_api.github_mock import MockGraphQLAdapter
from tracker_api.server import App

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", "items.json")
FAKE_SECRET = b"test-only-fake-secret"

def fresh(path=":memory:"):
    c = db.connect(path); db.migrate(c); db.seed(c, FIXTURE); return c

def app():
    return App(fresh(), MockGraphQLAdapter(), FAKE_SECRET)

def sign(body, secret=FAKE_SECRET):
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

def hook(app, event, payload, delivery, secret=FAKE_SECRET, sig=None):
    body = json.dumps(payload).encode()
    h = {"X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": sig or sign(body, secret)}
    return app.handle("POST", "/api/webhooks/github", {}, h, body)
