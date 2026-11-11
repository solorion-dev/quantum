#!/usr/bin/env python3
"""Dev-data snapshot for the tracker-board React app.

Runs ON Tritium (or anywhere the Tracker DB lives) and prints a JSON board
snapshot to stdout, using the exact queries board_server.py uses for its
list view (fetch_rows) and project hubs (fetch_projects: goal items joined
by undirected 'project' relations).

Why this exists: the stopgap board service exposes NO JSON list endpoint —
the board list is server-rendered HTML only. Until P5 (TRK-0273) ships a
real GET /api/board, the React app develops against this snapshot for the
list, while item detail + edits go through the live /api/item endpoints.

Usage (from the dev machine, over the SSH tunnel):
  ssh scott@tritium-linux 'python3 snapshot-board.py' > public/board-data.json
"""
import json
import re
import sqlite3
from datetime import datetime, timezone

DB = "/mnt/fast/tracker/tracker.db"


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s or "project"


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    items = [
        dict(r)
        for r in con.execute(
            "select id, kind, title, status, priority, assignee, due_at,"
            " points, updated_at from items"
        )
    ]
    goals = {
        r["id"]: r["title"]
        for r in con.execute("select id, title from items where kind='goal'")
    }
    edges = con.execute(
        "select item_id, related_id from relations where relation='project'"
    ).fetchall()
    con.close()
    members = {}
    for e in edges:
        for hub, other in (
            (e["item_id"], e["related_id"]),
            (e["related_id"], e["item_id"]),
        ):
            if hub in goals:
                members.setdefault(hub, set()).add(other)
    projects = []
    for hub, title in goals.items():
        if hub not in members:
            continue
        ids = set(members[hub])
        ids.add(hub)
        projects.append(
            {
                "id": hub,
                "title": title,
                "slug": slugify(title),
                "member_ids": sorted(ids),
            }
        )
    projects.sort(key=lambda p: p["title"].lower())
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": items,
        "projects": projects,
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
