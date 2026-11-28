// Smoke test for the Command Board service: boots the built server on an
// ephemeral port with an in-memory DB and exercises the core REST flow.
// Usage: npm run smoke   (builds first)
const base = process.env.SMOKE_BASE || 'http://127.0.0.1:8798';

async function main() {
  const health = await fetch(`${base}/health`).then((r) => r.json());
  console.log('health:', JSON.stringify(health));
  if (health.status !== 'ok') throw new Error('health not ok');

  const state = await fetch(`${base}/api/v1/state`).then((r) => r.json());
  console.log(`state: ${state.boards.length} boards, ${state.items.length} items`);
  if (state.boards.length !== 7) throw new Error('expected 7 seeded boards');

  const created = await fetch(`${base}/api/v1/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Smoke capture', kind: 'task' }),
  }).then((r) => r.json());
  console.log('created item:', created.id, created.column);
  if (created.column !== 'inbox') throw new Error('capture should land in inbox');

  const updated = await fetch(`${base}/api/v1/items/${created.id}/cooper-update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cooperStatus: 'Smoke OK', comment: 'Smoke comment', column: 'done', checked: true }),
  }).then((r) => r.json());
  console.log('cooper-update:', updated.cooperStatus, updated.comments.length, 'comments');
  if (updated.comments.length !== 1) throw new Error('comment missing');

  console.log('SMOKE PASS');
}

main().catch((err) => {
  console.error('SMOKE FAIL:', err.message);
  process.exit(1);
});
