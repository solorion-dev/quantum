// Command Board service types (TRK-0686).
// The model mirrors the Muse "Command Board" Space exactly, so the Space
// and this app stay two doors onto one board (see SYNC.md).

export const COLUMNS = ['inbox', 'now', 'next', 'later', 'waiting', 'done'] as const;
export type ColumnId = (typeof COLUMNS)[number];

export type ItemKind = 'task' | 'idea';
export type Assignee = 'scotty' | 'cooper';
export type Origin = 'app' | 'space' | 'mcp' | 'seed';

export interface Board {
  id: string;
  name: string;
  sortOrder: number;
  origin: Origin;
  spaceId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Subtask {
  id: string;
  itemId: string;
  title: string;
  checked: boolean;
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
}

export interface BoardComment {
  id: string;
  itemId: string;
  author: string;
  body: string;
  origin: Origin;
  spaceId: string | null;
  createdAt: string;
}

export interface BoardItem {
  id: string;
  boardId: string | null;
  column: ColumnId;
  kind: ItemKind;
  title: string;
  detail: string;
  priority: boolean;
  assignee: Assignee;
  checked: boolean;
  cooperStatus: string | null;
  trkId: string | null;
  createdBy: string;
  origin: Origin;
  spaceId: string | null;
  rev: number;
  createdAt: string;
  updatedAt: string;
  subtasks: Subtask[];
  comments: BoardComment[];
}

export interface ActivityEntry {
  id: number;
  itemId: string | null;
  actor: string;
  text: string;
  createdAt: string;
}

export interface BoardState {
  boards: Board[];
  items: BoardItem[];
  activity: ActivityEntry[];
}

export interface ChangeRow {
  seq: number;
  entity: 'board' | 'item' | 'comment' | 'subtask' | 'activity';
  entityId: string;
  op: 'upsert' | 'delete';
  origin: Origin;
  at: string;
}

export interface HealthResponse {
  status: 'ok';
  schema_version: number;
  boards: number;
  items: number;
}
