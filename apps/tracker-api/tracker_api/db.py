"""Schema, additive migrations, seeding and item CRUD."""
import json, os, sqlite3, datetime as dt
from pathlib import Path

STATUSES = ("backlog", "planned", "in_progress", "in_review", "blocked", "done", "cancelled")
PRIORITIES = ("critical", "high", "medium", "low", "none")
KINDS = ("goal", "issue", "task", "decision", "milestone", "bug", "note")
EDITABLE = ("title", "body", "status", "priority", "assignee_id", "due_at", "points", "kind", "parent_id")
LIVE_DB = "/mnt/fast/tracker/tracker.db"

def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

# 001 mirrors the live tracker's known shape. 002+ are ADDITIVE ONLY (new tables / new columns).
MIGRATIONS = [
    # 001 is the live Tritium schema EXACTLY (read-only dump, 2026-11-04). Never edit it.
    ("001_base", """
    CREATE TABLE IF NOT EXISTS embeddings (item_id TEXT PRIMARY KEY, model TEXT, dim INTEGER,
      vec BLOB, text_hash TEXT);
    CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL,
      ts TEXT NOT NULL, actor TEXT DEFAULT 'cooper', kind TEXT NOT NULL, text TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS item_tags (item_id TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY (item_id, tag));
    CREATE TABLE IF NOT EXISTS items (
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT DEFAULT '',
      status TEXT NOT NULL DEFAULT 'planned', priority TEXT NOT NULL DEFAULT 'none',
      assignee TEXT DEFAULT '', parent_id TEXT DEFAULT '', due_at TEXT DEFAULT '',
      points INTEGER, source TEXT DEFAULT 'manual', external_ref TEXT DEFAULT '',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL,
      kind TEXT NOT NULL, url TEXT NOT NULL, label TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS people (handle TEXT PRIMARY KEY, name TEXT NOT NULL,
      kind TEXT NOT NULL DEFAULT 'agent', matrix_id TEXT DEFAULT '', email TEXT DEFAULT '',
      github TEXT DEFAULT '', hub_worker TEXT DEFAULT '', notes TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS relations (item_id TEXT NOT NULL, related_id TEXT NOT NULL,
      relation TEXT NOT NULL DEFAULT 'related', PRIMARY KEY (item_id, related_id, relation));
    CREATE TABLE IF NOT EXISTS tags (name TEXT PRIMARY KEY);
    CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind);
    CREATE INDEX IF NOT EXISTS idx_items_status ON items(status)
    """),
    # people.github already exists (GitHub login) -> reused, not duplicated. Existing tags/item_tags ARE the labels.
    ("002_people_link", """
    ALTER TABLE people ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE items ADD COLUMN assignee_id TEXT REFERENCES people(handle);
    ALTER TABLE items ADD COLUMN field_clock TEXT NOT NULL DEFAULT '{}';
    UPDATE items SET assignee_id = assignee WHERE assignee IN (SELECT handle FROM people)
    """),
    ("003_labels_history", """
    ALTER TABLE tags ADD COLUMN color TEXT DEFAULT '#888888';
    INSERT OR IGNORE INTO tags(name) SELECT DISTINCT tag FROM item_tags;
    CREATE TABLE status_history(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL, from_status TEXT,
      to_status TEXT NOT NULL, actor TEXT, source TEXT NOT NULL DEFAULT 'ui', at TEXT NOT NULL)
    """),
    ("004_github_sync", """
    CREATE TABLE github_links(item_id TEXT NOT NULL, repo TEXT NOT NULL, number INTEGER NOT NULL,
      type TEXT NOT NULL DEFAULT 'issue', node_id TEXT, project_id TEXT, project_item_id TEXT, url TEXT,
      etag TEXT, remote_updated_at TEXT, last_synced_at TEXT, last_pushed TEXT NOT NULL DEFAULT '{}',
      UNIQUE(repo, number), UNIQUE(item_id, repo));
    CREATE TABLE suggested_changes(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL, field TEXT NOT NULL,
      current_value TEXT, proposed_value TEXT, remote_actor TEXT, delivery_id TEXT, reason TEXT,
      state TEXT NOT NULL DEFAULT 'pending', decided_by TEXT, decision_reason TEXT, decided_at TEXT, created_at TEXT NOT NULL);
    CREATE UNIQUE INDEX suggested_open_uq ON suggested_changes(item_id, field, proposed_value) WHERE state = 'pending';
    CREATE TABLE sync_log(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, direction TEXT NOT NULL, item_id TEXT,
      action TEXT NOT NULL, result TEXT NOT NULL, delivery_id TEXT, detail TEXT, at TEXT NOT NULL);
    CREATE TABLE webhook_deliveries(delivery_id TEXT PRIMARY KEY, event TEXT NOT NULL, received_at TEXT NOT NULL);
    """),
]

def connect(path):
    p = os.path.realpath(str(path)) if path != ":memory:" else path
    if p != ":memory:" and (p == LIVE_DB or p.startswith("/mnt/fast/tracker/")):
        raise RuntimeError("refusing to open the live tracker DB; use a local copy")
    c = sqlite3.connect(p, check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = OFF")
    return c

def migrate(c):
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, at TEXT NOT NULL)")
    done = {r[0] for r in c.execute("SELECT name FROM schema_migrations")}
    applied = []
    for name, sql in MIGRATIONS:
        if name in done:
            continue
        c.execute("BEGIN")
        try:
            for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                c.execute(stmt)
            c.execute("INSERT INTO schema_migrations VALUES(?,?)", (name, now()))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        applied.append(name)
    return applied

def seed(c, fixture_path):
    data = json.loads(Path(fixture_path).read_text())
    people = {it["assigneeId"] for it in data["items"] if it.get("assigneeId")}
    for h in sorted(people):
        c.execute("INSERT OR IGNORE INTO people(handle, name, kind, github) VALUES(?,?,?,?)",
                  (h, h.title(), "agent", f"{h}-fake-gh"))
    for it in data["items"]:
        c.execute("""INSERT OR REPLACE INTO items(id,kind,title,body,status,priority,assignee,assignee_id,parent_id,
          due_at,points,source,created_at,updated_at,field_clock) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'{}')""",
          (it["id"], it["kind"], it["title"], it["body"], it["status"], it["priority"], it["assigneeId"] or "",
           it["assigneeId"], it["parentId"] or "", it["dueAt"] or "", it["points"], "fixture", it["createdAt"], it["updatedAt"]))
        set_labels(c, it["id"], it.get("labels", []))
        if it["parentId"]:
            c.execute("INSERT OR IGNORE INTO relations(item_id, related_id, relation) VALUES(?,?,?)",
                      (it["parentId"], it["id"], "parent"))
        for cm in it.get("comments", []):
            c.execute("INSERT INTO events(item_id,kind,actor,text,ts) VALUES(?,?,?,?,?)",
                      (it["id"], "comment", cm["actor"], cm["body"], cm["at"]))
        for ln in it.get("links", []):
            c.execute("INSERT INTO links(item_id,kind,url,label) VALUES(?,?,?,?)",
                      (it["id"], ln["kind"], ln["target"], ln.get("label") or ""))
        c.execute("INSERT INTO status_history(item_id,from_status,to_status,actor,source,at) VALUES(?,?,?,?,?,?)",
                  (it["id"], None, it["status"], "fixture", "fixture", it["createdAt"]))
        g = it.get("github")
        if g:
            c.execute("""INSERT OR REPLACE INTO github_links(item_id,repo,number,type,node_id,project_item_id,url,
              etag,remote_updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
              (it["id"], g["repo"], g["number"], g["type"], f"NODE_{g['repo']}#{g['number']}", None, g["url"],
               None, None))
    return len(data["items"])

def set_labels(c, item_id, names):
    c.execute("DELETE FROM item_tags WHERE item_id=?", (item_id,))
    for n in names:
        c.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (n,))
        c.execute("INSERT OR IGNORE INTO item_tags(item_id, tag) VALUES(?,?)", (item_id, n))

def labels_of(c, item_id):
    return [r[0] for r in c.execute("SELECT tag FROM item_tags WHERE item_id=? ORDER BY tag", (item_id,))]

def next_id(c):
    r = c.execute("SELECT MAX(CAST(SUBSTR(id,5) AS INTEGER)) FROM items WHERE id LIKE 'TRK-%'").fetchone()[0]
    return f"TRK-{(r or 0) + 1:04d}"

class ValidationError(ValueError):
    pass

def _validate(c, f, v):
    if f == "status" and v not in STATUSES: raise ValidationError(f"bad status {v!r}")
    if f == "priority" and v not in PRIORITIES: raise ValidationError(f"bad priority {v!r}")
    if f == "kind" and v not in KINDS: raise ValidationError(f"bad kind {v!r}")
    if f == "points" and v is not None and not isinstance(v, int): raise ValidationError("points must be int")
    if f == "title" and not (isinstance(v, str) and v.strip()): raise ValidationError("title required")
    if f == "assignee_id" and v is not None and not c.execute(
            "SELECT 1 FROM people WHERE handle=? AND active=1", (v,)).fetchone():
        raise ValidationError(f"unknown person {v!r} (people table is the authority)")

def create_item(c, fields, actor, source="ui"):
    fields = dict(fields)
    item_id = next_id(c)
    fields.setdefault("kind", "task"); fields.setdefault("status", "backlog"); fields.setdefault("priority", "none")
    for f in list(fields):
        if f not in EDITABLE and f != "labels": raise ValidationError(f"field {f!r} not allowed")
        if f != "labels": _validate(c, f, fields[f])
    t = now()
    clock = {f: {"writer": actor, "source": source, "at": t} for f in fields if f != "labels"}
    c.execute("BEGIN")
    c.execute("""INSERT INTO items(id,kind,title,body,status,priority,assignee,assignee_id,parent_id,due_at,points,
      source,created_at,updated_at,field_clock) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (item_id, fields["kind"], fields["title"], fields.get("body", ""), fields["status"], fields["priority"],
       fields.get("assignee_id") or "", fields.get("assignee_id"), fields.get("parent_id") or "",
       fields.get("due_at") or "", fields.get("points"), source, t, t, json.dumps(clock)))
    set_labels(c, item_id, fields.get("labels", []))
    c.execute("INSERT INTO status_history(item_id,from_status,to_status,actor,source,at) VALUES(?,?,?,?,?,?)",
              (item_id, None, fields["status"], actor, source, t))
    c.execute("INSERT INTO events(item_id,kind,actor,text,ts) VALUES(?,?,?,?,?)", (item_id, "created", actor, "", t))
    c.execute("COMMIT")
    return get_item(c, item_id)

def update_item(c, item_id, changes, actor, source="ui"):
    row = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row: raise KeyError(item_id)
    changes = dict(changes)
    labels = changes.pop("labels", None)
    for f, v in changes.items():
        if f not in EDITABLE: raise ValidationError(f"field {f!r} not allowed")
        _validate(c, f, v)
    norm = lambda f, x: None if x == "" and f in ("parent_id", "due_at", "assignee_id") else x
    diff = {f: v for f, v in changes.items() if norm(f, row[f]) != v}
    if not diff and (labels is None or sorted(labels) == labels_of(c, item_id)):
        return get_item(c, item_id), []
    t = now()
    clock = json.loads(row["field_clock"] or "{}")
    c.execute("BEGIN")
    for f, v in diff.items():
        stored = "" if v is None and f in ("parent_id", "due_at") else v   # live convention: '' not NULL
        c.execute(f"UPDATE items SET {f}=? WHERE id=?", (stored, item_id))  # f is whitelisted above
        if f == "assignee_id": c.execute("UPDATE items SET assignee=? WHERE id=?", (v or "", item_id))
        clock[f] = {"writer": actor, "source": source, "at": t}
        c.execute("INSERT INTO events(item_id,kind,actor,text,ts) VALUES(?,?,?,?,?)",
                  (item_id, "change", actor, json.dumps({"field": f, "from": row[f], "to": v}), t))
    if "status" in diff:
        c.execute("INSERT INTO status_history(item_id,from_status,to_status,actor,source,at) VALUES(?,?,?,?,?,?)",
                  (item_id, row["status"], diff["status"], actor, source, t))
    if labels is not None:
        set_labels(c, item_id, labels); clock["labels"] = {"writer": actor, "source": source, "at": t}
        diff["labels"] = labels
    c.execute("UPDATE items SET updated_at=?, field_clock=? WHERE id=?", (t, json.dumps(clock), item_id))
    c.execute("COMMIT")
    return get_item(c, item_id), list(diff)

def _link(c, item_id):
    g = c.execute("SELECT * FROM github_links WHERE item_id=? LIMIT 1", (item_id,)).fetchone()
    if not g: return None
    return {"repo": g["repo"], "number": g["number"], "type": g["type"], "projectItemId": g["project_item_id"],
            "url": g["url"], "etag": g["etag"], "remoteUpdatedAt": g["remote_updated_at"]}, g

def item_json(c, row):
    link = _link(c, row["id"])
    sug = c.execute("SELECT id FROM suggested_changes WHERE item_id=? AND state='pending' ORDER BY id LIMIT 1",
                    (row["id"],)).fetchone()
    err = c.execute("SELECT detail FROM sync_log WHERE item_id=? ORDER BY id DESC LIMIT 1 ", (row["id"],)).fetchone()
    last_err = c.execute("SELECT result, detail FROM sync_log WHERE item_id=? AND direction='out' ORDER BY id DESC "
                         "LIMIT 1", (row["id"],)).fetchone()
    if not link: state = "unlinked"
    elif sug: state = "suggested"
    elif last_err and last_err["result"] == "error": state = "error"
    elif link[1]["last_synced_at"] and link[1]["last_synced_at"] >= row["updated_at"]: state = "synced"
    else: state = "pending"
    return {"id": row["id"], "kind": row["kind"], "title": row["title"], "body": row["body"], "status": row["status"],
            "priority": row["priority"], "assigneeId": row["assignee_id"] or None, "labels": labels_of(c, row["id"]),
            "parentId": row["parent_id"] or None, "dueAt": row["due_at"] or None, "points": row["points"],
            "externalRef": row["external_ref"] or None, "source": row["source"],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"], **flags(c, row),
            "project": project_of(c, row), "automated": is_automated(c, row), "github": link[0] if link else None,
            "sync": {"state": state, "lastSyncedAt": link[1]["last_synced_at"] if link else None,
                     "pendingSuggestionId": f"SUG-{sug['id']}" if sug else None,
                     "error": last_err["detail"] if state == "error" else None}}

STALE_DAYS = 14

def _has_col(c, table, col):
    return any(r[1] == col for r in c.execute(f"PRAGMA table_info({table})"))

def project_of(c, row):
    """Item's project. Live schema has no project column, so unless an explicit items.project column exists
    (proposed in migrations/002_project_column.sql, not applied) it's the top-level ancestor via parent_id.
    A root item is its own project. Cycles/missing parents stop at the last reachable item."""
    if "project" in row.keys() and row["project"]:
        return {"id": row["project"], "title": None, "derived": False}
    cur, seen = row, {row["id"]}
    while cur["parent_id"] and cur["parent_id"] not in seen:
        nxt = c.execute("SELECT id, title, parent_id FROM items WHERE id=?", (cur["parent_id"],)).fetchone()
        if not nxt: break
        seen.add(nxt["id"]); cur = nxt
    return {"id": cur["id"], "title": cur["title"], "derived": True}

# `automated` rule: true only when the item's CREATING write or its LAST write came from an UNATTENDED path.
#   creator     = actor of the item's 'created' event (plus items.source)
#   last writer = the field_clock entry with the latest `at` (per-field provenance)
#   unattended  = write source in AUTOMATED_SOURCES, or the handle is a system actor in SYSTEM_ACTORS.
#   people.kind does NOT count: an agent (or human) writing through the board UI / API with X-Actor is a
#   directed write, not automated. Accepting a GitHub suggestion is a write by the accepting person.
AUTOMATED_SOURCES = {"sync", "github", "github-sync", "webhook", "a2a", "automation"}
SYSTEM_ACTORS = {"sync", "github-sync", "a2a", "webhook"}

def _actor_automated(c, actor, source=None):
    if source and source in AUTOMATED_SOURCES: return True
    return bool(actor and actor in SYSTEM_ACTORS)

def is_automated(c, row):
    ev = c.execute("SELECT actor FROM events WHERE item_id=? AND kind='created' ORDER BY id LIMIT 1",
                   (row["id"],)).fetchone()
    if _actor_automated(c, ev["actor"] if ev else None, row["source"]): return True
    try: clock = json.loads(row["field_clock"] or "{}")
    except ValueError: clock = {}
    if clock:
        last = max(clock.values(), key=lambda v: v.get("at") or "")
        if _actor_automated(c, last.get("writer"), last.get("source")): return True
    return False

def flags(c, row, now_ts=None):
    ref = now_ts or dt.datetime.now(dt.timezone.utc)
    try:
        t = dt.datetime.fromisoformat((row["updated_at"] or "").replace("Z", "+00:00"))
        if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
        age = (ref - t).total_seconds()
    except ValueError:
        age = 0  # unparseable legacy timestamp: don't flag
    stale = row["status"] not in ("done", "cancelled") and age > STALE_DAYS * 86400
    triage = (not row["assignee_id"]) or row["priority"] == "none" or (
        row["status"] == "backlog" and not labels_of(c, row["id"]))
    return {"stale": bool(stale), "needsTriage": bool(triage)}

def get_item(c, item_id):
    row = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return item_json(c, row) if row else None

def list_items(c, status=None, kind=None, label=None, assignee=None, q=None, cursor=None, limit=50):
    sql, args = "SELECT * FROM items WHERE 1=1", []
    if status: sql += " AND status=?"; args.append(status)
    if kind: sql += " AND kind=?"; args.append(kind)
    if assignee: sql += " AND assignee_id=?"; args.append(assignee)
    if q: sql += " AND (title LIKE ? OR body LIKE ? OR id=?)"; args += [f"%{q}%", f"%{q}%", q]
    if label: sql += " AND id IN (SELECT item_id FROM item_tags WHERE tag=?)"; args.append(label)
    if cursor: sql += " AND id > ?"; args.append(cursor)
    sql += " ORDER BY id LIMIT ?"; args.append(min(int(limit), 200) + 1)
    rows = c.execute(sql, args).fetchall()
    more = len(rows) > int(limit)
    rows = rows[:int(limit)]
    return {"items": [item_json(c, r) for r in rows], "nextCursor": rows[-1]["id"] if more else None}

def item_detail(c, item_id):
    item = get_item(c, item_id)
    if not item: return None
    comments = [dict(r) for r in c.execute(
        "SELECT id, actor, text AS body, ts AS at FROM events WHERE item_id=? AND kind='comment' ORDER BY id", (item_id,))]
    history = [dict(r) for r in c.execute("SELECT from_status AS fromStatus, to_status AS toStatus, actor, source, at "
                                          "FROM status_history WHERE item_id=? ORDER BY id", (item_id,))]
    changes = [dict(r) for r in c.execute(
        "SELECT actor, text AS body, ts AS at FROM events WHERE item_id=? AND kind='change' ORDER BY id", (item_id,))]
    relations = [{"rel": r["relation"], "itemId": r["related_id"], "direction": "out"} for r in
                 c.execute("SELECT relation, related_id FROM relations WHERE item_id=?", (item_id,))] + \
                [{"rel": r["relation"], "itemId": r["item_id"], "direction": "in"} for r in
                 c.execute("SELECT relation, item_id FROM relations WHERE related_id=?", (item_id,))]
    links = [{"kind": r["kind"], "url": r["url"], "label": r["label"] or None} for r in
             c.execute("SELECT kind, url, label FROM links WHERE item_id=? ORDER BY id", (item_id,))]
    return {"item": item, "comments": comments, "statusHistory": history, "changes": changes,
            "relations": relations, "links": links, "githubLink": item["github"]}

def add_comment(c, item_id, actor, body):
    if not get_item(c, item_id): raise KeyError(item_id)
    if not (isinstance(body, str) and body.strip()): raise ValidationError("comment body required")
    t = now()
    cur = c.execute("INSERT INTO events(item_id,kind,actor,text,ts) VALUES(?,?,?,?,?)", (item_id, "comment", actor, body, t))
    return {"id": cur.lastrowid, "actor": actor, "body": body, "at": t}
