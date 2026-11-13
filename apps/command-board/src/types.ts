// Command Board UI types — mirror services/command-board/src/types.ts.

export const COLUMNS = ['inbox', 'now', 'next', 'later', 'waiting', 'done'] as const;
export type ColumnId = (typeof COLUMNS)[number];

export const COLUMN_LABELS: Record<ColumnId, string> = {
  inbox: 'Inbox',
  now: 'Now',
  next: 'Next',
  later: 'Later',
  waiting: 'Waiting',
  done: 'Done',
};

export type ItemKind = 'task' | 'idea';
export type Assignee = 'scotty' | 'cooper';

export interface Board {
  id: string;
  name: string;
  sortOrder: number;
  origin: string;
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
  origin: string;
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
  origin: string;
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

export interface CreateItemInput {
  title: string;
  detail?: string;
  kind?: ItemKind;
  boardId?: string | null;
  column?: ColumnId;
  priority?: boolean;
  assignee?: Assignee;
  createdBy?: string;
}

export interface UpdateItemInput {
  title?: string;
  detail?: string;
  kind?: ItemKind;
  boardId?: string | null;
  column?: ColumnId;
  priority?: boolean;
  assignee?: Assignee;
  checked?: boolean;
  cooperStatus?: string | null;
  trkId?: string | null;
}
