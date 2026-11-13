---
name: nebula-deploy
version: 1.0.0
description: "Deploy the Nebula web UI to Tritium: pull latest main, rebuild the React bundle, update the index shim, verify live. Use whenever Nebula frontend changes need to go live on the server."
tags: [quantum]
status: active
provenance: quantum
aliases: [local-nebula-deploy]
dependencies:
  tools: [dev_shell]
  repos: [dsect-net/nebula]
  urls: []
maintainers: [cooper]
---
# Nebula deploy

Deploys the Nebula React web UI to Tritium. The server (`server.py`, the
dsect-net/nebula repo) runs on Tritium at `/home/scott/comfy-companion`
— yes, the directory is named comfy-companion, but it is a clone of
`dsect-net/nebula` on branch `nebula-deploy`, serving `:8092`.

## Layout on Tritium

- Repo: `/home/scott/comfy-companion` (branch `nebula-deploy`, remote `dsect-net/nebula`)
- Web source: `web/` — build with `npm run build` (outputs to `../static/react/`)
- Served files: `static/react/` (committed build output: index.html, assets/, logo.png)
- Shim: `static/index.html` — **local-only, uncommitted**. A small page that
  pre-paints the theme and loads the hashed JS/CSS from `/static/react/assets/`.
  It must be rewritten after every build (hashes change) or the page 404s.
- Server: `server.py` serves static files from disk — **no restart needed**
  for frontend-only deploys. Restart only if `server.py` itself changed.

Use the tritium-mcp skill's `dev_shell` for all Tritium commands.

## Deploy steps

1. Back up the shim: `cp static/index.html /tmp/nebula-shim.html`
2. `git fetch origin && git reset --hard origin/main`
3. `cd web && npm run build` (must complete with no TS/vite errors)
4. Read the new hashed names from `static/react/index.html`:
   `assets/index-<hash>.js` and `assets/index-<hash>.css`
5. Rewrite the shim from the backup with the new hashes:
   `sed -e "s|assets/index-[A-Za-z0-9_-]*\.js|<new-js>|" -e "s|assets/index-[A-Za-z0-9_-]*\.css|<new-css>|" /tmp/nebula-shim.html > static/index.html`
   (Note: hashes may contain `-`; the character class must include it.)
6. Verify, all must be HTTP 200:
   - `http://127.0.0.1:8092/static/index.html`
   - the new JS and CSS under `/static/react/assets/`
   - `http://127.0.0.1:8092/static/react/logo.png`
7. Sanity: the served JS bundle should contain a string from the change
   (e.g. `grep -c "logo.png"`).

## Gotchas (learned Oct 2, 2026)

- Never `git checkout` the shim away — always back it up first; it is the
  only uncommitted file that matters.
- The `nebula-deploy` branch drifts behind main; `reset --hard` is the
  intended sync (nothing of value lives only on that branch).
- If the tunnel is down (Cloudflare 1033/530), Tritium is unreachable —
  check the box physically before retrying.
- After a host reboot, services may need `bash /home/scott/nebula-ltx25/ltx-prep.sh restore`.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
