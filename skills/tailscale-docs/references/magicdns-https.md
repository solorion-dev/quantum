# MagicDNS and HTTPS Certificates — Reference

## MagicDNS

Every device gets `<machine>.<tailnet>.ts.net` (e.g., `tritium.tailnet.ts.net`).

- Enable on the admin console DNS page
- Rename via console or `tailscale up --hostname=tritium`
- Supports custom search domains, split DNS, extra nameservers
- **Required by both Serve and HTTPS certs**
- Stable 100.x.y.z IPs work too, but names are ergonomic

## Tailscale HTTPS Certificates

```bash
sudo tailscale cert tritium.tailnet.ts.net
```

- Provisions real browser-trusted **Let's Encrypt** cert for MagicDNS name
- Private key never leaves the machine
- Use when terminating TLS yourself (Caddy/nginx) instead of Serve

### Renewal

- **Manual** — 90-day certs, script via cron/systemd
- **Or use Caddy 2.5+** — auto-fetches and renews `*.ts.net` certs with zero config (needs Tailscale socket access)

### Custom Domains

- **Not covered** by Tailscale certs
- For `nebula.dsect.net`-style names on tailnet: use ACME DNS-01 via DNS provider
- Or keep them on Cloudflare Tunnel (edge certs handled there)

## Docs
- https://tailscale.com/kb/1081/magicdns
- https://tailscale.com/kb/1153/enabling-https
