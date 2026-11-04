import datetime as dt, json, os, sqlite3, tempfile, unittest
from tracker_api import db
from tests.helpers import fresh, FIXTURE

class Migrations(unittest.TestCase):
    def test_idempotent(self):
        c = fresh(); self.assertEqual(db.migrate(c), [])

    def test_additive_on_legacy_db(self):
        # A DB shaped like today's live tracker (base tables, existing rows) keeps every row and column.
        c = db.connect(":memory:"); name, sql = db.MIGRATIONS[0]
        for s in [x for x in sql.split(";") if x.strip()]: c.execute(s)
        c.execute("INSERT INTO people(handle, name, github) VALUES('cooper','Cooper','fake-login')")
        c.execute("INSERT INTO items(id,kind,title,assignee,created_at,updated_at) VALUES('TRK-0001','task','old','cooper','2026-10-18T05:00:00','2026-10-18T05:00:00')")
        c.execute("INSERT INTO items(id,kind,title,created_at,updated_at) VALUES('TRK-0002','task','unassigned','2026-10-18T05:00:00','2026-10-18T05:00:00')")
        c.execute("INSERT INTO item_tags VALUES('TRK-0001','legacy')")
        before = {r[1] for r in c.execute("PRAGMA table_info(items)")}
        c.execute("CREATE TABLE schema_migrations(name TEXT PRIMARY KEY, at TEXT NOT NULL)")
        c.execute("INSERT INTO schema_migrations VALUES('001_base','t')")
        self.assertEqual(db.migrate(c), ["002_people_link", "003_labels_history", "004_github_sync"])
        after = {r[1] for r in c.execute("PRAGMA table_info(items)")}
        self.assertTrue(before <= after)
        r = c.execute("SELECT * FROM items WHERE id='TRK-0001'").fetchone()
        self.assertEqual((r["title"], r["assignee"], r["assignee_id"]), ("old", "cooper", "cooper"))
        self.assertEqual(db.labels_of(c, "TRK-0001"), ["legacy"])
        self.assertEqual(db.get_item(c, "TRK-0002")["assigneeId"], None)          # live '' -> null
        self.assertEqual(db.get_item(c, "TRK-0002")["parentId"], None)
        self.assertIn("legacy", [r[0] for r in c.execute("SELECT name FROM tags")])

    def test_001_matches_live_schema_exactly(self):
        norm = lambda s: " ".join(s.replace("IF NOT EXISTS ", "").split()).rstrip(";")
        live_path = os.path.join(os.path.dirname(__file__), "live_schema_20261104.sql")
        live = sorted(norm(x) for x in open(live_path).read().split(";\n") if x.strip())
        c = db.connect(":memory:")
        for s in [x for x in db.MIGRATIONS[0][1].split(";") if x.strip()]: c.execute(s)
        ours = sorted(norm(r[0]) for r in c.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
        self.assertEqual(ours, live)

    def test_no_drop_or_destructive_sql(self):
        for _, sql in db.MIGRATIONS[1:]:
            for bad in ("DROP ", "DELETE ", "RENAME"):
                self.assertNotIn(bad, sql.upper())

    def test_refuses_live_db(self):
        with self.assertRaises(RuntimeError): db.connect("/mnt/fast/tracker/tracker.db")

class Items(unittest.TestCase):
    def setUp(self): self.c = fresh()

    def test_seed_count(self):
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM items").fetchone()[0], 20)

    def test_create_assigns_next_id(self):
        it = db.create_item(self.c, {"title": "New", "labels": ["ui"]}, "pixel")
        self.assertEqual(it["id"], "TRK-9021"); self.assertEqual(it["labels"], ["ui"])

    def test_update_field_clock_and_history(self):
        it, changed = db.update_item(self.c, "TRK-9001", {"status": "in_progress", "title": "x"}, "volt")
        self.assertEqual(sorted(changed), ["status", "title"])
        clock = json.loads(self.c.execute("SELECT field_clock FROM items WHERE id='TRK-9001'").fetchone()[0])
        self.assertEqual(clock["status"]["writer"], "volt"); self.assertEqual(clock["title"]["source"], "ui")
        self.assertNotIn("priority", clock)
        h = self.c.execute("SELECT from_status, to_status FROM status_history WHERE item_id='TRK-9001' ORDER BY id").fetchall()
        self.assertEqual(tuple(h[-1]), ("backlog", "in_progress"))

    def test_noop_update_writes_nothing(self):
        before = self.c.execute("SELECT updated_at FROM items WHERE id='TRK-9001'").fetchone()[0]
        _, changed = db.update_item(self.c, "TRK-9001", {"status": "backlog"}, "volt")
        self.assertEqual(changed, [])
        self.assertEqual(self.c.execute("SELECT updated_at FROM items WHERE id='TRK-9001'").fetchone()[0], before)

    def test_validation(self):
        for bad in ({"status": "nope"}, {"priority": "urgent"}, {"assignee_id": "stranger"}, {"created_at": "x"},
                    {"title": " "}):
            with self.assertRaises(db.ValidationError): db.update_item(self.c, "TRK-9001", bad, "volt")

    def test_flags(self):
        ref = dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc)
        row = lambda i: self.c.execute("SELECT * FROM items WHERE id=?", (i,)).fetchone()
        self.assertTrue(db.flags(self.c, row("TRK-9003"), ref)["stale"])     # Oct 5, in_progress
        self.assertFalse(db.flags(self.c, row("TRK-9014"), ref)["stale"])    # Oct 5 but cancelled
        self.assertFalse(db.flags(self.c, row("TRK-9002"), ref)["stale"])    # recent
        self.assertTrue(db.flags(self.c, row("TRK-9006"), ref)["needsTriage"])   # no assignee
        self.assertTrue(db.flags(self.c, row("TRK-9005"), ref)["needsTriage"])   # priority none
        self.assertTrue(db.flags(self.c, row("TRK-9008"), ref)["needsTriage"])   # backlog, no labels
        self.assertFalse(db.flags(self.c, row("TRK-9002"), ref)["needsTriage"])

    def test_list_filters_and_cursor(self):
        page = db.list_items(self.c, limit=5); self.assertEqual(len(page["items"]), 5)
        self.assertEqual(page["nextCursor"], "TRK-9005")
        self.assertTrue(all(i["status"] == "done" for i in db.list_items(self.c, status="done")["items"]))
        self.assertTrue(all("db" in i["labels"] for i in db.list_items(self.c, label="db")["items"]))

    def test_detail_payload(self):
        d = db.item_detail(self.c, "TRK-9001")
        self.assertEqual(set(d), {"item", "comments", "statusHistory", "changes", "relations", "links", "githubLink"})
        self.assertEqual({r["itemId"] for r in d["relations"]}, {"TRK-9005", "TRK-9006", "TRK-9007"})
        self.assertEqual(d["githubLink"]["repo"], "solorion-dev/sandbox")
        self.assertEqual(len(db.item_detail(self.c, "TRK-9002")["comments"]), 1)

if __name__ == "__main__": unittest.main()
