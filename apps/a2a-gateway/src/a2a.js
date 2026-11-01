// Gateway core: A2A 1.0 JSON-RPC semantics for our profile, shared by the
// HTTP JSON-RPC endpoint and the MCP facade. Methods (profile v0.1):
//   SendMessage, SendStreamingMessage, GetTask, ListTasks, CancelTask,
//   SubscribeToTask, CreateTaskPushNotificationConfig,
//   GetTaskPushNotificationConfig, ListTaskPushNotificationConfigs,
//   DeleteTaskPushNotificationConfig, GetExtendedAgentCard.
// Skill selection rides in message metadata: { "dev.dsect.skill": "<id>" }
// (profile extension; the wire card stays vanilla).
import { agentMessage, TERMINAL } from "./tasks.js";
import { checkInvoke, checkMessageSize, checkApproval } from "./policy.js";

export class RpcError extends Error {
  constructor(code, message, data) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

const ERR = {
  invalidParams: (m) => new RpcError(-32602, m),
  taskNotFound: (id) => new RpcError(-32001, `task not found: ${id}`),
  taskNotCancelable: (id) => new RpcError(-32002, `task not cancelable: ${id}`),
  unsupported: (m) => new RpcError(-32004, m),
  extendedCardNotConfigured: () =>
    new RpcError(-32007, "authenticated extended Agent Card is not configured in profile v0.1"),
};

export class GatewayCore {
  constructor({ config, registry, tasks, ledger, adapters, rateLimiter }) {
    this.config = config;
    this.registry = registry;
    this.tasks = tasks;
    this.ledger = ledger;
    this.adapters = adapters; // Map agentId -> adapter
    this.rateLimiter = rateLimiter;
    // Ledger mirrors meaningful transitions only (guard inside Ledger).
    this.tasks.onTransition = (task) => {
      Promise.resolve(this.ledger.taskTransition(task)).catch(() => {});
    };
  }

  _agent(agentId) {
    const rec = this.registry.get(agentId);
    if (!rec) throw ERR.invalidParams(`unknown agent: ${agentId}`);
    return rec;
  }

  _adapter(agentId) {
    const ad = this.adapters.get(agentId);
    if (!ad) throw ERR.unsupported(`agent ${agentId} has no live adapter on this gateway`);
    return ad;
  }

  // ---------- SendMessage ----------
  async sendMessage(principal, agentId, params, { blocking = false } = {}) {
    const rec = this._agent(agentId);
    const message = params?.message;
    if (!message || !Array.isArray(message.parts)) throw ERR.invalidParams("message.parts required");
    checkMessageSize(principal, JSON.stringify(message).length, this.config);

    if (message.taskId) {
      const { task, done } = await this._continue(principal, rec, message);
      if (blocking) await done;
      return this.tasks.publicTask(task);
    }

    const { task, done } = await this._start(principal, rec, message, params);
    if (blocking || params?.configuration?.blocking) await done;
    return this.tasks.publicTask(task);
  }

  async _start(principal, rec, message, params) {
    this.rateLimiter.check(principal);
    const skillId =
      message.metadata?.["dev.dsect.skill"] ??
      params?.metadata?.["dev.dsect.skill"] ??
      (rec.card.skills.length === 1 ? rec.card.skills[0].id : null);
    if (!skillId)
      throw ERR.invalidParams("skill required: set message metadata dev.dsect.skill");
    const skillMeta = checkInvoke(principal, rec, skillId, this.config);
    const task = this.tasks.create({
      agentId: rec.agentId,
      creator: principal.agentId,
      contextId: message.contextId ?? params?.contextId,
      skillId,
      metadata: { ...(params?.metadata ?? {}), ...(message.metadata ?? {}) },
    });
    this.tasks.addHistory(task, message);
    const ref = await this.ledger.taskCreated(task);
    if (ref.trkId) task.metadata["dev.dsect.tracker"] = { trkId: ref.trkId };
    task.metadata["dev.dsect.hive"] = { contextRef: task.contextId };
    const adapter = this._adapter(rec.agentId);
    const done = Promise.resolve(
      adapter.deliver({ task, principal, skillMeta, approved: false }),
    ).catch((e) => {
      if (!TERMINAL.has(task.status.state)) {
        this.tasks.transition(
          task,
          "TASK_STATE_FAILED",
          agentMessage(`Adapter failure: ${String(e.message ?? e)}`, {
            taskId: task.id,
            contextId: task.contextId,
          }),
        );
      }
    });
    return { task, done };
  }

  async _continue(principal, rec, message) {
    const task = this.tasks.get(message.taskId);
    if (!task || task.agentId !== rec.agentId || !this.tasks.visibleTo(task, principal))
      throw ERR.taskNotFound(message.taskId);
    if (TERMINAL.has(task.status.state))
      throw ERR.invalidParams(`task ${task.id} is in terminal state ${task.status.state}`);
    const skillMeta = rec.skillMeta[task.skillId] ?? { minTier: 3, requiresApproval: false };
    this.tasks.addHistory(task, message);

    const approval = message.metadata?.["dev.dsect.approval"];
    if (task.status.state === "TASK_STATE_AUTH_REQUIRED") {
      if (approval?.decision === "approved") {
        if (!checkApproval(principal, task)) {
          this.tasks.transition(
            task,
            "TASK_STATE_AUTH_REQUIRED",
            agentMessage(
              `Approval by ${principal.agentId} NOT honored: approvals resolve only to Scotty or an agent holding his recorded delegation (scope a2a:approve), and never to the executing agent.`,
              { taskId: task.id, contextId: task.contextId },
            ),
          );
          return { task, done: Promise.resolve() };
        }
        const done = Promise.resolve(
          this._adapter(rec.agentId).continue({ task, principal, skillMeta, approved: true }),
        );
        return { task, done };
      }
      if (approval?.decision === "denied" && checkApproval(principal, task)) {
        this.tasks.transition(
          task,
          "TASK_STATE_REJECTED",
          agentMessage(`Approval denied by ${principal.agentId}. Task rejected.`, {
            taskId: task.id,
            contextId: task.contextId,
          }),
        );
        return { task, done: Promise.resolve() };
      }
      // Ordinary chatter while paused: recorded, does not resume work.
      return { task, done: Promise.resolve() };
    }

    const done = Promise.resolve(
      this._adapter(rec.agentId).continue({ task, principal, skillMeta, approved: false }),
    ).catch((e) => {
      if (!TERMINAL.has(task.status.state)) {
        this.tasks.transition(
          task,
          "TASK_STATE_FAILED",
          agentMessage(`Adapter failure on continue: ${String(e.message ?? e)}`, {
            taskId: task.id,
            contextId: task.contextId,
          }),
        );
      }
    });
    return { task, done };
  }

  // ---------- Streaming ----------
  /**
   * Runs a streaming send or subscribe. `sink(event)` receives stream
   * events ({task} first for new sends, then {statusUpdate}/{artifactUpdate});
   * sink(null) ends the stream. Returns when the stream closes.
   */
  async stream(principal, agentId, params, sink, { subscribeOnly = false } = {}) {
    const rec = this._agent(agentId);
    let task;
    let done = Promise.resolve();
    if (subscribeOnly) {
      task = this.tasks.get(params?.id);
      if (!task || task.agentId !== rec.agentId || !this.tasks.visibleTo(task, principal))
        throw ERR.taskNotFound(params?.id);
    } else {
      const message = params?.message;
      if (!message) throw ERR.invalidParams("message required");
      if (message.taskId) {
        ({ task, done } = await this._continue(principal, rec, message));
      } else {
        ({ task, done } = await this._start(principal, rec, message, params));
      }
    }
    sink({ task: this.tasks.publicTask(task) });
    if (TERMINAL.has(task.status.state)) {
      sink(null);
      return;
    }
    await new Promise((resolve) => {
      const unsub = this.tasks.subscribe(task.id, (event) => {
        if (event === null) {
          unsub();
          sink(null);
          resolve();
          return;
        }
        sink(event);
        if (event.statusUpdate?.final) {
          unsub();
          sink(null);
          resolve();
        }
      });
      // Safety: if the adapter finished between the terminal check and the
      // subscription, close out.
      if (TERMINAL.has(task.status.state)) {
        unsub();
        sink(null);
        resolve();
      }
      void done;
    });
  }

  // ---------- Queries ----------
  getTask(principal, agentId, params) {
    const rec = this._agent(agentId);
    const task = this.tasks.get(params?.id);
    if (!task || task.agentId !== rec.agentId || !this.tasks.visibleTo(task, principal))
      throw ERR.taskNotFound(params?.id);
    return this.tasks.publicTask(task, { historyLength: params?.historyLength });
  }

  listTasks(principal, agentId, params = {}) {
    const rec = this._agent(agentId);
    let all = this.tasks.listFor(principal).filter((t) => t.agentId === rec.agentId);
    if (params.contextId) all = all.filter((t) => t.contextId === params.contextId);
    if (params.status) all = all.filter((t) => t.status.state === params.status);
    const pageSize = Math.min(params.pageSize ?? 50, 200);
    return {
      tasks: all.slice(0, pageSize).map((t) => this.tasks.publicTask(t)),
      totalSize: all.length,
      pageSize,
      nextPageToken: "",
    };
  }

  async cancelTask(principal, agentId, params) {
    const rec = this._agent(agentId);
    const task = this.tasks.get(params?.id);
    if (!task || task.agentId !== rec.agentId || !this.tasks.visibleTo(task, principal))
      throw ERR.taskNotFound(params?.id);
    if (TERMINAL.has(task.status.state)) throw ERR.taskNotCancelable(task.id);
    try {
      await this._adapter(rec.agentId).cancel?.({ task, principal });
    } catch {
      /* best effort */
    }
    this.tasks.transition(
      task,
      "TASK_STATE_CANCELED",
      agentMessage(`Canceled by ${principal.agentId}.`, {
        taskId: task.id,
        contextId: task.contextId,
      }),
    );
    return this.tasks.publicTask(task);
  }

  // ---------- Push notification configs ----------
  createPushConfig(principal, agentId, params) {
    const rec = this._agent(agentId);
    const task = this.tasks.get(params?.taskId);
    if (!task || task.agentId !== rec.agentId || !this.tasks.visibleTo(task, principal))
      throw ERR.taskNotFound(params?.taskId);
    if (!params?.url) throw ERR.invalidParams("push config url required");
    return this.tasks.createPushConfig(task.id, params);
  }

  getPushConfig(principal, agentId, params) {
    const rec = this._agent(agentId);
    const cfg = this.tasks.getPushConfig(params?.taskId, params?.id);
    if (!cfg) throw ERR.invalidParams(`push config not found: ${params?.id}`);
    return cfg;
  }

  listPushConfigs(principal, agentId, params) {
    const rec = this._agent(agentId);
    const task = this.tasks.get(params?.taskId);
    if (!task || task.agentId !== rec.agentId || !this.tasks.visibleTo(task, principal))
      throw ERR.taskNotFound(params?.taskId);
    return this.tasks.listPushConfigs(task.id);
  }

  deletePushConfig(principal, agentId, params) {
    const rec = this._agent(agentId);
    this.tasks.deletePushConfig(params?.taskId, params?.id);
    return {};
  }

  getExtendedAgentCard() {
    throw ERR.extendedCardNotConfigured();
  }

  // ---------- Facade helpers (MCP) ----------
  /** Agent-side inbox drain: queued tasks for the caller's own agent id. */
  inboxTasks(principal) {
    const adapter = this.adapters.get(principal.agentId);
    if (!adapter || typeof adapter.pending !== "function") return [];
    return adapter.pending().map((t) => this.tasks.publicTask(t));
  }

  /** Agent-side inbox completion (a2a_respond). */
  respondInbox(principal, taskId, text) {
    const adapter = this.adapters.get(principal.agentId);
    if (!adapter || typeof adapter.respond !== "function")
      throw ERR.unsupported(`${principal.agentId} has no inbox adapter`);
    const task = this.tasks.get(taskId);
    if (!task || task.agentId !== principal.agentId) throw ERR.taskNotFound(taskId);
    adapter.respond(task, text);
    return this.tasks.publicTask(task);
  }
}
