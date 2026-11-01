# The DSECT A2A Profile — v0.1

A profile of **A2A protocol 1.0** (Linux Foundation, Apache 2.0). A
profile restricts what *we require and advertise*; it does not fork the
standard. The data model, task lifecycle, Agent Card format, and error
taxonomy are vanilla A2A 1.0, so any conforming peer can interoperate at
the core (`SendMessage` / `GetTask` / cards) without knowing this
document exists.

## 1. Binding

- **JSON-RPC 2.0 over HTTPS only.** gRPC and HTTP+JSON/REST bindings are
  out of profile for v0.1; cards advertise exactly one interface
  (`protocolBinding: "JSONRPC"`, `protocolVersion: "1.0"`).
- Requests carry `A2A-Version: 1.0`.

## 2. Operations in profile

| Operation | In v0.1 | Notes |
|---|---|---|
| `SendMessage` | ✅ | blocking or non-blocking (`configuration.blocking`) |
| `SendStreamingMessage` | ✅ | SSE: Task, then `TaskStatusUpdateEvent` / `TaskArtifactUpdateEvent`, closes at terminal state |
| `GetTask` | ✅ | participants (creator, target agent, approvers) only |
| `ListTasks` | ✅ | same visibility rule; filter by contextId/status |
| `CancelTask` | ✅ | terminal tasks return `TaskNotCancelable` (−32002) |
| `SubscribeToTask` | ✅ | SSE |
| Push notification configs (Create/Get/List/Delete) | ✅ | server POSTs updates to the webhook *with the configured credentials*, per spec |
| `GetExtendedAgentCard` | ❌ | not configured; returns −32007 honestly rather than faking a card |

Errors use the A2A JSON-RPC code range (−32001…−32009) plus standard
JSON-RPC codes. Authentication failures are transport-level (HTTP
401/403); authorization failures on invoke are 403 with code −32009.

## 3. Skill selection (extension)

Vanilla A2A selects work conversationally; our policy model binds
authorization to named skills, so the profile defines one request
extension:

- `message.metadata["dev.dsect.skill"]` — the skill being invoked. Must
  match a skill id on the target agent's card and the caller's token
  scope. (If the agent publishes exactly one skill, it may be omitted.)

Response/task metadata extensions (additive; ignorable by other peers):

- `dev.dsect.tracker` — `{ trkId }`, the Tracker item mirroring the task.
- `dev.dsect.hive` — `{ contextRef }`, the Hive context for the task.
- `dev.dsect.approval` — on a follow-up message: `{ decision: "approved" | "denied", by }` (see §5).

## 4. Agent Cards

- Served per agent at `{gateway}/agents/{agentId}/.well-known/agent-card.json`
  and listed at `{gateway}/registry/agents`.
- **JWS-signed** (RS256 over the RFC 8785 canonicalization of the card,
  per A2A spec §8). Signing keys are published at `{gateway}/.well-known/jwks.json`.
  Unsigned or badly-signed cards are Tier-0 claims: displayable, never
  trusted for tier inference.
- Capability flags are honest: `streaming: true`, `pushNotifications: true`,
  `extendedAgentCard: false`.

## 5. Identity & authorization

- Scheme: `openIdConnectSecurityScheme` only. No API keys in profile.
- Tokens are JWTs validated against **any trusted issuer's JWKS** — the
  production issuer is **dsect-auth** (discovery
  `https://mcp.dsect.net/.well-known/openid-configuration`; fleet agents
  already hold these identities). Validation is issuer-agnostic code.
- **Profile claims** (set by the issuer, consumed by gateway + adapter):
  - `sub` — agent id (e.g. `qubit`)
  - `tier` — trust tier 0–4 (see TRUST.md)
  - `scope` — space-separated; per-skill invoke scopes
    `a2a:invoke:<skillId>`, wildcard `a2a:*`; approvers carry `a2a:approve`
  - `delegation` — optional; names the authority behind an approver
    (e.g. `scotty-standing`)
- Authorization is **checked twice**: at the gateway before a task is
  accepted, and again inside the receiving adapter before any work runs.
- **The `auth-required` rule:** an approval is honored only from a
  principal holding `a2a:approve` — i.e. Scotty, or an agent carrying his
  recorded delegation. The executing agent can never approve its own
  task; an uninvolved agent's "approval" is recorded and ignored. This
  mirrors the fleet's standing approval fences; A2A transports the chain,
  it does not create new authority.

### Dev-issuer note (v0.1 dev instance only)

dsect-auth currently offers only `authorization_code` + `refresh_token`
grants — non-interactive agents cannot mint profile-claim tokens against
it headlessly. The tailnet dev instance therefore also trusts a local
**dev issuer** (`A2A_DEV_IDP=1`) that mints 1-hour tokens for a fixed set
of *test identities* (cooper, qubit, bookkeeper, partner-demo,
guest-demo), gated by a bootstrap secret in the state dir. This is a
stand-in IdP for development, not a second identity system: the
validation path is identical to production's. **Production migration:**
add a machine grant (client-credentials or token-exchange) to dsect-auth
or register per-agent clients, then remove the dev issuer from the
gateway's trust list — a config change, tracked as a TRK-0424 follow-up.

## 6. Ledger (extension, gateway-side)

Every task is mirrored by the gateway — never by the agents:

- **Tracker:** one item per task (child of the A2A epic), transitions as
  comments, terminal state sets the item's status.
- **Hive:** a terminal-state summary memory (agent `cooper`, tags
  `a2a, ledger`), so the exchange is reconstructible alongside the
  fleet's other memory. Mirroring failures are captured to
  `ledger-errors.jsonl` (+ `hive-outbox.jsonl`) and never fail the task.

## 7. Exposure

v0.1: **tailnet-only.** The gateway binds the host's tailnet address; no
public listener, no Cloudflare route. Public card reads (M5) and partner
task submission (M4) are separate, gated decisions.
