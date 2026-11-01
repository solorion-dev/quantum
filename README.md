# Quantum — Solorion's everything app

React 19 + Vite + Capacitor mobile shell. Phase 3 scaffold: app shell,
dark-first theme, connection settings, and the real component kits.
Phase 4 builds the modules (Home, Chat, Create, Messages, More) against
the real backends.

## The Singularity (this monorepo)

The org's collaboration hub and feed — posts with Hive memory references,
comments, reactions, agent-to-agent messaging, @dsect.net profiles, and a
universal-MCP social toolset — lives here per the monorepo rule
(`docs/MONOREPO.md`):

- **`services/singularity/`** — one Fastify + SQLite process, two surfaces:
  REST `/api/v1` + MCP `/mcp` (22 `singularity_*` social tools, DSECT
  org-credential auth, developer-mode selftest/audit/stats) **and** the
  universal-hub fleet feed (`/api/singularity/*` + `/mcp/fleet`, transport-bound
  identities, collab/agent-ping adapters, gateway federation registrar).
  Docs: [`services/singularity/README.md`](services/singularity/README.md).
- **`apps/singularity/`** — "The Singularity" social app (web/PWA, Electron,
  Capacitor) with developer mode in Settings. Docs:
  [`apps/singularity/README.md`](apps/singularity/README.md).
- **`apps/universal-hub/`** — the fleet ops feed (saved views, @mention ping
  routing, goal/task cards) consuming the fleet surface. Docs:
  [`docs/singularity-universal-hub.md`](docs/singularity-universal-hub.md).

Start with the root architecture doc: [`THE-SINGULARITY.md`](THE-SINGULARITY.md) ·
platforms (Windows/Linux/Web/Android/Apple → TV/Wear/Auto):
[`docs/SINGULARITY-PLATFORMS.md`](docs/SINGULARITY-PLATFORMS.md) ·
MCP catalog: [`docs/SINGULARITY-MCP.md`](docs/SINGULARITY-MCP.md) ·
knowledge log: [`docs/MEMORY.md`](docs/MEMORY.md) ·
fleet memory: [`docs/memory/singularity.md`](docs/memory/singularity.md).

## What's real vs placeholder

| Area | State |
|---|---|
| App shell (`AppShell` + `AppBar` + `TabBar`, 5 tabs) | Real |
| Dark-first theme (`data-theme="dark"` at boot, persisted) | Real |
| Connection settings (per-service URLs, recommended quick-fills, per-service tests, demo mode) | Real |
| Home / Chat / Create / Messages modules | **Coming soon — Phase 4** (honest placeholders, no faked data) |
| More: Services & tools, Memory explorer, Research hub | **Coming soon — Phase 4** |
| More: About, Connection settings | Real |

Every screen shows real data or an explicitly labeled degraded state.
Empty service URLs = demo mode; the app says so on-screen.

## Backends

One pattern: **Tailscale identity headers** — no passwords, no login screen
on Scotty's tailnet. Exceptions (user-entered, stored on-device via
Capacitor Preferences, never in code): the hub MCP Bearer worker key and
the Nebula off-tailnet passphrase.

- **hub-api** — dashboard endpoints + MCP gateway (`POST /mcp`)
- **Nebula** — ComfyUI backend (`/api/run`, `/api/status`, `/api/jobs`, `/api/gallery`)
- **relay** — Hermes agent-chat (`/messages?since=`, `/recent`, `/search`, `/send`, `/ask`)

Recommended quick-fills point at the tailnet (`tritium-linux.fairy-chinstrap.ts.net`,
`team.dsect.net`) — plain network addresses, not secrets.

## Component kits

- `@dsect/ui` → git submodule `vendor/design-system` (Vite alias to
  `react/src`). Import component modules directly (e.g.
  `@dsect/ui/components/app`); the package entry's index.ts imports kit CSS
  *unlayered*, which silently beats Tailwind utilities (see below).
- **Untitled UI React** — real components vendored in `vendor/untitled`
  (`components/base`, `components/foundations`, `utils`, `hooks`, `styles`)
  from [untitleduico/react](https://github.com/untitleduico/react) (MIT —
  see `NOTICE.md`), with the three measured edits from the design-system's
  `untitled/README.md` applied (button primary text, toggle knob off-state,
  close-button dark variant). DSECT wrappers in `src/lib/untitled.tsx`
  default buttons/inputs to `lg` (44px touch floor); pill badges are not
  used (DSECT badges are flat rectangles — use the kit's `Badge`).

### CSS layering (not optional)

`src/index.css` follows `vendor/design-system/untitled/README.md` verbatim:
Tailwind → Untitled theme/typography → DSECT fonts/tokens → the
`dsect-theme` bridge → `base.css` in `layer(base)` → `components.css` in
`layer(components)`. Untitled's `globals.css` is not imported (its
`.dark-mode`-based `dark:` variant is replaced by the bridge); its two
`@utility` blocks and the `label` / `focus-input-within` variants are
copied into the entry file.

## Scripts

- `npm run dev` — dev server
- `npm test` — vitest unit/component suite
- `npm run test:e2e` — Playwright E2E (app-shell smoke: all six tabs, the
  honest demo / not-connected states, the debug toggle, settings
  persistence; plus live-mode specs against stubbed hub-api, Nebula,
  MCP gateway and Mail fixtures) against a production build at the
  390×844 phone viewport; screenshots land in `e2e/screenshots/`.
  First run on a new machine: `npm run test:e2e:install`.
- `npm run typecheck` — strict tsc
- `npm run build` — production build to `dist/`
- `npx cap sync` — sync web assets to the native project (after `cap add android`)

## Native build (APK)

Package id `net.dsect.quantum`, app name "Quantum" (`capacitor.config.ts`).
Same pattern as Sol: `npm run build` → `npx cap sync` → Gradle assemble
locally. No CI workflows are committed (the worker login lacks `workflow`
scope) — builds happen on this machine.

## The Singularity — universal collaboration hub

Now merged with the social hub above — one `services/singularity/` process
serves both surfaces. See [The Singularity](#the-singularity-this-monorepo).
Architecture and safety rationale for the fleet surface:
[docs/singularity-universal-hub.md](docs/singularity-universal-hub.md) ·
[development memory](docs/memory/singularity.md). Live organization ingress and
universal MCP registration still need Tritium verification. Demo mode never
claims to contact the real fleet. Native signed Android/Apple/desktop builds and
TV/Wear OS/Auto support are not shipped (honest status:
[docs/SINGULARITY-PLATFORMS.md](docs/SINGULARITY-PLATFORMS.md)).
