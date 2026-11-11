---
name: local-service-chain-diagnosis
description: Use when a named fleet service or site is reported down — a 502, an unreachable *.dsect.net name, "the hub/board/Jellyfin isn't working" — before asserting any root cause. Traces the user's real path hop by hop (DNS → edge/tunnel → proxy → listener → process → logs/deps) and names each surface checked, avoiding green-on-the-wrong-surface verdicts.
---

# Service Chain Diagnosis

## Purpose
Most wrong outage calls come from probing a convenient surface instead of the path the user actually travels. On Oct 21 the hub was called "healthy" for hours off port 8790 — that's Reeve — while the real backend crash-looped behind the proxy. This procedure names every hop before it trusts any of them. (For fleet-wide symptom triage use local-quantum-doctor; for claim discipline generally use local-verify-authoritative-surface. This skill is the network-path procedure for one named service.)

## Procedure
1. **State the claim and the real path.** "X is down" means: from the user's entry point (public name, app, bookmark) to the bytes. Write the expected chain before probing: public DNS → Cloudflare edge → tunnel ingress or nginx vhost → upstream host:port → process/systemd unit → its logs and filesystem dependencies (mounts, state dirs, config).
2. **Probe hop by hop, naming each surface and its raw result** (status code, byte count, latency). A green at any hop proves only that hop. Record which process actually listens on each port (`ss -ltnp`, unit status) — never assume a port's owner.
3. **Read the failing unit's journal and its dependency declarations** (`RequiresMountsFor`, `WorkingDirectory`, state paths). Two of tonight's three outages were dependency deaths, not code deaths: hub-api crash-looping on a root-owned stub state dir; llama-embed never starting because its model mount was absent.
4. **Fix only the hop that's dead**, minimally and reversibly, then re-verify the *whole public path* — "fixed" is claimed only when the user's entry point returns the expected result.
5. **Report the scope of every check.** "Reeve answers on :8790" is evidence; "the hub is healthy" is a verdict. Never upgrade one into the other.

## Trap table (verified, Tritium)
- **mcp.dsect.net chain:** Cloudflare → mail-inbound tunnel → nginx :8094 → **127.0.0.1:8091 (dsect-hub-api)**. Port **:8790 is Reeve**, a different service — its 200 proves nothing about the hub.
- **Jellyfin origin is 127.0.0.1:8100** (host-networked container). **:8096** is an nginx vhost serving a memorial page; **:8090** is the Ops Hub. A 200 from :8096 is not evidence Jellyfin is up.
- **Dispatcharr :9191 refuses loopback** — probe via the LAN IP, and re-derive that IP from the live configs (it was .34, now 192.168.4.196; stale notes and .bak files keep the old one). Its proxy takes 4–8s to first byte: short-timeout probes fabricate "dead stream." Give stream checks 30s+.
- **NXDOMAIN ≠ origin down.** tracker.dsect.net returned empty from the VM while the board served 200 on Tritium — the Cloudflare record itself was gone. Confirm with a DoH query plus control names in the same run (see local-domain-dns-audit).
- **Vantage limits:** this VM's egress proxy returns empty-reply for some surfaces (public names, ts.net). A failed probe from the VM is scoped evidence, not a verdict — cross-check from Tritium or the user's own screen before calling anything down.
- **fstab can look guilty and be innocent:** the /srv/ai entries were present all along; their *source device* (a removed drive) was absent. Check `blkid`/`findmnt` for the device before editing mount config.

## Output contract
Every diagnosis report lists: the chain with each hop named, the result observed at each hop, which hop was dead, the fix applied (or the exact change needed, if it's fenced), and the public-path verification that earned the word "fixed."
