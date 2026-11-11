---
name: local-domain-dns-audit
description: Use when a *.dsect.net or *.solorion.dev name stops resolving, when auditing DNS records across Scotty's zones, before or after a Solorion migration tranche, or when checking whether a subdomain's tunnel/proxy wiring is intact. Distinguishes a missing record (NXDOMAIN) from a dead origin, with control names in every run.
---

# Domain & DNS Health Audit

## Lesson this encodes
On Oct 21, tracker.dsect.net "wasn't working" while its server answered 200 the whole time — the Cloudflare DNS record itself had vanished (NXDOMAIN). One missing record and a dead zone look identical from a browser. Audit records as their own surface; never infer them from the origin's health.

## Build the expected-name list from evidence
Derive the names that *should* resolve from live artifacts, not memory: cloudflared configs on Tritium (`~/.cloudflared/`, `/etc/cloudflared/`), nginx vhosts, Tailscale Serve config, and service notes. Memory's list is a cross-check, not the source.

## Audit procedure
1. For every expected name, query DNS-over-HTTPS (Cloudflare: `https://cloudflare-dns.com/dns-query?name=<name>&type=A` with `Accept: application/dns-json`; repeat for CNAME where relevant). Record: Status, Answer (target/IPs), or absence.
2. **Always run at least two control names in the same batch** (e.g. nebula.dsect.net, hub.dsect.net). Controls resolving while one name returns **Status 3 (NXDOMAIN)** = that record is gone, zone healthy. Everything failing = suspect the zone or your own vantage, not 30 separate records.
3. Classify each name's chain and verify the matching hop:
   - **Tunnel-backed (proxied):** needs BOTH the proxied record pointing at the tunnel AND a tunnel ingress rule for the hostname. Check the tunnel's journal too — zero requests ever arriving for a name is consistent with DNS death, not origin death.
   - **Tailnet names** (e.g. hub.dsect.net → 100.x): public DoH may show the tailnet IP by design. Verify these through Tailscale status/Serve, not public resolvers.
   - **Direct/nginx:** confirm a vhost actually claims the name on :443 before blaming DNS for a wrong-site response.
4. Cross-check resolution from a second vantage (Tritium itself) — this VM's egress proxy fabricates empty replies for some names, which is a vantage artifact, not DNS evidence.

## Report
Per name: resolves? / to what? / chain intact at which hop? / verdict. Group as: healthy, record-missing, record-wrong, origin-down-behind-good-DNS. Name the exact corrective change for each defect (e.g. "restore proxied record + dsect-web ingress rule tracker.dsect.net → http://127.0.0.1:7654").

## Fences
- **Never improvise DNS changes.** Creating, restoring, or altering records is Scotty's call or an explicitly approved task. The audit reports; it does not edit. (Restoring tracker.dsect.net was left as his decision on Oct 21, with the interim tailnet link offered.)
- Solorion migration state: dsect.net remains the live zone until Scotty releases tranches; solorion.dev is registered (Squarespace; DNS-to-Cloudflare is a planned tranche under dsect-net/quantum#58). Audit both zones and expect asymmetry — a missing solorion.dev record may be "not yet migrated," not "broken." Say which.
