# MCP Facade — Tool Reference

The gateway exposes an **MCP server** (Streamable HTTP) at
`POST {gateway}/mcp` so that any MCP-speaking agent can use A2A through
tools, without implementing the A2A wire protocol.

- **Auth:** the same OIDC bearer token used for A2A itself
  (`Authorization: Bearer <token>`). Your token's `sub` *is* your agent
  identity for every tool; tier policy is enforced identically to the
  JSON-RPC surface.
- **Framing:** standard MCP JSON-RPC (`initialize`, `tools/list`,
  `tools/call`). Tool results are JSON text content (the A2A objects:
  cards, tasks) — parse them as JSON.

- **Access paths:** this facade is served by the gateway itself. The hub MCP
  (`mcp.dsect.net`) does not proxy these tools yet — connect your MCP client
  directly to the gateway (tailnet), or use the operator CLI `bin/a2a.js`
  from Tritium, which calls this facade with dev-issuer tokens.
- **Relationship to A2A:** the facade is a convenience binding over the
  same gateway core. MCP is the vertical layer (agent ↔ tools); A2A
  remains the horizontal protocol (agent ↔ agent). Nothing the facade
  does is unavailable over raw A2A, and vice versa.

## Tools

### `a2a_discover`

Search the registry for agents and skills.

| Argument | Type | Notes |
|---|---|---|
| `query` | string | free-text match over skill ids/names/descriptions and agent ids |
| `skill` | string | exact skill id |
| `tag` | string | skill tag |

Returns a list of `{ agentId, agentName, endpoint, skill, policy }` where
`policy` is `{ minTier, requiresApproval }` — check it before sending so
a doomed request never burns rate limit.

### `a2a_send_task`

Delegate work (`SendMessage` under the hood).

| Argument | Type | Notes |
|---|---|---|
| `agent` | string, required | target agent id |
| `text` | string, required | task message text |
| `skill` | string | skill id (profile extension `dev.dsect.skill`) |
| `data` | object | optional structured data part (e.g. `{ "path": "AGENT_STANDARD.md" }`) |
| `taskId` | string | continue a paused task (input-required / auth-required follow-ups) |
| `contextId` | string | group related tasks |
| `blocking` | boolean | wait for a terminal or paused state before returning |

Returns the task object: `{ id, contextId, status: { state, … },
artifacts, history, metadata }` — `metadata["dev.dsect.tracker"]` links
the Tracker mirror.

### `a2a_task_status`

`{ taskId }` → the task (state, last 10 history entries, artifacts).
Visible only to the task's creator, its target agent, and approvers.

### `a2a_inbox`

Lists **your own** queued hosted-inbox tasks — work other agents
delegated to you that is waiting for a response. (Only meaningful for
agents behind the hosted-inbox adapter, e.g. Cooper.)

### `a2a_respond`

Complete one of your inbox tasks: `{ taskId, text }`. Your text becomes
the result artifact and the task transitions to `TASK_STATE_COMPLETED`.

### `a2a_approve`

Fulfill an `auth-required` approval: `{ taskId, decision, note? }` with
`decision` = `"approved"` or `"denied"`.

**Approval rule (enforced):** honored only from Scotty or an agent
holding his recorded delegation (token scope `a2a:approve`). The
executing agent can never approve its own work; anyone else's attempt is
recorded on the task and ignored. See TRUST.md.

## Example session (dev instance, operator CLI equivalents)

```sh
a2a discover --skill fleet-brief
# → qubit, minTier 3, requiresApproval false

a2a send qubit public-status "What is running on the host?"
# → task … TASK_STATE_SUBMITTED (poll with `a2a status <taskId>`,
#    or use --blocking)

a2a send qubit gated-file-read "Summarize AGENT_STANDARD.md"
# → pauses at TASK_STATE_AUTH_REQUIRED …
a2a approve <taskId> approved     # … until a delegated approver acts
```

## Errors

Tool errors return MCP `isError` results whose text carries the A2A/HTTP
failure (e.g. tier/scope denials are 403s naming the missing tier or
scope). Rate limits are per identity and tier (T1 guests are tightly
capped) — back off rather than retrying in a loop.
