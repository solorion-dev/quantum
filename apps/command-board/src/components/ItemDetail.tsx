import { useEffect, useState } from 'react';
import type { Board, BoardItem, ColumnId } from '../types.js';
import { COLUMNS, COLUMN_LABELS } from '../types.js';

interface ItemDetailProps {
  item: BoardItem;
  boards: Board[];
  actor: 'scotty' | 'cooper';
  onClose: () => void;
  onUpdate: (item: BoardItem, patch: Record<string, unknown>) => Promise<void>;
  onComment: (item: BoardItem, body: string) => Promise<void>;
  onAddSubtask: (item: BoardItem, title: string) => Promise<void>;
  onToggleSubtask: (item: BoardItem, subtaskId: string, checked: boolean) => Promise<void>;
  onDelete: (item: BoardItem) => Promise<void>;
}

export default function ItemDetail({
  item,
  boards,
  actor,
  onClose,
  onUpdate,
  onComment,
  onAddSubtask,
  onToggleSubtask,
  onDelete,
}: ItemDetailProps) {
  const [title, setTitle] = useState(item.title);
  const [detail, setDetail] = useState(item.detail);
  const [comment, setComment] = useState('');
  const [subtaskTitle, setSubtaskTitle] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(item.title);
    setDetail(item.detail);
  }, [item.id, item.title, item.detail]);

  const guard = async (fn: () => Promise<void>) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    }
  };

  const selectCls = 'border border-[#d1d5db] rounded-lg px-2 py-1.5 bg-white text-sm text-[#111827]';
  const labelCls = 'block text-xs font-semibold uppercase tracking-wide text-[#6b7280] mb-1';

  return (
    <div className="fixed inset-0 z-30 bg-black/40 flex items-end sm:items-center justify-center p-0 sm:p-6" role="dialog" aria-modal="true" aria-label={item.title}>
      <div className="bg-white w-full max-w-2xl max-h-[92vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl shadow-xl">
        <div className="sticky top-0 bg-white border-b border-[#e5e7eb] px-4 py-3 flex items-center gap-2">
          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${item.kind === 'idea' ? 'bg-[#f3f0ff] text-[#6342e6]' : 'bg-[#f1f3f5] text-[#4b5563]'}`}>
            {item.kind}
          </span>
          {item.trkId && <span className="font-mono text-xs bg-[#f3f0ff] text-[#6342e6] px-2 py-0.5 rounded-full">{item.trkId}</span>}
          <span className="text-xs text-[#9ca3af] ml-auto">rev {item.rev} · {new Date(item.updatedAt).toLocaleString()}</span>
          <button onClick={onClose} className="px-2 py-1 rounded-lg border border-[#d1d5db] text-sm" aria-label="Close detail">
            ✕
          </button>
        </div>

        <div className="px-4 py-4 space-y-4">
          {error && <p className="text-sm text-[#dc2626] bg-[#fef2f2] border border-[#fecaca] rounded-lg px-3 py-2">{error}</p>}

          <div>
            <label className={labelCls} htmlFor="detail-title">Title</label>
            <div className="flex gap-2">
              <input
                id="detail-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="flex-1 border border-[#d1d5db] rounded-xl px-3 py-2 text-[15px]"
              />
              <button
                className="px-3 py-2 rounded-xl bg-[#111827] text-white text-sm font-semibold disabled:opacity-40"
                disabled={title.trim() === item.title || !title.trim()}
                onClick={() => void guard(() => onUpdate(item, { title: title.trim() }))}
              >
                Save
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className={labelCls}>Board</label>
              <select
                className={selectCls + ' w-full'}
                value={item.boardId ?? ''}
                onChange={(e) =>
                  void guard(() =>
                    onUpdate(item, {
                      boardId: e.target.value || null,
                      column: e.target.value ? (item.column === 'inbox' ? 'now' : item.column) : 'inbox',
                    })
                  )
                }
              >
                <option value="">Inbox (unfiled)</option>
                {boards.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls}>Column</label>
              <select
                className={selectCls + ' w-full'}
                value={item.column}
                onChange={(e) => void guard(() => onUpdate(item, { column: e.target.value as ColumnId }))}
              >
                {COLUMNS.map((c) => (
                  <option key={c} value={c}>
                    {COLUMN_LABELS[c]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls}>Assignee</label>
              <select
                className={selectCls + ' w-full'}
                value={item.assignee}
                onChange={(e) => void guard(() => onUpdate(item, { assignee: e.target.value }))}
              >
                <option value="scotty">Scotty</option>
                <option value="cooper">Cooper</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Priority</label>
              <button
                className={`w-full px-2 py-1.5 rounded-lg border text-sm font-medium ${item.priority ? 'border-[#d97706] bg-[#fffbeb] text-[#d97706]' : 'border-[#d1d5db] text-[#4b5563]'}`}
                onClick={() => void guard(() => onUpdate(item, { priority: !item.priority }))}
              >
                {item.priority ? '⚑ Priority' : 'Not flagged'}
              </button>
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-[#374151]">
            <input
              type="checkbox"
              checked={item.checked}
              onChange={(e) => void guard(() => onUpdate(item, { checked: e.target.checked }))}
              className="w-4 h-4 accent-[#111827]"
            />
            Checked off (done)
          </label>

          {item.cooperStatus && (
            <div className="bg-[#f8f9fa] border border-[#e5e7eb] rounded-xl px-3 py-2.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#6342e6] mb-0.5">Cooper status</p>
              <p className="text-sm text-[#374151]">{item.cooperStatus}</p>
            </div>
          )}

          <div>
            <label className={labelCls} htmlFor="detail-notes">Notes</label>
            <textarea
              id="detail-notes"
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
              rows={3}
              className="w-full border border-[#d1d5db] rounded-xl px-3 py-2 text-sm"
              placeholder="Detail, links, context…"
            />
            <button
              className="mt-1.5 px-3 py-1.5 rounded-lg border border-[#d1d5db] text-sm disabled:opacity-40"
              disabled={detail === item.detail}
              onClick={() => void guard(() => onUpdate(item, { detail }))}
            >
              Save notes
            </button>
          </div>

          <div>
            <p className={labelCls}>Subtasks</p>
            <ul className="space-y-1.5">
              {item.subtasks.map((s) => (
                <li key={s.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={s.checked}
                    onChange={(e) => void guard(() => onToggleSubtask(item, s.id, e.target.checked))}
                    className="w-4 h-4 accent-[#111827]"
                  />
                  <span className={s.checked ? 'line-through text-[#9ca3af]' : 'text-[#111827]'}>{s.title}</span>
                </li>
              ))}
              {item.subtasks.length === 0 && <li className="text-sm text-[#9ca3af]">No subtasks yet.</li>}
            </ul>
            <div className="flex gap-2 mt-2">
              <input
                value={subtaskTitle}
                onChange={(e) => setSubtaskTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && subtaskTitle.trim()) {
                    void guard(async () => {
                      await onAddSubtask(item, subtaskTitle.trim());
                      setSubtaskTitle('');
                    });
                  }
                }}
                placeholder="Add a subtask…"
                className="flex-1 border border-[#d1d5db] rounded-lg px-2.5 py-1.5 text-sm"
              />
              <button
                className="px-3 py-1.5 rounded-lg bg-[#111827] text-white text-sm font-semibold disabled:opacity-40"
                disabled={!subtaskTitle.trim()}
                onClick={() =>
                  void guard(async () => {
                    await onAddSubtask(item, subtaskTitle.trim());
                    setSubtaskTitle('');
                  })
                }
              >
                Add
              </button>
            </div>
          </div>

          <div>
            <p className={labelCls}>Comments</p>
            <ul className="space-y-3">
              {item.comments.map((c) => (
                <li key={c.id} className="bg-[#f8f9fa] border border-[#eef0f2] rounded-xl px-3 py-2.5">
                  <p className="text-xs text-[#6b7280] mb-1">
                    <span className={`font-semibold ${c.author === 'cooper' ? 'text-[#6342e6]' : 'text-[#111827]'}`}>
                      {c.author === 'cooper' ? 'Cooper' : c.author === 'scotty' ? 'Scotty' : c.author}
                    </span>{' '}
                    · {new Date(c.createdAt).toLocaleString()}
                  </p>
                  <p className="text-sm text-[#1f2937] whitespace-pre-wrap">{c.body}</p>
                </li>
              ))}
              {item.comments.length === 0 && <li className="text-sm text-[#9ca3af]">No comments yet.</li>}
            </ul>
            <div className="flex gap-2 mt-3">
              <input
                data-testid="comment-input"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && comment.trim()) {
                    void guard(async () => {
                      await onComment(item, comment.trim());
                      setComment('');
                    });
                  }
                }}
                placeholder={`Comment as ${actor === 'cooper' ? 'Cooper' : 'Scotty'}…`}
                className="flex-1 border border-[#d1d5db] rounded-lg px-2.5 py-2 text-sm"
              />
              <button
                data-testid="comment-send"
                className="px-3 py-2 rounded-lg bg-[#111827] text-white text-sm font-semibold disabled:opacity-40"
                disabled={!comment.trim()}
                onClick={() =>
                  void guard(async () => {
                    await onComment(item, comment.trim());
                    setComment('');
                  })
                }
              >
                Send
              </button>
            </div>
          </div>

          <div className="pt-2 border-t border-[#e5e7eb] flex items-center justify-between">
            <p className="text-xs text-[#9ca3af]">Created by {item.createdBy} · {new Date(item.createdAt).toLocaleString()}</p>
            <button
              className="px-3 py-1.5 rounded-lg border border-[#fecaca] text-[#dc2626] text-sm"
              onClick={() => {
                if (window.confirm('Delete this item? This cannot be undone.')) {
                  void guard(() => onDelete(item));
                }
              }}
            >
              Delete item
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
