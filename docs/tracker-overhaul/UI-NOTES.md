# Tracker board overhaul: UI notes (Pixel, 2026-11-04)

Branch `experimental/tracker-overhaul-20261104`. App: `apps/tracker-board` (v2.0.0-experimental). Not deployed.

## Run it
```sh
git submodule update --init vendor/design-system      # @dsect/ui at 685acd3, consumed from source
cd apps/tracker-api && python3 -m tracker_api --reset  # http://127.0.0.1:7655/api
cd apps/tracker-board && npm ci
TRACKER_API=http://127.0.0.1:7655 npm run dev          # the vite proxy sends /api to TRACKER_API (default 7655)
```
- Data source: `VITE_TRACKER_SOURCE=auto|api|fixture` (default `auto`, which checks `/api/health` and falls back to the fixture). Override per tab with `?source=fixture` or `?source=api`.
- Load testing: `?source=fixture&synthetic=600` pads the fixture to 600 fake items.
- Edits send `X-Actor: pixel` (`VITE_TRACKER_ACTOR`).
- Tests: `PW_CHROME=/usr/bin/google-chrome npx playwright test`. This starts its own throwaway API on 7656 (`--reset --db /tmp/tracker-board-e2e.db`) and vite on 5175. The projects are desktop-1920 and phone-390, and the axe tags are wcag2a/2aa/21aa/22aa.
- `npm run lint`, `npx tsc -b` and `npm run build` are clean.

## What's in it
- **Shared filter bar** across Board, List and Projects: search, status, priority, assignee (including Unassigned), labels, project, flags (stale, needs triage) and A2A mode (group, show inline, hide). It shows removable chips and is URL-addressable (`#/view/ITEM?query`).
- **Summary strip.** Its metrics are buttons that apply the matching filter.
- **Board.** 5 primary columns; Backlog and Cancelled collapse at the edges. Pointer drag/drop is supported. For keyboard use, arrows move focus and Shift+Left/Right moves the card one column (PATCH). Enter opens the item. Each column pages at 30 cards ("Show 30 more"). On phones it becomes a horizontal scroll-snap row.
- **List.** Kit `Table` with sortable `aria-sort` headers. It pages at 100 rows.
- **Projects.** Progress per project/root, which also acts as a filter.
- **Detail.** Read-first drawer, or a bottom sheet at ≤720px. Sections: Overview, Description, Links, Sync, Relations, History and Comments. Editing status, priority and assignee is an opt-in step.
- **GitHub badge** with a sync dot and text: Synced (green), Sync pending (grey), Suggestion waiting (amber), Sync error (red).
- **Suggestions inbox** with Accept and Reject; Reject takes an optional reason. It calls the real `/api/suggestions` endpoints.
- **Labels** use the tags-table colour as a decorative swatch when one is set. Null assignee, parent and due date render as Unassigned or an em dash.
- Light theme by default; Dark is a toggle stored in `localStorage['tracker.theme']`. Styling uses tokens only.

## Performance (600 items, 1920x1080, synthetic fixture)
Load to first card took ≈350ms, with 150 cards in the DOM (paged). Search filter took ≈60ms. List "+100 rows" took ≈155ms. Paging was chosen over virtualization so DnD, focus order and axe stay simple. If the real data proves heavier, the next step is windowing the list.

## For Scout
- E2E: `apps/tracker-board/e2e/smoke.spec.ts` has 13 tests (7 on desktop, 6 on phone) and they all pass. The suggestion test signs a GitHub webhook with the README's **fake local secret** against the throwaway API only.
- The phone tests use keyboard activation inside the scroll-snap board and the animating sheet, because Playwright's pointer hit-test fights both. Real taps were checked by screenshot.
- Worth testing by hand: screen-reader announcements for card moves (there is a `role=status` live count plus toasts), and the dark theme with axe (contrast was measured at a 4.77 minimum, but axe only ran on Light).

## Stubbed or waiting on Volt
- `project`: there is no field yet. The UI uses `item.project` if present, otherwise the root ancestor through `parentId`.
- A2A detection is a heuristic (label `a2a` or `automated`, or a title starting "A2A"). It needs a real flag or `source` value.
- Relation direction: I read `rel: parent, direction: out` as "Parent of". Please confirm.
- People: 7fa3ad8 returns `name`, where 946dcb8 returned `display`. The client accepts either.
- Creating items (POST) is wired in the client but there is no UI for it yet.

## Open questions
1. A project field and an A2A flag (see above).
2. Kit: FilterBar chips use a generic "Remove filter" aria-label, so the app renders its own chips. Should this go upstream to @dsect/ui, along with the local Popover and MultiSelect?
3. **Security:** tracker.dsect.net is public with no auth and exposes `POST /api/item/<id>/update`. It needs an auth decision before this board points at prod.
