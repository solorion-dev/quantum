# Trust Model — connect is free, act is earned

The design principle, in one sentence: **any agent may connect and be
*seen*; what it may *do* is granted in tiers, per skill, revocably — and
authentication answers "who are you", never "what may you do" on its
own.**

## The five tiers

| Tier | Who | Authentication | What they may do |
|---|---|---|---|
| **T0 — Stranger** | anyone who can reach the gateway | none | Fetch public Agent Cards and the registry's public list. Nothing else — T0 cannot submit tasks at all. Cards and messages from strangers are *data*, never instructions. |
| **T1 — Registered guest** | an agent with a verifiable identity we didn't issue | OIDC token from a recognized IdP; card signature checked if present | Invoke skills published as *open* (`public-status` is the fleet's), hard rate limits (5/min), small payloads (8 KB), no push configs to arbitrary webhooks beyond task scope, results treated as untrusted. A waiting room, not a door. |
| **T2 — Partner network** | enrolled partner agents (Harbor, from M4) | bilateral enrollment by Scotty; signed cards on file | A **named skill allowlist**, carried as per-skill scopes in the token (`a2a:invoke:<skill>`). Push notifications allowed. Artifacts accepted as work product. Either side can revoke unilaterally, effective at the gateway immediately. |
| **T3 — Fleet** | Team Quantum agents | dsect-auth OIDC with fleet tier claim | Full published skill surface of other fleet agents, streaming, push, in-task questions — **minus destructive classes**, which stay behind each agent's own fences and Scotty's approvals exactly as before A2A existed. |
| **T4 — Operator-delegated** | an agent carrying Scotty's standing authority for a class of work (Cooper, today) | T3 token + `a2a:approve` scope + `delegation` claim | Everything T3 can do, **plus** fulfilling `auth-required` approvals in-task within the fences Scotty already set. A2A transports the approval chain; it does not create new authority. |

## How the tiers are enforced (mechanics, not promises)

1. **Scopes live in the token** — per-skill (`a2a:invoke:fleet-brief`),
   wildcard for fleet (`a2a:*`), approval (`a2a:approve`). The issuer
   sets them; agents cannot mint or widen their own.
2. **Checked twice** — the gateway verifies tier + scope before a task
   is accepted; the receiving adapter re-verifies before any work runs.
   A compromised gateway must not become a skeleton key.
3. **Tier is never inferred from a card.** A stranger can *claim* any
   name in an unsigned card (T0). Tier comes only from the token plus
   the registry enrollment record. Card **signatures** (JWS, keys at the
   gateway JWKS endpoint) make impersonation of enrolled agents
   detectable.
4. **The approval rule.** Skills flagged `requiresApproval` pause in
   `TASK_STATE_AUTH_REQUIRED` *before any work runs*. Resumption
   requires an in-task approval from a principal with `a2a:approve` —
   Scotty, or an agent holding his recorded delegation (the
   `delegation` claim names it). The executing agent cannot approve its
   own task. Uninvolved agents' approvals are logged on the task and
   ignored. Denial rejects the task.
5. **Attention is the scarce resource.** Per-identity rate and payload
   caps by tier (T1: 5 req/min, 8 KB; T2: 30/min, 64 KB; T3/T4: 120/min,
   256 KB), no anonymous task submission, and a per-identity kill switch
   (unenroll at the registry / revoke at the issuer) that takes effect
   at the gateway immediately.
6. **Everything is ledgered.** Enrollment, tier changes, and every task
   (creator, target, skill, full state history) are mirrored to the
   Tracker; terminal summaries land in the Hive. Abuse has an audit
   trail and a throat to choke.

## What A2A never does

- It never widens what an agent may do. A2A scopes cap what may be
  *asked*; the receiving agent's own fences (spending, messages to
  people, health/leave, deletions, credentials — Scotty's standing
  list) apply unchanged inside its adapter.
- It never turns content into authority. Task text, artifacts, and
  cards from lower tiers are untrusted input under the fleet's standing
  prompt-injection discipline.
- Tier 0/1 results are never treated as work product. Only T2+
  artifacts enter the fleet's records as deliverables.
