// MCP facade — the gateway's own MCP server (Streamable HTTP, POST /mcp).
// It lets any MCP-speaking agent use A2A through tools it already
// understands, without implementing the A2A wire protocol:
//   a2a_discover  — find agents/skills in the registry
//   a2a_send_task — delegate work (SendMessage under the hood)
//   a2a_task_status — poll a task
//   a2a_inbox     — a receiving agent's queued hosted-inbox tasks
//   a2a_respond   — complete an inbox task with an artifact
//   a2a_approve   — fulfill an auth-required approval in-task
// The caller's bearer token is the same OIDC token used for A2A itself;
// the facade derives the principal identically and the core enforces the
// same tier policy. MCP is the vertical convenience; A2A stays the
// horizontal protocol. (Survey §1.2: the two compose, they don't merge.)
import { RpcError } from "./a2a.js";

const TOOLS = [
  {
    name: "a2a_discover",
    description:
      "Search the A2A registry for agents and skills. Returns agent ids, endpoints, skill descriptions, and the trust policy (minTier, requiresApproval) for each skill.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Free-text match over skills/agents" },
        skill: { type: "string", description: "Exact skill id" },
        tag: { type: "string", description: "Skill tag" },
      },
    },
  },
  {
    name: "a2a_send_task",
    description:
      "Delegate a task to another agent over A2A (SendMessage). Set skill via the target agent's card (see a2a_discover). To continue a paused task (input-required / auth-required), pass taskId. Non-blocking by default: poll with a2a_task_status.",
    inputSchema: {
      type: "object",
      required: ["agent", "text"],
      properties: {
        agent: { type: "string", description: "Target agent id, e.g. qubit" },
        text: { type: "string", description: "Task message text" },
        skill: { type: "string", description: "Skill id (metadata dev.dsect.skill)" },
        taskId: { type: "string", description: "Continue this existing task" },
        contextId: { type: "string" },
        data: { type: "object", description: "Optional structured data part" },
        blocking: { type: "boolean", description: "Wait for terminal/paused state" },
      },
    },
  },
  {
    name: "a2a_task_status",
    description: "Get an A2A task's current state, history tail, and artifacts.",
    inputSchema: {
      type: "object",
      required: ["taskId"],
      properties: { taskId: { type: "string" } },
    },
  },
  {
    name: "a2a_inbox",
    description:
      "List YOUR agent's queued hosted-inbox tasks (tasks other agents delegated to you that are waiting for your response).",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "a2a_respond",
    description:
      "Complete one of your inbox tasks: attaches your text as the result artifact and marks the task completed.",
    inputSchema: {
      type: "object",
      required: ["taskId", "text"],
      properties: { taskId: { type: "string" }, text: { type: "string" } },
    },
  },
  {
    name: "a2a_approve",
    description:
      "Fulfill (or deny) an auth-required approval on a task. Only honored from Scotty or an agent holding his recorded delegation (scope a2a:approve); the executing agent can never approve its own work.",
    inputSchema: {
      type: "object",
      required: ["taskId", "decision"],
      properties: {
        taskId: { type: "string" },
        decision: { type: "string", enum: ["approved", "denied"] },
        note: { type: "string" },
      },
    },
  },
];

function textResult(obj) {
  return { content: [{ type: "text", text: JSON.stringify(obj, null, 2) }] };
}

export async function handleMcp(core, registry, principal, body) {
  const { id, method, params } = body ?? {};
  if (method === "initialize") {
    return {
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: params?.protocolVersion ?? "2025-03-26",
        capabilities: { tools: {} },
        serverInfo: { name: "a2a-gateway", version: "0.1.0" },
      },
    };
  }
  if (method === "ping") return { jsonrpc: "2.0", id, result: {} };
  if (method?.startsWith("notifications/")) return null; // accepted, no reply
  if (method === "tools/list") return { jsonrpc: "2.0", id, result: { tools: TOOLS } };
  if (method === "tools/call") {
    try {
      const result = await callTool(core, registry, principal, params?.name, params?.arguments ?? {});
      return { jsonrpc: "2.0", id, result };
    } catch (e) {
      return {
        jsonrpc: "2.0",
        id,
        result: {
          content: [{ type: "text", text: `Error: ${e.message}` }],
          isError: true,
        },
      };
    }
  }
  return {
    jsonrpc: "2.0",
    id,
    error: { code: -32601, message: `method not found: ${method}` },
  };
}

async function callTool(core, registry, principal, name, args) {
  switch (name) {
    case "a2a_discover":
      return textResult(registry.search(args));
    case "a2a_send_task": {
      const message = {
        messageId: `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
        role: "ROLE_USER",
        parts: [{ text: args.text }, ...(args.data ? [{ data: args.data }] : [])],
        ...(args.taskId ? { taskId: args.taskId } : {}),
        ...(args.contextId ? { contextId: args.contextId } : {}),
        metadata: { ...(args.skill ? { "dev.dsect.skill": args.skill } : {}) },
      };
      const task = await core.sendMessage(principal, args.agent, { message }, { blocking: !!args.blocking });
      return textResult(task);
    }
    case "a2a_task_status": {
      const task = core.tasks.get(args.taskId);
      if (!task) throw new RpcError(-32001, `task not found: ${args.taskId}`);
      return textResult(core.getTask(principal, task.agentId, { id: args.taskId, historyLength: 10 }));
    }
    case "a2a_inbox":
      return textResult(core.inboxTasks(principal));
    case "a2a_respond":
      return textResult(core.respondInbox(principal, args.taskId, args.text));
    case "a2a_approve": {
      const task = core.tasks.get(args.taskId);
      if (!task) throw new RpcError(-32001, `task not found: ${args.taskId}`);
      const message = {
        messageId: `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
        role: "ROLE_USER",
        parts: [{ text: args.note ?? `Approval decision: ${args.decision}` }],
        taskId: args.taskId,
        contextId: task.contextId,
        metadata: {
          "dev.dsect.approval": { decision: args.decision, by: principal.agentId },
        },
      };
      const updated = await core.sendMessage(principal, task.agentId, { message });
      return textResult(updated);
    }
    default:
      throw new RpcError(-32601, `unknown tool: ${name}`);
  }
}
