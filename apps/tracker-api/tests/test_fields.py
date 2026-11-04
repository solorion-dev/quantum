import json, sqlite3, unittest
from tracker_api import db
from tests.helpers import app, fresh

class PeopleDisplay(unittest.TestCase):
    def test_display_and_deprecated_name_alias(self):
        st, out = app().handle("GET", "/api/people", {}, {}, b"")
        self.assertEqual(st, 200)
        for p in out["people"]:
            self.assertIn("display", p); self.assertEqual(p["name"], p["display"])

class Project(unittest.TestCase):
    def setUp(self): self.c = fresh()
    def test_root_is_own_project(self):
        self.assertEqual(db.get_item(self.c, "TRK-9001")["project"]["id"], "TRK-9001")
    def test_child_and_grandchild_use_top_level(self):
        it = db.create_item(self.c, {"title": "grandchild", "parent_id": "TRK-9005"}, "human-x")
        p = it["project"]
        self.assertEqual((p["id"], p["derived"]), ("TRK-9001", True))
        self.assertEqual(p["title"], db.get_item(self.c, "TRK-9001")["title"])
    def test_cycle_and_missing_parent_terminate(self):
        self.c.execute("UPDATE items SET parent_id='TRK-9003' WHERE id='TRK-9002'")
        self.c.execute("UPDATE items SET parent_id='TRK-9002' WHERE id='TRK-9003'")
        self.assertIn(db.get_item(self.c, "TRK-9002")["project"]["id"], ("TRK-9002", "TRK-9003"))
        self.c.execute("UPDATE items SET parent_id='TRK-0404' WHERE id='TRK-9004'")
        self.assertEqual(db.get_item(self.c, "TRK-9004")["project"]["id"], "TRK-9004")
    def test_explicit_column_wins_and_proposed_002_applies(self):
        sql = open("migrations/002_project_column.sql").read()
        self.c.executescript(sql)
        self.assertEqual(self.c.execute("SELECT project FROM items WHERE id='TRK-9006'").fetchone()[0], "TRK-9001")
        self.c.execute("UPDATE items SET project='TRK-7777' WHERE id='TRK-9006'")
        self.assertEqual(db.get_item(self.c, "TRK-9006")["project"], {"id": "TRK-7777", "title": None, "derived": False})
    def test_live_schema_untouched(self):
        cols = [r[1] for r in self.c.execute("PRAGMA table_info(items)")]
        self.assertNotIn("project", cols)

class Automated(unittest.TestCase):
    def setUp(self):
        self.c = fresh()
        self.c.execute("INSERT INTO people(handle,name,kind) VALUES('scotty','Scotty','human')")
    def test_fixture_items_not_automated(self):
        self.assertFalse(db.get_item(self.c, "TRK-9001")["automated"])
    def test_human_created_not_automated(self):
        self.assertFalse(db.create_item(self.c, {"title": "h"}, "scotty")["automated"])
    def test_unknown_ui_actor_not_automated(self):
        self.assertFalse(db.create_item(self.c, {"title": "u"}, "board-ui")["automated"])
    def test_agent_via_ui_not_automated(self):
        self.assertFalse(db.create_item(self.c, {"title": "a"}, "pixel")["automated"])
    def test_agent_kind_with_unattended_source_automated(self):
        self.assertTrue(db.create_item(self.c, {"title": "a"}, "pixel", source="a2a")["automated"])
    def test_webhook_actor_created(self):
        self.assertTrue(db.create_item(self.c, {"title": "w"}, "webhook")["automated"])
    def test_sync_source_created(self):
        self.assertTrue(db.create_item(self.c, {"title": "s"}, "scotty", source="sync")["automated"])
    def test_a2a_actor_created(self):
        self.assertTrue(db.create_item(self.c, {"title": "x"}, "a2a")["automated"])
    def test_last_writer_agent_ui_not_automated(self):
        it = db.create_item(self.c, {"title": "h"}, "scotty")
        it, _ = db.update_item(self.c, it["id"], {"priority": "high"}, "pixel")
        self.assertFalse(it["automated"])
    def test_last_writer_sync_makes_automated(self):
        it = db.create_item(self.c, {"title": "h"}, "scotty")
        it, _ = db.update_item(self.c, it["id"], {"priority": "high"}, "github-sync", source="sync")
        self.assertTrue(it["automated"])
    def test_human_accepting_suggestion_is_human_write(self):
        it, _ = db.update_item(self.c, "TRK-9001", {"priority": "low"}, "scotty", source="github-suggest")
        self.assertFalse(it["automated"])

class RelationDirection(unittest.TestCase):
    def test_out_parent_means_parent_of(self):
        d = db.item_detail(fresh(), "TRK-9001")
        self.assertIn({"rel": "parent", "itemId": "TRK-9005", "direction": "out"}, d["relations"])
        d = db.item_detail(fresh(), "TRK-9005")
        self.assertIn({"rel": "parent", "itemId": "TRK-9001", "direction": "in"}, d["relations"])

if __name__ == "__main__": unittest.main()
