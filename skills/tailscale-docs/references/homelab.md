# Home Lab Architecture Patterns — Reference

## Pattern A: One Reverse Proxy + One Serve (Recommended for Tritium)

- Caddy on loopback, routing by path/Host to backends
- Single `tailscale serve --bg --https=443` to Caddy
- One stable URL: `https://tritium.tailnet.ts.net`
- One ACL port (443)
- Caddy smooths sub-path quirks

**Pros:** Clean URLs, single cert, easy ACLs
**Cons:** Caddy to maintain, path routing can break apps

## Pattern B: Serve Per Port

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8092
tailscale serve --bg --https=8443 http://127.0.0.1:8090
```

- `https://host.ts.net` and `https://host.ts.net:8443`
- No proxy to maintain

**Pros:** Simple, no extra moving parts
**Cons:** Ugly URLs, per-port ACL grants

## Pattern C: Tailscale Services

Each service gets its own MagicDNS name (e.g., `https://nebula.tailnet.ts.net`).

- Must pre-create services in admin console (Admin → Services)
- Closest to per-service-hostname ergonomics without reverse proxy

**Pros:** Clean per-service names
**Cons:** Beta surface, console setup required

## Pattern D: Public via Cloudflare Tunnel

Keep public services on Cloudflare Tunnel (current `dsect-web` + `dsect-mail-inbound` split).

**Pros:** Custom `*.dsect.net` domains, Access/WAF, generous free tier
**Cons:** Separate from tailnet

## Hardening Checklist

- [ ] Tag Tritium (`tag:server`)
- [ ] Default-deny ACL + explicit port grants
- [ ] Device approval for new tailnet members
- [ ] Key expiry enabled
- [ ] Funnel disabled in policy by default
- [ ] `tailscaled` auto-updating
- [ ] Document service → URL mapping
