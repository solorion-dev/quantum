# Developer Hub — `apps/dev-hub`

Slice 1 of the Developer Hub (TRK-0075): an authenticated, read-only
operator landing for the DSECT fleet. It aggregates the fleet's **own**
live surfaces into one Overview page — it does not invent a new source
of truth, and every section of the API response names the surface that
served it (`sources` object).

## What's in slice 1

- **Overview page only.** Bootcheck verdict banner, fleet services
  grouped (core systemd units / Docker containers / loopback HTTP
  services) with health chips and probe latency, host cards (uptime,
  load, memory, disks `/`, `/mnt/fast`, `/mnt/mybook`), and Tracker
  counts by status. Auto-refreshes every 15 s with a last-updated stamp.
- **Stub nav** — Logs, Tailscale, Home Assistant, Cron are rendered as
  disabled entries marked “next slice”. Nothing behind them exists yet.
- **Read-only aggregator backend** — `server/devhub_server.py`, a
  single-file Python **stdlib-only** server (pattern:
  `apps/breeze-studio/breeze_server.py`). It serves the built app from
  `apps/dev-hub/dist` and same-origin JSON:
  - `GET /api/session` — caller identity (see auth below).
  - `GET /api/fleet/status` — live aggregate. Fleet data tries hub-api
    `http://127.0.0.1:8091/api/status` first; on error/401 it falls back
    to direct read-only probes (`systemctl is-active` for
    `dsect-hub-api`, `cloudflared-dsect-web`, `tailscaled`, `docker`;
    `docker ps`; loopback HTTP GETs). Bootcheck verdict comes from
    quantum-bootcheck's latest summary file
    (`/home/scott/quantum-bootcheck-latest.txt`, the `LATEST=` path in
    `/usr/local/sbin/quantum-bootcheck.sh`). Host data from `/proc` and
    `shutil.disk_usage`. Tracker counts from SQLite opened read-only
    (`file:/mnt/fast/tracker/tracker.db?mode=ro`), `items` grouped by
    `status`.
  - All endpoints are GET-only; POST/PUT/DELETE/PATCH return **405**.
    There is no mutating endpoint, by design — audited actions stay
    gated on Scotty's explicit decision (spec v0 decision 2, still open).

## Auth model

Being on the tailnet is the credential (same pattern as hub-api):

1. The server looks at the peer IP of the request.
2. **Loopback / self peer = box operator (preview behaviour).** A
   request from `127.0.0.1`/`::1`, or a connection from this host to its
   own tailnet address (only local processes can source from the host's
   own IP — Tailscale authenticates sources), is identified as the
   first allowlist entry. This exists so the preview can be verified
   from the box itself: Tritium is a tagged device, so `tailscale
   whois` on its own IP returns the device DNS name
   (`tritium-linux.fairy-chinstrap.ts.net`), not a user login, and
   on-box curl/Playwright would otherwise 401. Preview-only behaviour,
   not the production model.
3. Any other peer is resolved with `tailscale whois --json <peer_ip>`;
   the resulting `LoginName` must appear in
   `server/allowed_logins.txt`.
4. **Fail closed:** a missing or empty allowlist admits nobody (401).

Seeded allowlist: `scottyvenable@gmail.com` (also the sole entry found
in hub-api's on-box `allowed_logins.txt`, read by name only) and
`cooper@dsect.net`.

## Run it

```bash
cd apps/dev-hub
npm install
npm run build

# Preview (slice 1, Tritium): tailnet IP only — never 0.0.0.0
DEVHUB_HOST=100.66.182.7 DEVHUB_PORT=8420 \
  python3 server/devhub_server.py
# -> http://100.66.182.7:8420/
```

Detached preview as run for slice 1 verification:

```bash
setsid nohup env DEVHUB_HOST=100.66.182.7 DEVHUB_PORT=8420 \
  python3 server/devhub_server.py >/tmp/devhub-8420.log 2>&1 &
```

Screenshots / render evidence:

```bash
npm run screenshots   # scripts/capture.mjs (Playwright)
# writes screenshots/overview-desktop.png, screenshots/overview-phone.png,
# and screenshots/render-evidence.txt (title, headings, service-row count)
```

## What's stubbed / not done

- Logs, Tailscale, Home Assistant, Cron pages: nav stubs only.
- Hive page: not in slice 1.
- No actions (restart/wake/etc.) — no endpoint, no UI affordance beyond
  the plan note.
- **Production path is NOT done:** no nginx vhost, no `dev.dsect.net`
  DNS/serve config was created for slice 1. The intended production
  route is an nginx vhost on the tailnet IP + `tailscale serve`
  (mirroring `dsect-hub`), so real requests arrive with resolvable
  tailnet peers; that is a later, separately approved step.

## Conventions

Self-contained app like `apps/universal-hub`: own `package.json`,
React 19 + Vite + TypeScript + `@tailwindcss/vite`. Style: modern
corporate minimalist — light surfaces (`#fafafa` canvas, white cards),
soft `neutral-200` borders, black primary buttons, brand violet
(`#7c5cff`) only for the logo, active nav, and links.
