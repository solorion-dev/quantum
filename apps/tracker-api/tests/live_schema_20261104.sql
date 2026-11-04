CREATE TABLE embeddings (item_id TEXT PRIMARY KEY, model TEXT, dim INTEGER,
  vec BLOB, text_hash TEXT);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL,
  ts TEXT NOT NULL, actor TEXT DEFAULT 'cooper', kind TEXT NOT NULL, text TEXT DEFAULT '');
CREATE INDEX idx_items_kind ON items(kind);
CREATE INDEX idx_items_status ON items(status);
CREATE TABLE item_tags (item_id TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY (item_id, tag));
CREATE TABLE items (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'planned', priority TEXT NOT NULL DEFAULT 'none',
  assignee TEXT DEFAULT '', parent_id TEXT DEFAULT '', due_at TEXT DEFAULT '',
  points INTEGER, source TEXT DEFAULT 'manual', external_ref TEXT DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE links (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL,
  kind TEXT NOT NULL, url TEXT NOT NULL, label TEXT DEFAULT '');
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE people (handle TEXT PRIMARY KEY, name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'agent', matrix_id TEXT DEFAULT '', email TEXT DEFAULT '',
  github TEXT DEFAULT '', hub_worker TEXT DEFAULT '', notes TEXT DEFAULT '');
CREATE TABLE relations (item_id TEXT NOT NULL, related_id TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'related', PRIMARY KEY (item_id, related_id, relation));
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE tags (name TEXT PRIMARY KEY);
