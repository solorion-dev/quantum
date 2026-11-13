---
name: quantum-auth
version: 1.0.0
description: "Quantum auth skill. Use when a dsect.net login fails, a tunnel is confused with the tailnet, or a password needs setting. Never store or retrieve a password. Hub stays tailnet-only."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-auth]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Auth

## Pass

1. Memory search dsect-auth and the hostname. Newer signed row wins.
2. `hub.dsect.net` is tailnet-only on purpose. Proxying it breaks Tailscale WhoIs. Do not put it on the public tunnel.
3. `nebula.dsect.net` is public through the tunnel. Tunnel presence is not tailnet presence. A passphrase prompt there is the fallback, not proof the app is broken.
4. Secure Vault capture does not write `users.db`. Do not read a password back out. He re-supplies it on a channel that can hash into `/home/scott/.config/dsect-auth/users.db`.
5. No passwords, tokens, or hashes in memory, mail, or Codex.

## Close

Workspace note: hostname, which door failed, next check. Not the secret.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
