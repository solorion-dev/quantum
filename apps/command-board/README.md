# Quantum Command Board (`apps/command-board`)

The official Quantum application for the Command Board (TRK-0686): Scotty's
quick-capture task & idea board, graduated from the Muse "Command Board"
Space into the monorepo. One shared board, two doors — this app is the
canonical one; the Space syncs against it (see **SYNC.md** in this folder).

Built with **React 19 + TypeScript + Vite + Tailwind CSS**, following the
Quantum corporate minimalist design language (light surfaces, soft borders,
black primary buttons, generous whitespace, brand violet `#7C5CFF` as an
accent only).

## What it does

- **Quick Capture** pinned at the top: one line, Task/Idea toggle, ⚑ Now-ish
  priority flag, Enter to add. Captures land in the **Inbox**.
- **Boards**: Main, Minecraft, Quantum / Fleet, Money, Leave & Paperwork,
  Creative, Home (seeded) — plus user-creatable boards. Deleting a board
  returns its items to the Inbox unfiled.
- **Kanban + List** per board over the columns Now / Next / Later / Waiting /
  Done; cards move via the column menu (drag is a Space-side nicety, the
  menu is the reliable path on phones).
- **Item detail**: title/notes editing, board/column/assignee/priority
  controls, checkbox subtasks, a Scotty ⇄ Cooper comment thread, Cooper's
  status line, and a Tracker ID chip — the same fields the fleet works with.
- **Activity feed**: the audit stream of everything that happens on the
  board (captures, filings, moves, Cooper updates).
- The board **polls every 20 s**, so Cooper's updates appear without a
  reload — same behavior as the Space.

## Architecture

- **No mocks, no fake data:** the UI talks only to the Command Board REST
  API (`services/command-board`, default `http://127.0.0.1:8798`).
- **Same-origin discipline (TRK-0660):** the client defaults to relative
  `/api` paths. In dev, the Vite proxy forwards `/api` to the service; in
  production the app is served on the same origin as the API. Set
  `VITE_BOARD_API_URL` only for non-standard deployments.
- **Solorion-login seam:** there is deliberately **no app-local password
  form**. The "Acting as" switcher (Scotty/Cooper) is the v1 seam, exactly
  like the bank app's account switcher; production fronting is the Solorion
  universal login (TRK-0494), and the service accepts an optional
  `BOARD_TOKEN` bearer in the meantime.
- Fleet agents use the same board through the hub-api **`quantum_board_*`
  MCP tools**, which wrap this API — never a second write path.

## Run it

```sh
# 1) the canonical service (from services/command-board)
npm install && npm run build && npm start        # http://127.0.0.1:8798

# 2) this app
npm install && npm run dev                        # http://127.0.0.1:5179
```

## Verify

```sh
npm run typecheck && npm test                     # unit (API client)
npm run test:e2e                                  # Playwright, service + dev server running
```

Screenshots from the verification pass live in `screenshots/`
(desktop 1280×800 and phone 390×844).
