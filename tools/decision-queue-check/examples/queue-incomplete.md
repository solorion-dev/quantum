# Pending decisions queue (worked example — incomplete)

Decisions Cooper has flagged to Scotty that block advancement. Under the decision
timeout rule: each item carries a deadline; past the deadline Cooper
may decide it himself (choosing his recommended option), record it here, and
report it in chat. Fenced items (money, messages to others, health/leave,
deletions, credentials, irreversible) NEVER auto-decide.

Status legend: awaiting / emailed / auto-decided / decided-by-scotty / dropped

| # | Decision | Asked | Deadline | Recommended | Status |
|---|----------|-------|----------|-------------|--------|
| 1 | Reorder the Nebula render queue priorities? | 2026-11-01 09:00 | when the render batch feels right | Reorder | awaiting |
| 2 | Pick the default map tile style for the dashboard? | 2026-11-02 12:00 | Thu Nov 5, 2026 ~12:00 EST (24h) | Street style | DECIDED 2026-11-03 — Scotty approved directly |

Notes:
- Deadline scale: 1h / 4h / 8h / 12h / 24h tiers, 48h hard cap. First clocks started Nov 2, 2026 ~09:00 EST.
