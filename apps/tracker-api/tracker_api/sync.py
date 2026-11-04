"""Sync engine. Tracker DB is source of truth; GitHub Projects is an outward mirror.
Inbound GitHub changes NEVER write items directly: they become suggested_changes for a human."""
import hashlib, hmac, json, uuid
from . import db

# tracker field -> Project v2 field name
MIRRORED = {"title": "Title", "status": "Status", "priority": "Priority", "points": "Points", "due_at": "Due", "id": "TRK"}
REVERSE = {v: k for k, v in MIRRORED.items() if k != "id"}
STATUS_TO_GH = {"backlog": "Backlog", "planned": "Todo", "in_progress": "In Progress", "in_review": "In Review",
                "blocked": "Blocked", "done": "Done", "cancelled": "Cancelled"}
GH_TO_STATUS = {v: k for k, v in STATUS_TO_GH.items()}

def _log(c, run_id, direction, item_id, action, result, detail=None, delivery_id=None):
    c.execute("INSERT INTO sync_log(run_id,direction,item_id,action,result,delivery_id,detail,at) VALUES(?,?,?,?,?,?,?,?)",
              (run_id, direction, item_id, action, result, delivery_id, detail, db.now()))

def _to_remote(field, value):
    return STATUS_TO_GH.get(value, value) if field == "status" else value

def _from_remote(field, value):
    return GH_TO_STATUS.get(value, value) if field == "status" else value

def suggest(c, item_id, field, current, proposed, actor=None, delivery_id=None, reason=None):
    """Create a pending suggestion. Duplicate pending suggestions (same item/field/value) are ignored."""
    cur = c.execute("""INSERT OR IGNORE INTO suggested_changes(item_id,field,current_value,proposed_value,remote_actor,
        delivery_id,reason,state,created_at) VALUES(?,?,?,?,?,?,?,'pending',?)""",
        (item_id, field, json.dumps(current), json.dumps(proposed), actor, delivery_id, reason, db.now()))
    return cur.rowcount == 1

def run_outbound(c, adapter, project_id=None, dry=False):
    """Idempotent mirror keyed by TRK id. Per field: push only if local differs from what we last pushed.
    If GitHub changed that field since our last push (remote != last_pushed), don't overwrite: suggest instead."""
    project_id = project_id or getattr(adapter, "PROJECT_ID", None)
    run_id = uuid.uuid4().hex[:12]
    stats = {"runId": run_id, "dry": dry, "added": 0, "updatedFields": 0, "unchanged": 0, "conflicts": 0, "errors": 0}
    for link in c.execute("SELECT * FROM github_links ORDER BY item_id").fetchall():
        item = c.execute("SELECT * FROM items WHERE id=?", (link["item_id"],)).fetchone()
        if not item: continue
        try:
            pid = link["project_item_id"]
            if not pid:
                if dry: stats["added"] += 1; continue
                pid = adapter.add_item(project_id, link["node_id"])
                c.execute("UPDATE github_links SET project_item_id=?, project_id=? WHERE item_id=? AND repo=?",
                          (pid, project_id, link["item_id"], link["repo"]))
                stats["added"] += 1
            remote = adapter.get_project_item(project_id, pid) or {"fields": {}, "updatedAt": None}
            pushed = json.loads(link["last_pushed"] or "{}")
            changed = False
            for f, gh in MIRRORED.items():
                want = _to_remote(f, item[f])
                have = remote["fields"].get(gh)
                if have == want:
                    pushed[gh] = want; continue
                if gh in pushed and have != pushed[gh] and f != "id":
                    # Remote edited since our last push: conflict -> human decides, local stays authoritative.
                    if suggest(c, item["id"], f, item[f], _from_remote(f, have), "github",
                               reason="remote edited during outbound"): stats["conflicts"] += 1
                    continue
                if dry: stats["updatedFields"] += 1; continue
                ts = adapter.update_field(project_id, pid, gh, want)
                pushed[gh] = want; stats["updatedFields"] += 1; changed = True
                remote["updatedAt"] = ts
            if not changed: stats["unchanged"] += 1
            if not dry:
                c.execute("""UPDATE github_links SET last_pushed=?, remote_updated_at=?, last_synced_at=?
                             WHERE item_id=? AND repo=?""",
                          (json.dumps(pushed), remote["updatedAt"], db.now(), link["item_id"], link["repo"]))
                _log(c, run_id, "out", item["id"], "mirror", "ok", json.dumps({"changed": changed}))
        except Exception as e:  # one bad item never stops the run
            stats["errors"] += 1
            if not dry: _log(c, run_id, "out", item["id"], "mirror", "error", str(e)[:300])
    return stats

# ---------------------------------------------------------------- webhooks
def verify_signature(secret: bytes, body: bytes, header: str | None) -> bool:
    if not secret or not header or not header.startswith("sha256="): return False
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)

class WebhookError(Exception):
    def __init__(self, status, msg): super().__init__(msg); self.status = status

def handle_webhook(c, adapter, secret, headers, body):
    h = {k.lower(): v for k, v in headers.items()}
    if not verify_signature(secret, body, h.get("x-hub-signature-256")):
        raise WebhookError(401, "bad signature")
    delivery, event = h.get("x-github-delivery"), h.get("x-github-event")
    if not delivery or not event: raise WebhookError(400, "missing delivery/event header")
    if c.execute("INSERT OR IGNORE INTO webhook_deliveries VALUES(?,?,?)", (delivery, event, db.now())).rowcount == 0:
        return {"duplicate": True, "suggestions": 0}
    payload = json.loads(body or b"{}")
    n = 0
    sender = (payload.get("sender") or {}).get("login")
    if event in ("issues", "pull_request"):
        obj = payload.get(event if event == "issues" else "pull_request") or payload.get("issue") or {}
        repo = (payload.get("repository") or {}).get("full_name")
        link = c.execute("SELECT * FROM github_links WHERE repo=? AND number=?", (repo, obj.get("number"))).fetchone()
        if link:
            item = c.execute("SELECT * FROM items WHERE id=?", (link["item_id"],)).fetchone()
            action = payload.get("action")
            if action == "closed" and item["status"] not in ("done", "cancelled"):
                n += suggest(c, item["id"], "status", item["status"], "done", sender, delivery, f"{event} closed on GitHub")
            elif action == "reopened" and item["status"] in ("done", "cancelled"):
                n += suggest(c, item["id"], "status", item["status"], "planned", sender, delivery, f"{event} reopened")
            elif action in ("assigned", "unassigned"):
                login = (payload.get("assignee") or {}).get("login")
                p = c.execute("SELECT handle FROM people WHERE github_login=?", (login,)).fetchone()
                proposed = (p["handle"] if p else None) if action == "assigned" else None
                if action == "assigned" and not p:
                    _log(c, None, "in", item["id"], "assign", "skipped", f"unknown github login", delivery)
                elif proposed != item["assignee_id"]:
                    n += suggest(c, item["id"], "assignee_id", item["assignee_id"], proposed, sender, delivery,
                                 f"{event} {action} on GitHub")
    elif event == "projects_v2_item":
        pid = (payload.get("projects_v2_item") or {}).get("node_id")
        link = c.execute("SELECT * FROM github_links WHERE project_item_id=?", (pid,)).fetchone()
        if link:
            item = c.execute("SELECT * FROM items WHERE id=?", (link["item_id"],)).fetchone()
            remote = adapter.get_project_item(link["project_id"], pid) or {"fields": {}}
            pushed = json.loads(link["last_pushed"] or "{}")
            for gh, f in REVERSE.items():
                if gh in remote["fields"] and remote["fields"][gh] != pushed.get(gh):
                    val = _from_remote(f, remote["fields"][gh])
                    if val != item[f]:
                        n += suggest(c, item["id"], f, item[f], val, sender, delivery, "Project field edited")
    elif event in ("installation", "installation_repositories"):
        pass  # recorded in sync_log only; installs are Scotty's action
    _log(c, None, "in", None, event, "ok", json.dumps({"suggestions": n}), delivery)
    return {"duplicate": False, "suggestions": n}

# ---------------------------------------------------------------- suggestions
def list_suggestions(c, state="pending"):
    rows = c.execute("SELECT * FROM suggested_changes WHERE (? IS NULL OR state=?) ORDER BY id", (state, state))
    return [{"id": f"SUG-{r['id']}", "itemId": r["item_id"], "field": r["field"],
             "currentValue": json.loads(r["current_value"]), "proposedValue": json.loads(r["proposed_value"]),
             "remoteActor": r["remote_actor"], "reason": r["reason"], "state": r["state"],
             "decidedBy": r["decided_by"], "decisionReason": r["decision_reason"], "decidedAt": r["decided_at"], "createdAt": r["created_at"]} for r in rows]

def _sid(s): return int(str(s).removeprefix("SUG-"))

def decide(c, sug_id, accept, actor, reason=None):
    r = c.execute("SELECT * FROM suggested_changes WHERE id=?", (_sid(sug_id),)).fetchone()
    if not r: raise KeyError(sug_id)
    if r["state"] != "pending": raise db.ValidationError(f"suggestion already {r['state']}")
    item = None
    if accept:
        # Applied as the accepting human; source marks provenance. Goes through normal validation + history.
        item, _ = db.update_item(c, r["item_id"], {r["field"]: json.loads(r["proposed_value"])}, actor,
                                 source="github-suggest")
    c.execute("UPDATE suggested_changes SET state=?, decided_by=?, decided_at=?, decision_reason=? WHERE id=?",
              ("accepted" if accept else "rejected", actor, db.now(), reason, r["id"]))
    c.execute("INSERT INTO events(item_id,kind,actor,body,at) VALUES(?,?,?,?,?)",
              (r["item_id"], "suggestion", actor, json.dumps({"id": f"SUG-{r['id']}", "accepted": accept,
                                                              "reason": reason}), db.now()))
    return {"suggestion": next(s for s in list_suggestions(c, None) if s["id"] == f"SUG-{r['id']}"),
            "item": item or db.get_item(c, r["item_id"])}
