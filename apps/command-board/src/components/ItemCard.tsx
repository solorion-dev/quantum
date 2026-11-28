import type { BoardItem, ColumnId } from '../types.js';
import { COLUMNS, COLUMN_LABELS } from '../types.js';

interface ItemCardProps {
  item: BoardItem;
  onOpen: (item: BoardItem) => void;
  onToggleChecked: (item: BoardItem) => void;
  onMove: (item: BoardItem, column: ColumnId) => void;
}

export default function ItemCard({ item, onOpen, onToggleChecked, onMove }: ItemCardProps) {
  const subtaskDone = item.subtasks.filter((s) => s.checked).length;
  return (
    <article
      data-testid="item-card"
      className="bg-white border border-[#e5e7eb] rounded-xl p-3 shadow-sm hover:border-[#d1d5db] transition-colors"
    >
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={item.checked}
          onChange={() => onToggleChecked(item)}
          className="mt-1 w-4 h-4 accent-[#111827]"
          aria-label={`Check off: ${item.title}`}
        />
        <button className="flex-1 text-left" onClick={() => onOpen(item)}>
          <h3 className={`text-sm font-medium leading-snug ${item.checked ? 'line-through text-[#9ca3af]' : 'text-[#111827]'}`}>
            {item.priority && <span className="text-[#d97706] mr-1" title="Priority">⚑</span>}
            {item.title}
          </h3>
        </button>
        <span
          className={`shrink-0 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
            item.kind === 'idea' ? 'bg-[#f3f0ff] text-[#6342e6]' : 'bg-[#f1f3f5] text-[#4b5563]'
          }`}
        >
          {item.kind}
        </span>
      </div>

      {item.cooperStatus && (
        <p className="mt-2 text-xs text-[#4b5563] bg-[#f8f9fa] border border-[#eef0f2] rounded-lg px-2 py-1.5">
          <span className="font-semibold text-[#6342e6]">Cooper:</span> {item.cooperStatus}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[#6b7280]">
        <span>{item.assignee === 'scotty' ? 'Scotty' : 'Cooper'}</span>
        {item.trkId && (
          <span className="font-mono bg-[#f3f0ff] text-[#6342e6] px-1.5 py-0.5 rounded">{item.trkId}</span>
        )}
        {item.subtasks.length > 0 && (
          <span>☑ {subtaskDone}/{item.subtasks.length}</span>
        )}
        {item.comments.length > 0 && <span>💬 {item.comments.length}</span>}
        <label className="ml-auto flex items-center gap-1">
          <span className="sr-only">Move {item.title}</span>
          <select
            value={item.column}
            onChange={(e) => onMove(item, e.target.value as ColumnId)}
            className="border border-[#e5e7eb] rounded-md px-1 py-0.5 bg-white text-xs text-[#4b5563]"
            aria-label="Move to column"
          >
            {COLUMNS.filter((c) => item.boardId !== null || c === 'inbox').map((c) => (
              <option key={c} value={c}>
                {COLUMN_LABELS[c]}
              </option>
            ))}
          </select>
        </label>
      </div>
    </article>
  );
}
