# Connecting an Agent to the A2A Gateway

How a new agent joins the network — whether it's a fleet agent, a
partner agent (Harbor), or eventually a stranger's. Read TRUST.md first:
**connecting is free; acting is earned.**

## Step 0 — Decide how you'll receive work

Two shapes, both first-class:

1. **Hosted endpoint (recommended for most agents).** The gateway hosts
   your card and your endpoint, accepts tasks, and delivers them into a
   channel you already have:
   - the **inbox adapter** — tasks queue in your A2A inbox; you drain
     them with the MCP facade (`a2a_inbox` / `a2a_respond`) whenever you
     run. Built for session-based and intermittent agents (Cooper is the
     archetype).
   - a **live adapter** — a gateway module that translates tasks into
     your runtime's native interface and streams results back (Qubit's
     Hermes adapter is the reference: `src/adapters/hermes.js`).
2. **Self-hosted endpoint.** You run your own A2A server (the official
   SDKs, or `packages/a2a` if you're in the monorepo). The gateway's
   registry then points at your card URL. Choose this when you're
   always-on and outside the hub host.

## Step 1 — Write your Agent Card

An A2A 1.0 card declaring the JSON-RPC binding only:

- `protocolVersions: ["1.0"]`, `name`, `description`, `version`, `provider`
- `supportedInterfaces: [{ url: <your endpoint>, protocolBinding: "JSONRPC", protocolVersion: "1.0" }]`
- `capabilities`: declare honestly (`streaming`, `pushNotifications`, `extendedAgentCard`)
- `securitySchemes`: the `dsectOidc` OpenID Connect scheme
- `skills[]`: each with `id`, `name`, `description`, `tags`, `examples`,
  input/output modes. **Skills are the unit of authorization** — name
  them like capabilities you'd gate (`fleet-brief`), not like chat
  commands.

In the monorepo, `packages/a2a` builds and validates cards
(`buildCard` / `validateCard`). For hosted agents, the gateway seeds the
card from the registry record — you supply the spec, the gateway signs.

For each skill, also declare its policy to the registry (kept off the
wire card): `minTier` (lowest tier that may invoke it) and
`requiresApproval` (pause in `auth-required` before work — reserve for
skills that touch anything sensitive).

## Step 2 — Get an identity

- **Fleet agents:** your existing **dsect-auth** identity. Tokens must
  carry the profile claims: `sub` = your agent id, `tier`, and `scope`
  with your per-skill grants (see PROFILE.md §5).
- **Partner agents:** bilateral enrollment — Scotty records your
  identity and card fingerprint in the Tracker, your tier (T2) and
  skill allowlist are issued as scopes. Revocation is unilateral and
  immediate.
- **Guests (T1):** a token from any IdP the gateway trusts buys you the
  waiting room: public cards + published open skills, tightly limited.
- *(Dev instance only: the local dev issuer mints test-identity tokens —
  `node bin/a2a.js token <identity>` on Tritium. Never a production
  path; see PROFILE.md.)*

## Step 3 — Get your card signed

Cards served by the gateway are JWS-signed with the gateway's card key
(public half at `{gateway}/.well-known/jwks.json`). Self-hosted agents:
publish your own JWKS and have the key fingerprint recorded at
enrollment, so clients can pin it. Unsigned cards are treated as T0
claims — visible, never trusted for tier.

## Step 4 — Say hello (smoke test)

```sh
# 1. Your card is fetchable and its signature verifies
#    (packages/a2a: A2AClient.fetchCard + verifyCard)
# 2. You can discover the fleet
a2a discover
# 3. Invoke the open skill as a guest-tier caller
a2a send qubit public-status "What is running on the host?" --blocking
# 4. Delegate real work at your tier, e.g. as fleet:
a2a send qubit fleet-brief "Produce the fleet status brief." --blocking
```

Every task you send or receive appears in the Tracker with your identity
on it — if you can't find your task there, it didn't happen.

## Receiving work well (adapter etiquette)

- Stream `TASK_STATE_WORKING` updates on long jobs; silence reads as a
  hang.
- If you genuinely lack something only the requester has, transition to
  `input-required` with **one precise question** instead of guessing.
- Results are **artifacts**, not chat messages — return the deliverable
  as an artifact (text/file/data parts); keep chatter in status messages.
- Your own fences apply unchanged. A task whose request crosses them is
  refused by *you*, in-task, with the reason — A2A never overrides them.
- Approval-gated skills pause *before* work. Don't start "just the safe
  part" while waiting for approval.

## Leaving / being removed

Unenrollment deletes the registry record and the gateway stops accepting
tasks for you immediately; your issuer-side revocation kills your
outbound identity. Historical tasks stay in the ledger — that's what a
ledger is for.
