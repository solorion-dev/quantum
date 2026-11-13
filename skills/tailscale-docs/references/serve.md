# Tailscale Serve — Reference

Tailnet-only HTTPS reverse proxy. Traffic never leaves the tailnet.

## Quick Start

```bash
# One-time: enable in admin console (DNS page → MagicDNS + HTTPS Certificates)
# Serve itself needs one-time enablement via admin console link

sudo tailscale set --operator=$USER

# Serve a local service on tailnet HTTPS
tailscale serve --bg --https=443 http://127.0.0.1:8092

# Second service on alternate port
tailscale serve --bg --https=8443 http://127.0.0.1:8090

# Sub-path routing
tailscale serve --bg --set-path /watch http://127.0.0.1:8100

# Status and teardown
tailscale serve status
tailscale serve --https=443 off
tailscale serve reset
```

Result: `https://<machine>.<tailnet>.ts.net/` with browser-trusted cert.

## Config File (serve.json)

Declarative via `TS_SERVE_CONFIG` env var or `tailscale serve set-config`.

Three top-level keys:
- **TCP** — ports; `HTTPS:true` terminates TLS, `TCPForward` for raw TCP
- **Web** — keyed by `"<magicdns>:port"`; handlers: `Proxy`, `Path`, `Text`
- **AllowFunnel** — per-hostport public flag

## Gotchas

- Needs one-time interactive admin-console enablement (CLI prints login link)
- HTTPS needs MagicDNS + "HTTPS Certificates" enabled on DNS page
- Config persists across reboots — turn off when decommissioning
- One HTTPS serve per port — use `--set-path`, another port, or reverse proxy
- `--set-path` breaks apps with absolute asset URLs — test each app
- `serve --bg` can hang if Serve isn't enabled — wrap in `timeout`
- Works on mobile clients

## Docs
https://tailscale.com/kb/1312/serve
