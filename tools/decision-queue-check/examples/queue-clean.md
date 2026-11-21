# Pending decisions queue (worked example — clean)

Decisions Cooper has flagged to Scotty that block advancement. Under the decision
timeout rule: each item carries a deadline; past the deadline Cooper
may decide it himself (choosing his recommended option), record it here, and
report it in chat. Fenced items (money, messages to others, health/leave,
deletions, credentials, irreversible) NEVER auto-decide.

Status legend: awaiting / emailed / auto-decided / decided-by-scotty / dropped

| # | Decision | Asked | Deadline | Recommended | Status |
|---|----------|-------|----------|-------------|--------|
| 1 | Tune the Jellyfin transcoding cache size? | 2026-11-01 09:00 | Fri Nov 27, 2026 ~09:00 EST (24h — blocks nothing) | Raise it | awaiting |
| 2 | Clear dangling worker keyIds from workers.json? | 2026-11-01 09:05 | none — credential-adjacent, FENCED, never auto-decides | Clear + commit | awaiting (fenced: his call) |
| 3 | Restart the preview slot to pick up the new build? | 2026-10-20 10:00 | Wed Oct 21, 2026 ~10:00 EDT (24h) | Restart it | AUTO-DECIDED 2026-10-20 ~10:30 EDT — Cooper: restarted, verified healthy |
| 4 | Pick the default map tile style for the dashboard? | 2026-11-02 12:00 | Thu Nov 5, 2026 ~12:00 EST (24h) | Street style | DECIDED 2026-11-03 — Scotty approved directly |

## Outcome lines — 14-day reviews

Scope: the auto-decisions — #3. Item #2 is still awaiting Scotty (fenced) — no decision exists yet, so no outcome line is owed for it.

- **#3 (auto-decided 2026-10-20) — Outcome 2026-11-04: HELD UP.** The preview slot has run the new build since; no rollback recorded. Evidence: deploy log.

Notes:
- Deadline scale: 1h / 4h / 8h / 12h / 24h tiers, 48h hard cap. First clocks started Nov 2, 2026 ~09:00 EST.
