interface HeaderProps {
  inboxCount: number;
  nowCount: number;
  waitingCount: number;
  doneCount: number;
  actor: 'scotty' | 'cooper';
  onActorChange: (actor: 'scotty' | 'cooper') => void;
  view: 'board' | 'activity';
  onViewChange: (view: 'board' | 'activity') => void;
  onRefresh: () => void;
  refreshing: boolean;
}

export default function Header({
  inboxCount,
  nowCount,
  waitingCount,
  doneCount,
  actor,
  onActorChange,
  view,
  onViewChange,
  onRefresh,
  refreshing,
}: HeaderProps) {
  return (
    <header className="bg-white border-b border-[#e5e7eb] sticky top-0 z-20">
      <div className="max-w-[1440px] mx-auto px-4 py-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-3 mr-auto">
          <div className="w-9 h-9 rounded-xl bg-[#111827] text-white grid place-items-center font-bold text-lg select-none">
            ✓
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-tight text-[#111827]">Command Board</h1>
            <p className="text-xs text-[#6b7280] leading-tight">
              Inbox {inboxCount} · In progress {nowCount} · Waiting on Scotty {waitingCount} · Done {doneCount}
            </p>
          </div>
        </div>

        <nav className="flex items-center gap-1 bg-[#f1f3f5] rounded-full p-1" aria-label="View">
          <button
            className={`px-3 py-1.5 rounded-full text-sm font-medium ${view === 'board' ? 'bg-[#111827] text-white' : 'text-[#4b5563]'}`}
            onClick={() => onViewChange('board')}
          >
            Board
          </button>
          <button
            className={`px-3 py-1.5 rounded-full text-sm font-medium ${view === 'activity' ? 'bg-[#111827] text-white' : 'text-[#4b5563]'}`}
            onClick={() => onViewChange('activity')}
          >
            Activity
          </button>
        </nav>

        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="px-3 py-1.5 rounded-full border border-[#d1d5db] text-sm text-[#374151] bg-white disabled:opacity-50"
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>

        <label className="flex items-center gap-2 text-sm text-[#4b5563]">
          <span className="hidden sm:inline">Acting as</span>
          <select
            value={actor}
            onChange={(e) => onActorChange(e.target.value as 'scotty' | 'cooper')}
            className="border border-[#d1d5db] rounded-lg px-2 py-1.5 bg-white text-[#111827]"
            aria-label="Acting user (Solorion login seam)"
          >
            <option value="scotty">Scotty</option>
            <option value="cooper">Cooper</option>
          </select>
        </label>
      </div>
    </header>
  );
}
