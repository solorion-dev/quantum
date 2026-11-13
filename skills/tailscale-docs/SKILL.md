---
name: tailscale-docs
version: 1.0.0
description: "Look up current Tailscale documentation for Serve, Funnel, ACLs, MagicDNS, HTTPS certs, and home-lab patterns. Use when planning Tailscale work, verifying CLI syntax, or answering how-to questions about tailnet services."
tags: [quantum]
status: active
provenance: quantum
aliases: [local-tailscale-docs]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Tailscale Docs Lookup

## Purpose
Find current, accurate Tailscale documentation. Never answer version-sensitive CLI syntax or config schema from memory — always verify against the live docs.

## Workflow

1. **Search the official KB first:**
   - Use `browser.search` with query like `tailscale serve https site:tailscale.com` or `tailscale funnel limitations site:tailscale.com`
   - Prefer results from `tailscale.com/kb/` — these are the official docs

2. **Open the KB page:**
   - Use `browser.open` on the official KB URL
   - Read the current syntax, flags, and limitations

3. **Cross-check if needed:**
   - If the KB page is unclear or seems outdated, search for recent homelab guides
   - Note the date of any secondary source

4. **Report with citations:**
   - Include the KB URL
   - Quote the relevant command/config exactly
   - Note any gotchas or prerequisites

## Key KB Pages

| Topic | URL |
|-------|-----|
| Tailscale Serve | https://tailscale.com/kb/1312/serve |
| Tailscale Funnel | https://tailscale.com/kb/1223/funnel |
| ACL syntax (grants) | https://tailscale.com/kb/1192/acl-syntax |
| MagicDNS | https://tailscale.com/kb/1081/magicdns |
| HTTPS certificates | https://tailscale.com/kb/1153/enabling-https |
| Exit nodes | https://tailscale.com/kb/1103/exit-nodes |
| Subnet routers | https://tailscale.com/kb/1019/subnets |
| Tailscale Services | https://tailscale.com/kb/1624/services |

## Quick Reference

See `references/` for detailed cheat sheets:
- `serve.md` — Serve CLI and config
- `funnel.md` — Funnel setup and limitations
- `acls.md` — ACL grants syntax and examples
- `magicdns-https.md` — MagicDNS and certificate management
- `homelab.md` — Home lab architecture patterns

## Operating Rules

1. **Always verify CLI syntax** against the live KB before recommending commands. Tailscale's CLI evolves; `serve` config schema in particular has changed.
2. **Note prerequisites** — Serve needs admin-console enablement, HTTPS needs MagicDNS + cert toggle, Funnel needs policy `nodeAttrs`.
3. **Distinguish Serve vs Funnel** — Serve is tailnet-only; Funnel is public via ts.net. Neither does custom domains.
4. **For Scotty's setup** — public services stay on Cloudflare Tunnel (custom `*.dsect.net` domains). Tailscale Serve is for tailnet-only services. Funnel is for ad-hoc shares only.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
