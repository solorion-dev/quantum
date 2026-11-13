import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api/client.js';
import Header from './components/Header.js';
import QuickCapture from './components/QuickCapture.js';
import ItemCard from './components/ItemCard.js';
import ItemDetail from './components/ItemDetail.js';
import ActivityFeed from './components/ActivityFeed.js';
import EmptyState from './components/EmptyState.js';
import type { BoardItem, BoardState, ColumnId } from './types.js';
import { COLUMN_LABELS } from './types.js';

const BOARD_COLUMNS: ColumnId[] = ['now', 'next', 'later', 'waiting', 'done'];
const POLL_MS = 20000;

export default function App() {
  const [state, setState] = useState<BoardState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [actor, setActor] = useState<'scotty' | 'cooper'>(() =>
    typeof localStorage !== 'undefined' && localStorage.getItem('cb-actor') === 'cooper' ? 'cooper' : 'scotty'
  );
  const [view, setView] = useState<'board' | 'activity'>('board');
  const [layout, setLayout] = useState<'kanban' | 'list'>('kanban');
  const [selectedBoardId, setSelectedBoardId] = useState<string>('inbox');
  const [openItemId, setOpenItemId] = useState<string | null>(null);
  const [newBoardName, setNewBoardName] = useState('');
  const selectedRef = useRef<string>('inbox');
  selectedRef.current = selectedBoardId;

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const next = await api.getState();
      setState(next);
      setError(null);
      // Keep the current tab if it still exists (boards can be deleted).
      const sel = selectedRef.current;
      if (sel !== 'inbox' && !next.boards.some((b) => b.id === sel)) {
        setSelectedBoardId('inbox');
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? `Could not reach the Command Board service (${err.message}). Is services/command-board running on :8798?`
          : 'Could not reach the Command Board service.'
      );
    } finally {
      if (!quiet) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(true), POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    api.setActor(actor);
    try {
      localStorage.setItem('cb-actor', actor);
    } catch {
      // non-fatal
    }
  }, [actor]);

  const counts = useMemo(() => {
    const items = state?.items ?? [];
    return {
      inbox: items.filter((i) => i.column === 'inbox' && !i.checked).length,
      now: items.filter((i) => i.column === 'now' && !i.checked).length,
      waiting: items.filter((i) => i.column === 'waiting' && i.assignee === 'scotty' && !i.checked).length,
      done: items.filter((i) => i.column === 'done' || i.checked).length,
    };
  }, [state]);

  const openItem = state?.items.find((i) => i.id === openItemId) ?? null;

  const after = async (fn: () => Promise<unknown>) => {
    await fn();
    await refresh(true);
  };

  const handleCapture = async (input: { title: string; kind: 'task' | 'idea'; priority: boolean }) => {
    await after(() =>
      api.createItem({ title: input.title, kind: input.kind, priority: input.priority, createdBy: actor, assignee: 'cooper' })
    );
    setSelectedBoardId('inbox');
    setView('board');
  };

  const boardItems = useMemo(() => {
    if (!state) return [];
    if (selectedBoardId === 'inbox') return state.items.filter((i) => i.boardId === null || i.column === 'inbox');
    return state.items.filter((i) => i.boardId === selectedBoardId);
  }, [state, selectedBoardId]);

  return (
    <div className="min-h-screen bg-[#f8f9fa]">
      <Header
        inboxCount={counts.inbox}
        nowCount={counts.now}
        waitingCount={counts.waiting}
        doneCount={counts.done}
        actor={actor}
        onActorChange={setActor}
        view={view}
        onViewChange={setView}
        onRefresh={() => void refresh()}
        refreshing={refreshing}
      />

      <main className="max-w-[1440px] mx-auto px-4 py-4 space-y-4">
        <QuickCapture onCapture={handleCapture} />

        {error && (
          <div className="bg-[#fef2f2] border border-[#fecaca] text-[#991b1b] rounded-xl px-4 py-3 text-sm" role="alert">
            {error}
          </div>
        )}

        {view === 'activity' ? (
          <ActivityFeed activity={state?.activity ?? []} />
        ) : (
          <>
            <div className="flex items-center gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Boards">
              <button
                role="tab"
                aria-selected={selectedBoardId === 'inbox'}
                onClick={() => setSelectedBoardId('inbox')}
                className={`shrink-0 px-3.5 py-2 rounded-full text-sm font-medium border ${
                  selectedBoardId === 'inbox'
                    ? 'bg-[#111827] text-white border-[#111827]'
                    : 'bg-white text-[#374151] border-[#e5e7eb]'
                }`}
              >
                📥 Inbox{counts.inbox > 0 ? ` (${counts.inbox})` : ''}
              </button>
              {(state?.boards ?? []).map((b) => (
                <button
                  key={b.id}
                  role="tab"
                  aria-selected={selectedBoardId === b.id}
                  onClick={() => setSelectedBoardId(b.id)}
                  className={`shrink-0 px-3.5 py-2 rounded-full text-sm font-medium border ${
                    selectedBoardId === b.id
                      ? 'bg-[#111827] text-white border-[#111827]'
                      : 'bg-white text-[#374151] border-[#e5e7eb]'
                  }`}
                >
                  {b.name}
                </button>
              ))}
              <div className="shrink-0 flex items-center gap-1 ml-1">
                <input
                  value={newBoardName}
                  onChange={(e) => setNewBoardName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newBoardName.trim()) {
                      void (async () => {
                        const board = await api.createBoard(newBoardName.trim());
                        setNewBoardName('');
                        await refresh(true);
                        setSelectedBoardId(board.id);
                      })();
                    }
                  }}
                  placeholder="New board…"
                  className="w-32 border border-dashed border-[#d1d5db] rounded-full px-3 py-2 text-sm bg-transparent"
                  aria-label="New board name"
                />
                <button
                  className="px-3 py-2 rounded-full border border-[#d1d5db] bg-white text-sm disabled:opacity-40"
                  disabled={!newBoardName.trim()}
                  onClick={() =>
                    void (async () => {
                      const board = await api.createBoard(newBoardName.trim());
                      setNewBoardName('');
                      await refresh(true);
                      setSelectedBoardId(board.id);
                    })()
                  }
                >
                  + Board
                </button>
              </div>
              {selectedBoardId !== 'inbox' && (
                <div className="ml-auto shrink-0 flex bg-[#f1f3f5] rounded-full p-1" role="group" aria-label="Layout">
                  <button
                    className={`px-3 py-1 rounded-full text-xs font-medium ${layout === 'kanban' ? 'bg-[#111827] text-white' : 'text-[#4b5563]'}`}
                    onClick={() => setLayout('kanban')}
                  >
                    Kanban
                  </button>
                  <button
                    className={`px-3 py-1 rounded-full text-xs font-medium ${layout === 'list' ? 'bg-[#111827] text-white' : 'text-[#4b5563]'}`}
                    onClick={() => setLayout('list')}
                  >
                    List
                  </button>
                </div>
              )}
            </div>

            {!state ? (
              <p className="text-sm text-[#6b7280] py-8 text-center">Loading the board…</p>
            ) : selectedBoardId === 'inbox' ? (
              <section aria-label="Inbox" className="space-y-2 max-w-3xl">
                {boardItems.length === 0 ? (
                  <EmptyState title="Inbox zero." hint="New captures land here; Cooper files them onto boards." />
                ) : (
                  boardItems.map((item) => (
                    <ItemCard
                      key={item.id}
                      item={item}
                      onOpen={(i) => setOpenItemId(i.id)}
                      onToggleChecked={(i) => void after(() => api.updateItem(i.id, { checked: !i.checked }))}
                      onMove={(i, col) => void after(() => api.updateItem(i.id, { column: col }))}
                    />
                  ))
                )}
              </section>
            ) : layout === 'list' ? (
              <section aria-label="Board list" className="space-y-2 max-w-3xl">
                {boardItems.length === 0 ? (
                  <EmptyState title="Nothing on this board yet." hint="File an Inbox capture here from its detail view." />
                ) : (
                  boardItems.map((item) => (
                    <ItemCard
                      key={item.id}
                      item={item}
                      onOpen={(i) => setOpenItemId(i.id)}
                      onToggleChecked={(i) => void after(() => api.updateItem(i.id, { checked: !i.checked }))}
                      onMove={(i, col) => void after(() => api.updateItem(i.id, { column: col }))}
                    />
                  ))
                )}
              </section>
            ) : (
              <section aria-label="Board kanban" className="flex gap-3 overflow-x-auto pb-2 items-start">
                {BOARD_COLUMNS.map((col) => {
                  const colItems = boardItems.filter((i) => i.column === col);
                  return (
                    <div key={col} className="w-[280px] shrink-0 bg-[#f1f3f5]/60 border border-[#e5e7eb] rounded-2xl p-2.5">
                      <h2 className="text-xs font-semibold uppercase tracking-wide text-[#6b7280] px-1 pb-2 flex justify-between">
                        <span>{COLUMN_LABELS[col]}</span>
                        <span>{colItems.length}</span>
                      </h2>
                      <div className="space-y-2">
                        {colItems.length === 0 ? (
                          <EmptyState title="Empty" />
                        ) : (
                          colItems.map((item) => (
                            <ItemCard
                              key={item.id}
                              item={item}
                              onOpen={(i) => setOpenItemId(i.id)}
                              onToggleChecked={(i) => void after(() => api.updateItem(i.id, { checked: !i.checked }))}
                              onMove={(i, c) => void after(() => api.updateItem(i.id, { column: c }))}
                            />
                          ))
                        )}
                      </div>
                    </div>
                  );
                })}
              </section>
            )}
          </>
        )}
      </main>

      {openItem && state && (
        <ItemDetail
          item={openItem}
          boards={state.boards}
          actor={actor}
          onClose={() => setOpenItemId(null)}
          onUpdate={async (item, patch) => {
            await after(() => api.updateItem(item.id, patch as any));
          }}
          onComment={async (item, body) => {
            await after(() => api.addComment(item.id, actor, body));
          }}
          onAddSubtask={async (item, title) => {
            await after(() => api.addSubtask(item.id, title));
          }}
          onToggleSubtask={async (_item, subtaskId, checked) => {
            await after(() => api.updateSubtask(subtaskId, { checked }));
          }}
          onDelete={async (item) => {
            await after(() => api.deleteItem(item.id));
            setOpenItemId(null);
          }}
        />
      )}
    </div>
  );
}
