/**
 * Collab tab — the DSECT collaboration system in the Quantum app.
 *
 * Two views, one codebase: Simple (clean task lists, default) and Board
 * (kanban with drag-between-columns, filters, activity feed). Same
 * `/api/collab/*` backend as the hub dashboard module.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card } from '@dsect/ui/components/surfaces';
import { EmptyState, Spinner } from '@dsect/ui/components/feedback';
import { TextField, TextArea } from '@dsect/ui/components/forms';
import { Button } from '@dsect/ui/components/buttons';
import { Dialog } from '@dsect/ui/components/overlays';
import { ListTodo, KanbanSquare, Plus } from 'lucide-react';
import { getSettings } from '../../lib/settings';
import { CollabClient, type CollabActivityEvent, type CollabGoal, type CollabTag, type KanbanBoard } from '../../api/collab';
import { SimpleView } from './SimpleView';
import { BoardView } from './BoardView';
import { ActivityFeed } from './ActivityFeed';

type ViewMode = 'simple' | 'board';

export function CollabScreen() {
  const settings = getSettings();
  const client = useMemo(() => new CollabClient(settings.hub.baseUrl), [settings.hub.baseUrl]);

  const [mode, setMode] = useState<ViewMode>('simple');
  const [goals, setGoals] = useState<CollabGoal[]>([]);
  const [tags, setTags] = useState<CollabTag[]>([]);
  const [board, setBoard] = useState<KanbanBoard | null>(null);
  const [activity, setActivity] = useState<CollabActivityEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [goalId, setGoalId] = useState<string | null>(null);
  const [showNewGoal, setShowNewGoal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!client.configured) return;
    setLoading(true);
    setError(null);
    try {
      // Board + goals + tags + activity degrade independently.
      const [g, b, t, a] = await Promise.allSettled([
        client.goals(),
        client.board(goalId ?? undefined),
        client.tags(),
        client.activity(20),
      ]);
      if (g.status === 'fulfilled') setGoals(g.value);
      if (b.status === 'fulfilled') setBoard(b.value);
      if (t.status === 'fulfilled') setTags(t.value);
      if (a.status === 'fulfilled') setActivity(a.value);
      const failures = [g, b, t, a].filter((r) => r.status === 'rejected');
      if (failures.length === 4) {
        setError('Could not reach the collaboration backend. Check the tailnet connection.');
      }
    } finally {
      setLoading(false);
    }
  }, [client, goalId]);

  useEffect(() => {
    if (!client.configured) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([client.goals(), client.board(goalId ?? undefined), client.tags(), client.activity(20)])
      .then(([g, b, t, a]) => {
        if (cancelled) return;
        if (g.status === 'fulfilled') setGoals(g.value);
        if (b.status === 'fulfilled') setBoard(b.value);
        if (t.status === 'fulfilled') setTags(t.value);
        if (a.status === 'fulfilled') setActivity(a.value);
        // Same total-failure semantics as refresh() (TRK-0610): only
        // when all four calls fail is the backend unreachable — partial
        // failure still degrades per section with no error card.
        const failures = [g, b, t, a].filter((r) => r.status === 'rejected');
        if (failures.length === 4) {
          setError('Could not reach the collaboration backend. Check the tailnet connection.');
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [client, goalId]);

  const createGoal = async () => {
    const title = newTitle.trim();
    if (!title || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      await client.createGoal({ title, description: newDesc.trim() || undefined });
      setNewTitle('');
      setNewDesc('');
      setShowNewGoal(false);
      await refresh();
    } catch {
      setCreateError('Could not create the goal. Check the connection and try again.');
    } finally {
      setCreating(false);
    }
  };

  if (!client.configured) {
    return (
      <div className="p-4">
        <EmptyState
          title="Collaboration is not connected"
          text="Add your Hub API base URL in More → Connection settings to sync goals and boards."
        />
      </div>
    );
  }

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* View toggle + actions */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex gap-1" role="tablist" aria-label="Collab view">
          <Button
            size="sm"
            variant={mode === 'simple' ? 'primary' : 'ghost'}
            onClick={() => setMode('simple')}
            role="tab"
            aria-selected={mode === 'simple'}
          >
            <ListTodo size={14} /> Simple
          </Button>
          <Button
            size="sm"
            variant={mode === 'board' ? 'primary' : 'ghost'}
            onClick={() => setMode('board')}
            role="tab"
            aria-selected={mode === 'board'}
          >
            <KanbanSquare size={14} /> Board
          </Button>
        </div>
        <Button size="sm" variant="outline" onClick={() => { setShowNewGoal(true); setCreateError(null); }}>
          <Plus size={14} /> Goal
        </Button>
      </div>

      {error && (
        <Card className="p-3">
          <p className="text-sm text-[var(--red)]">{error}</p>
          <Button size="sm" variant="ghost" onClick={refresh} className="mt-1">Retry</Button>
        </Card>
      )}

      {mode === 'simple' ? (
        <SimpleView client={client} goals={goals} loading={loading && goals.length === 0} onChanged={refresh} />
      ) : (
        <>
          <BoardView
            client={client}
            goals={goals}
            tags={tags}
            board={board}
            loading={loading && !board}
            goalId={goalId}
            onGoalId={setGoalId}
            onChanged={refresh}
          />
          <Card className="p-4">
            <h3 className="font-semibold text-sm mb-2">Recent activity</h3>
            <ActivityFeed events={activity} loading={loading && activity.length === 0} />
          </Card>
        </>
      )}

      <Dialog open={showNewGoal} onClose={() => setShowNewGoal(false)} title="New goal">
        <div className="flex flex-col gap-3">
          <TextField
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            label="Title"
            placeholder="Goal title"
          />
          <TextArea
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            label="Description"
            placeholder="Description (optional)"
            rows={3}
          />
          {createError && (
            <p className="text-sm text-[var(--red)]" role="alert">{createError}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowNewGoal(false)}>Cancel</Button>
            <Button onClick={createGoal} disabled={creating || !newTitle.trim()}>
              {creating ? <Spinner size="sm" /> : 'Create goal'}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
