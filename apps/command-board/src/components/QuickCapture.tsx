import { useState } from 'react';
import type { ItemKind } from '../types.js';

interface QuickCaptureProps {
  onCapture: (input: { title: string; kind: ItemKind; priority: boolean }) => Promise<void>;
}

export default function QuickCapture({ onCapture }: QuickCaptureProps) {
  const [title, setTitle] = useState('');
  const [kind, setKind] = useState<ItemKind>('task');
  const [priority, setPriority] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const clean = title.trim();
    if (!clean || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onCapture({ title: clean, kind, priority });
      setTitle('');
      setPriority(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not capture that — try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="bg-white border border-[#e5e7eb] rounded-2xl p-3 sm:p-4 shadow-sm" aria-label="Quick capture">
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          data-testid="quick-capture-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit();
          }}
          placeholder="Capture a task or idea…"
          className="flex-1 border border-[#d1d5db] rounded-xl px-3 py-2.5 text-[15px] outline-none focus:border-[#7c5cff] focus:ring-2 focus:ring-[#f3f0ff]"
        />
        <div className="flex items-center gap-2">
          <div className="flex bg-[#f1f3f5] rounded-full p-1" role="group" aria-label="Kind">
            <button
              className={`px-3 py-1.5 rounded-full text-sm font-medium ${kind === 'task' ? 'bg-[#111827] text-white' : 'text-[#4b5563]'}`}
              onClick={() => setKind('task')}
            >
              Task
            </button>
            <button
              className={`px-3 py-1.5 rounded-full text-sm font-medium ${kind === 'idea' ? 'bg-[#7c5cff] text-white' : 'text-[#4b5563]'}`}
              onClick={() => setKind('idea')}
            >
              Idea
            </button>
          </div>
          <button
            className={`px-3 py-2 rounded-xl border text-sm font-medium ${priority ? 'border-[#d97706] bg-[#fffbeb] text-[#d97706]' : 'border-[#d1d5db] text-[#4b5563] bg-white'}`}
            onClick={() => setPriority((p) => !p)}
            aria-pressed={priority}
            title="Flag as priority"
          >
            ⚑ Now-ish
          </button>
          <button
            data-testid="quick-capture-add"
            onClick={() => void submit()}
            disabled={busy || !title.trim()}
            className="px-4 py-2.5 rounded-xl bg-[#111827] text-white text-sm font-semibold disabled:opacity-40"
          >
            Add
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-[#dc2626]">{error}</p>}
      <p className="mt-2 text-xs text-[#9ca3af]">Lands in the Inbox. Cooper files it from there — nothing gets lost.</p>
    </section>
  );
}
