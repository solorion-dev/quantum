import type Database from 'better-sqlite3';
import { BoardService } from './service.js';

/**
 * Seed-on-empty (TRK-0686): the same real backlog the Muse Command
 * Board Space opened with, so the Quantum app starts as the same board,
 * not a demo. Board names match the Space exactly.
 */
export function seedIfEmpty(db: Database.Database): boolean {
  const { boards } = new BoardService(db).getCounts();
  if (boards > 0) return false;

  const svc = new BoardService(db);

  const main = svc.createBoard({ name: 'Main', origin: 'seed' }, 'cooper');
  const minecraft = svc.createBoard({ name: 'Minecraft', origin: 'seed' }, 'cooper');
  const fleet = svc.createBoard({ name: 'Quantum / Fleet', origin: 'seed' }, 'cooper');
  const money = svc.createBoard({ name: 'Money', origin: 'seed' }, 'cooper');
  const leave = svc.createBoard({ name: 'Leave & Paperwork', origin: 'seed' }, 'cooper');
  svc.createBoard({ name: 'Creative', origin: 'seed' }, 'cooper');
  svc.createBoard({ name: 'Home', origin: 'seed' }, 'cooper');
  void minecraft;

  const wipe = svc.createItem(
    {
      title: "Wipe the old Windows install on Tritium's 1.8T drive — inventory + rescue first",
      boardId: main.id,
      column: 'now',
      priority: true,
      assignee: 'cooper',
      createdBy: 'cooper',
      origin: 'seed',
    },
    'cooper'
  );
  svc.updateItem(wipe.id, {
    cooperStatus: 'In progress tonight — inventory and rescue run before anything is deleted.',
  });
  svc.addComment(wipe.id, {
    author: 'cooper',
    origin: 'seed',
    body: "Running this tonight in order: full inventory of the Windows volume, rescue anything unique to the spare drive (copy-verified), sweep the fstab/boot references, and only then remove the partitions. ~1.85 TB to reclaim. The /srv/ai btrfs partition on the same drive is fenced off — never resized, never touched. I'll stop before the delete step if the inventory turns up anything surprising.",
  });

  const decision = svc.createItem(
    {
      title: "Pick the Decision Page's home: its own sidebar Space vs a view inside Tritium/Quantum",
      boardId: main.id,
      column: 'waiting',
      assignee: 'scotty',
      createdBy: 'cooper',
      origin: 'seed',
    },
    'cooper'
  );
  svc.updateItem(decision.id, {
    cooperStatus: 'Waiting on Scotty — my lean is its own Space, but you floated both.',
  });
  svc.addComment(decision.id, {
    author: 'cooper',
    origin: 'seed',
    body: "My recommendation: its own sidebar Space. Your decisions span money, fleet, and leave paperwork — not just Tritium — and a dedicated spot with a pending count is harder to lose than a tab. The starter backlog is ready either way: the 3 fenced digest items, the cron audit, the A2A standard, the thermistor order, and PR #133 once it's fixed.",
  });

  const cron = svc.createItem(
    {
      title: 'Cron audit — approve the trim plan (49 jobs → ~33)',
      boardId: main.id,
      column: 'waiting',
      assignee: 'scotty',
      createdBy: 'cooper',
      origin: 'seed',
    },
    'cooper'
  );
  svc.updateItem(cron.id, {
    cooperStatus: 'Waiting on Scotty — plan is written, needs your approval to apply.',
  });
  svc.addComment(cron.id, {
    author: 'cooper',
    origin: 'seed',
    body: '49 scheduled jobs audited; the trim plan retires or merges about a third of them (stale one-offs, duplicates, and jobs whose work moved elsewhere). Nothing gets deleted until you approve the list — the plan is the deliverable waiting on you here.',
  });

  const a2a = svc.createItem(
    {
      title: 'A2A membership standard (TRK-0676) — approve so it binds the fleet',
      boardId: main.id,
      column: 'waiting',
      assignee: 'scotty',
      createdBy: 'cooper',
      origin: 'seed',
      trkId: 'TRK-0676',
    },
    'cooper'
  );
  svc.updateItem(a2a.id, {
    cooperStatus: 'Waiting on Scotty — standard is drafted; approval makes it binding.',
  });
  svc.addComment(a2a.id, {
    author: 'cooper',
    origin: 'seed',
    body: "The agent-to-agent membership standard is drafted and filed as TRK-0676. It only binds the fleet once you approve it — until then agents like Reeve stay in limbo (his A2A enrollment was deferred Nov 12 for exactly this reason).",
  });

  const bridge = svc.createItem(
    {
      title: "Bridgecrest $321 due Sat Nov 14 — payment prepared, needs Scotty's tap",
      boardId: money.id,
      column: 'now',
      priority: true,
      assignee: 'scotty',
      createdBy: 'cooper',
      origin: 'seed',
    },
    'cooper'
  );
  svc.updateItem(bridge.id, { cooperStatus: 'Payment prepared — waiting on your tap to submit.' });
  svc.addComment(bridge.id, {
    author: 'cooper',
    origin: 'seed',
    body: "$321 to Bridgecrest, due Saturday Nov 14. The payment is prepared and staged; it just needs your tap to submit. Flagging here so it doesn't get buried while PFML income is still settling in.",
  });

  const davis = svc.createItem(
    {
      title: 'Davis Chiropractic — call to pause (next appt Wed Nov 18)',
      boardId: money.id,
      column: 'next',
      assignee: 'scotty',
      createdBy: 'cooper',
      origin: 'seed',
    },
    'cooper'
  );
  svc.updateItem(davis.id, { cooperStatus: 'Up next — call before the Wed Nov 18 appointment.' });
  svc.addComment(davis.id, {
    author: 'cooper',
    origin: 'seed',
    body: "Next appointment is Wednesday Nov 18. The call is to pause the plan while you're on leave — worth making before that appointment rather than after another charge lands.",
  });

  const joyous = svc.createItem(
    {
      title: 'Joyous follow-up today 2:10 PM — report the Nov 11 dose episode',
      boardId: leave.id,
      column: 'now',
      priority: true,
      assignee: 'scotty',
      createdBy: 'cooper',
      origin: 'seed',
    },
    'cooper'
  );
  svc.updateItem(joyous.id, {
    cooperStatus: 'Today, Fri Nov 13 at 2:10 PM online — rescheduled from the missed Nov 4 follow-up.',
  });
  svc.addComment(joyous.id, {
    author: 'cooper',
    origin: 'seed',
    body: 'Rescheduled follow-up is today at 2:10 PM online. Main thing to report: the Nov 11 dose episode. The $159 payment went through Nov 12, so the old hold-request text is moot — no need to raise it.',
  });

  const pr133 = svc.createItem(
    {
      title: 'PR #133 Command Hub — Gemini applying 3 fixes, Cooper re-verifies',
      boardId: fleet.id,
      column: 'next',
      assignee: 'cooper',
      createdBy: 'cooper',
      origin: 'seed',
    },
    'cooper'
  );
  svc.updateItem(pr133.id, {
    cooperStatus: 'Gemini is applying the 3 fixes; I re-verify before it moves.',
  });
  svc.addComment(pr133.id, {
    author: 'cooper',
    origin: 'seed',
    body: "Gemini has the 3 fixes for the Command Hub PR. Once they're in, I re-verify the whole change before it goes anywhere near merge — same drill as always: the fix doesn't count until it's checked against the artifact.",
  });

  const graduate = svc.createItem(
    {
      title: 'Command Board as a Quantum app + Quantum MCP tools, synced with the Muse Space',
      boardId: fleet.id,
      column: 'now',
      priority: true,
      assignee: 'cooper',
      createdBy: 'scotty',
      origin: 'seed',
      trkId: 'TRK-0686',
    },
    'cooper'
  );
  svc.updateItem(graduate.id, {
    cooperStatus: 'Building now — canonical app + API in the monorepo, quantum_board_* tools as a draft hub-api PR.',
  });
  svc.addComment(graduate.id, {
    author: 'cooper',
    origin: 'seed',
    body: 'Scotty (Nov 13, via the Space): graduate this board from a Muse Space into a real Quantum application with Quantum MCP tools, and keep the Space and the app in sync — one shared board, two doors. The app owns the canonical store; MCP tools wrap its API; the Space syncs against it (see SYNC.md in apps/command-board).',
  });

  return true;
}
