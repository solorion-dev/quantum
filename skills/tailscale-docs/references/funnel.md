# Tailscale Funnel — Reference

Public internet exposure via Tailscale relays. Extends Serve.

## Quick Start

```bash
tailscale funnel --bg 3000
tailscale funnel --bg --set-path /blog http://localhost:3001/blog
```

Result: `https://<machine>.<tailnet>.ts.net` publicly accessible.

## Requirements

- HTTPS certs enabled (DNS page)
- Funnel allowed in ACL policy:
  ```json
  "nodeAttrs": [{"target": ["tag:server"], "attr": ["funnel"]}]
  ```
- Per-node enablement in admin console

## Limitations

- Only ports **443, 8443, 10000**
- HTTPS only
- **No custom domains** — ts.net only, cannot use `*.dsect.net`
- One funnel per port
- **No Tailscale auth on funnel traffic** — backend must authenticate itself
- Bandwidth/rate limits — positioned for **personal/hobby use, not production**
- Unavailable on iOS/Android/macOS App Store builds

## Funnel vs Cloudflare Tunnel

| | Tailscale Funnel | Cloudflare Tunnel |
|---|---|---|
| Setup | One command | Tunnel + DNS config |
| Domain | `*.ts.net` only | Custom `*.dsect.net` |
| Auth | None (backend must handle) | Cloudflare Access, WAF |
| Limits | Hobby-grade | Generous free tier |
| Use case | Ad-hoc shares, demos, webhooks | Permanent public services |

**Recommendation for Tritium:** Keep Cloudflare Tunnel as the permanent public front door. Use Funnel only for temporary shares.

## Docs
https://tailscale.com/kb/1223/funnel
