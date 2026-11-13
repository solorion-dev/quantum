import Database from 'better-sqlite3';
import fs from 'node:fs';
import path from 'node:path';

export interface Migration {
  version: number;
  description: string;
  up: (db: Database.Database) => void;
}

const migrations: Migration[] = [
  {
    version: 1,
    description:
      'Command Board canonical store (TRK-0686): boards, items, subtasks, comments, activity, changes (sync log), schema_version. Mirrors the Muse Command Board Space model; space_id columns map rows to Space-side ids for sync (see SYNC.md).',
    up: (db: Database.Database) => {
      db.exec(`
        CREATE TABLE IF NOT EXISTS boards (
          id         TEXT PRIMARY KEY,
          name       TEXT NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 0,
          origin     TEXT NOT NULL DEFAULT 'app',
          space_id   TEXT NULL UNIQUE,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS items (
          id            TEXT PRIMARY KEY,
          board_id      TEXT NULL REFERENCES boards(id),
          column_id     TEXT NOT NULL DEFAULT 'inbox'
                        CHECK (column_id IN ('inbox','now','next','later','waiting','done')),
          kind          TEXT NOT NULL DEFAULT 'task' CHECK (kind IN ('task','idea')),
          title         TEXT NOT NULL,
          detail        TEXT NOT NULL DEFAULT '',
          priority      INTEGER NOT NULL DEFAULT 0,
          assignee      TEXT NOT NULL DEFAULT 'cooper' CHECK (assignee IN ('scotty','cooper')),
          checked       INTEGER NOT NULL DEFAULT 0,
          cooper_status TEXT NULL,
          trk_id        TEXT NULL,
          created_by    TEXT NOT NULL DEFAULT 'scotty',
          origin        TEXT NOT NULL DEFAULT 'app',
          space_id      TEXT NULL UNIQUE,
          rev           INTEGER NOT NULL DEFAULT 1,
          created_at    TEXT NOT NULL,
          updated_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subtasks (
          id         TEXT PRIMARY KEY,
          item_id    TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
          title      TEXT NOT NULL,
          checked    INTEGER NOT NULL DEFAULT 0,
          sort_order INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS comments (
          id         TEXT PRIMARY KEY,
          item_id    TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
          author     TEXT NOT NULL,
          body       TEXT NOT NULL,
          origin     TEXT NOT NULL DEFAULT 'app',
          space_id   TEXT NULL UNIQUE,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity (
          id         INTEGER PRIMARY KEY AUTOINCREMENT,
          item_id    TEXT NULL,
          actor      TEXT NOT NULL,
          text       TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS changes (
          seq       INTEGER PRIMARY KEY AUTOINCREMENT,
          entity    TEXT NOT NULL CHECK (entity IN ('board','item','comment','subtask','activity')),
          entity_id TEXT NOT NULL,
          op        TEXT NOT NULL CHECK (op IN ('upsert','delete')),
          origin    TEXT NOT NULL DEFAULT 'app',
          at        TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_items_board ON items(board_id, column_id);
        CREATE INDEX IF NOT EXISTS idx_comments_item ON comments(item_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_subtasks_item ON subtasks(item_id, sort_order);
        CREATE INDEX IF NOT EXISTS idx_changes_seq ON changes(seq);
      `);
    },
  },
];

export function getDatabasePath(): string {
  return process.env.BOARD_DB || './data/command-board.db';
}

export function getCurrentSchemaVersion(db: Database.Database): number {
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_version (
      version INTEGER PRIMARY KEY,
      applied_at TEXT NOT NULL,
      description TEXT
    );
  `);
  const row = db.prepare('SELECT MAX(version) as current_version FROM schema_version').get() as {
    current_version: number | null;
  };
  return row?.current_version ?? 0;
}

export function migrate(db: Database.Database): number {
  const currentVersion = getCurrentSchemaVersion(db);

  for (const m of migrations) {
    if (m.version > currentVersion) {
      const applyMigration = db.transaction(() => {
        m.up(db);
        db.prepare(
          'INSERT INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)'
        ).run(m.version, new Date().toISOString(), m.description);
      });
      applyMigration();
    }
  }

  return getCurrentSchemaVersion(db);
}

export function openDatabase(dbPath?: string): Database.Database {
  const resolvedPath = dbPath ?? getDatabasePath();

  if (resolvedPath !== ':memory:') {
    const dir = path.dirname(resolvedPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }

  const db = new Database(resolvedPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  migrate(db);

  return db;
}
