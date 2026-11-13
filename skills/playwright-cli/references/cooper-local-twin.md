# Cooper local twin (pre-reconciliation)

Seeded from Codex `playwright-cli`; this is the divergent local copy (`local-playwright-cli`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# Browser Automation with playwright-cli

## Quick start

```bash
playwright-cli open
playwright-cli goto https://playwright.dev
playwright-cli click e15      # interact using refs from the snapshot
playwright-cli type "page.click"
playwright-cli press Enter
playwright-cli screenshot
playwright-cli close
```

## Core commands

open, goto, type, click, dblclick, fill (--submit presses Enter), drag, drop (--path/--data), hover, select, upload, check/uncheck, snapshot, find (text or --regex), eval (JS in page or against an element ref), dialog-accept/dismiss, resize, close.

Navigation: go-back, go-forward, reload.
Keyboard: press, keydown, keyup.
Mouse: mousemove, mousedown/up (left/right), mousewheel.
Save-as: screenshot (--filename, --hires), pdf.
Tabs: tab-list, tab-new, tab-close, tab-select.
Storage: state-save/load; cookie-*, localstorage-*, sessionstorage-* (list/get/set/delete/clear).
Network: route (--status, --body), route-list, unroute.
DevTools: console, requests, request <id>, run-code, tracing-start/stop, recording-start/stop, video-start/chapter/stop, video-show-actions/hide-actions, `show --annotate` (interactive UI-review dashboard), generate-locator, highlight (--style, --hide).

## Raw / JSON output

`--raw` strips status/generated-code/snapshot, returning only the result value — good for piping. `--json` wraps replies as structured JSON.

## Targeting elements

Prefer refs from `snapshot` (e.g. `click e15`). CSS selectors and Playwright locators also work: `click "#main > button.submit"`, `click "getByRole('button', { name: 'Submit' })"`, `click "getByTestId('submit-button')"`.

## Sessions

`-s=name` scopes commands to a named browser session (supports `--persistent` profile). `tab-list`/`list`, `close-all`, `kill-all` manage sessions/browsers globally.

## Open parameters

`--browser=chrome|firefox|webkit|msedge`, `--mobile` (emulate generic mobile — lighter snapshots), `--device="iPhone 15"`, `--persistent`/`--profile=path`, `attach --extension=chrome`, `attach --cdp=chrome|msedge|http://localhost:9222`, `--config=file.json`.

## Windows `&` in URLs

`cmd.exe`/PowerShell treat `&` as a separator — escape with `^&` in cmd, or prefix `--%` in PowerShell.

## Interactive UI review

`playwright-cli open <url>` then `playwright-cli show --annotate` — user draws boxes and types comments on the live page; you receive the annotated screenshot, snapshot of the marked region, and notes. Use for "UI review" / "design feedback" requests.

## Installation

Global: `npm install -g @playwright/cli@latest`. Or local via `npx --no-install playwright --version` / `npx playwright cli`.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
