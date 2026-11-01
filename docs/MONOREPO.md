# Quantum platform monorepo migration

**Decision (Scotty, Oct 15, 2026):** Change the default. New Quantum-flavored apps start in one platform monorepo; separate repos are for things that have earned them. Scotty approved starting the migration on Oct 15 ("We can probably start that migration").

## The rule

- **Monorepo by default** for anything that shares Quantum's login, design language, and home on Tritium.
- **Separate repo** for infrastructure, standalone products, and anything with its own audience, deploy rhythm, or access rules.
- **Spin out, don't start out.** An app graduates to its own repo when it proves it needs one.
- **No big-bang migration.** Existing repos stay put; apps fold in opportunistically, one at a time, each fold verified (build green against the pushed artifact) before the next begins.
- **Monorepo home:** `dsect-net/quantum` — the everything app is the platform's front door, so the repo restructures around it: `apps/` (quantum app first) and `packages/` (shared UI kit, auth, clients).

## Repo inventory & classification (30 repos, audited Nov 1, 2026)

### Fold into the monorepo (share Quantum's login / design / Tritium home)
- `quantum` — becomes the monorepo home itself (`apps/quantum`)
- `design-system` (426 KB, CSS/TS) → `packages/ui` — the shared component kit every app imports
- `agent-chat` (381 KB, TS) — agent team chat; a Quantum module
- `hive-memory` (1 MB, JS) — Hive explorer; a Quantum module
- `research-hub` (52 KB, TS, idle since Sept 29) — research module; lowest-risk first fold
- `quantum-cli` (26 KB, JS) → `packages/cli` (later phase; tooling, not an app surface)

### Stays separate (earned it)
- `tritium-stacks` — infrastructure; different blast radius and cadence
- `hub-api` — ops hub service; deploys independently (revisit only after the monorepo is proven)
- `nebula` — large standalone generation service/product, actively developed
- `eidolon` — standalone product, 108 MB, own identity
- `sol-app` — standalone product with its own APK/releases
- `home-assistant` — server config repo, not an app
- `quantum-codex` — the vault / operating-system docs
- `wroc` — personal work tooling (Python), unrelated stack
- `dsect.dev` — public site
- `quantum-launcher` (Kotlin), `hive-flutter` (Flutter) — different stacks; revisit if they converge
- `herald`, `cerebrum` — Python backend services, not app surfaces
- `quantum-plus` — Jellyfin theme; unrelated surface
- `.github`, `agent-template-kit`, `template-*` — org scaffolding

### Archive candidates (empty stubs, no code, idle since Sept 25, 2026)
- `tritium` (3 KB stub), `lightspeed` (3 KB stub), `event-horizon` (3 KB stub) — name reservations with no implementation; archiving unclutters every sweep. (Archiving is Scotty's explicit call per repo, not part of the phases below.)

### Not yet classified (owner decision needed)
- `scotty-stats` — present in the org; not in the Oct 15 audit. Fold / stay / archive is Scotty's call.
- `quantum-credits` — present in the org; not in the Oct 15 audit. Fold / stay / archive is Scotty's call.

## Phases (story points, Fibonacci)

1. **Designate & document** — this issue + `docs/MONOREPO.md` in `dsect-net/quantum`. *(2 pts — done Oct 15)*
2. **Restructure quantum repo** — move the existing app to `apps/quantum`, create `packages/` skeleton, workspace tooling, build + tests verified green against the pushed ref, APK path unaffected. *(13 pts)*
3. **First fold: research-hub** — smallest leaf, no dependents; proves the fold procedure end to end. *(3 pts)*
4. **design-system → packages/ui** — highest value; every app imports the kit instead of vendoring copies. Import paths updated in quantum app; build verified. *(5 pts)*
5. **Fold agent-chat and hive-memory as modules** — one at a time, each verified live before the next. *(8 pts)*
6. **Evaluate, don't assume** — hub-api and nebula stay separate unless a concrete sharing need appears; quantum-cli folds only if the TUI starts sharing packages. *(review, 0 pts)*

**Program total: ~31 points.**

## Guardrails
- **Stack-affinity guardrail.** The monorepo default is not a gravity well: a component on a foreign runtime — a Python/Demucs audio worker, a native toolchain, GPU-bound processing — is not forced into the TypeScript/pnpm monorepo merely to obey "spin out, don't start out." Heavy or foreign-runtime services stay as isolated containers or in their own repos and talk to the platform over the same contracts as everything else. The monorepo default applies to components that genuinely share Quantum's stack, login, and design language; stack affinity beats repo tidiness. *(From the Cooper × Antigravity joint plan §3; decided by Cooper, Oct 15, 2026, under Scotty's handoff rule.)*
- One fold at a time; a fold is done only when the app builds and runs from the monorepo (verified against the pushed artifact, not a local tree).
- Merging a fold = deploying it, per Scotty's standing rule; nothing folds silently.
- Old repos are archived (not deleted) after a successful fold, with a pointer README to the monorepo.
- Anything with its own users/releases (Sol, Eidolon) is out of scope unless Scotty explicitly adds it.
