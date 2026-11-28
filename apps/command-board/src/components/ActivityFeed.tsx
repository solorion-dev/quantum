import type { ActivityEntry } from '../types.js';

export default function ActivityFeed({ activity }: { activity: ActivityEntry[] }) {
  if (activity.length === 0) {
    return (
      <div className="bg-white border border-[#e5e7eb] rounded-2xl p-8 text-center text-[#6b7280] text-sm">
        No activity yet — captures, filings and Cooper updates will show up here.
      </div>
    );
  }
  return (
    <ol className="bg-white border border-[#e5e7eb] rounded-2xl divide-y divide-[#eef0f2]" data-testid="activity-feed">
      {activity.map((entry) => (
        <li key={entry.id} className="px-4 py-3 flex gap-3">
          <span
            className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${entry.actor === 'cooper' ? 'bg-[#7c5cff]' : 'bg-[#111827]'}`}
            aria-hidden
          />
          <div className="min-w-0">
            <p className="text-sm text-[#1f2937]">{entry.text}</p>
            <p className="text-xs text-[#9ca3af]">
              {entry.actor} · {new Date(entry.createdAt).toLocaleString()}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
