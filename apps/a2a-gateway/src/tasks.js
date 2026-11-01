// Task store: lifecycle, history, artifacts, SSE subscribers, push
// notification fan-out. A2A 1.0 task shape:
//   { id, contextId, status: { state, message, timestamp },
//     artifacts: [], history: [], metadata }
// Terminal states refuse further messages (enforced in the dispatcher).
import crypto from "node:crypto";

export const TERMINAL = new Set([
  "TASK_STATE_COMPLETED",
  "TASK_STATE_FAILED",
  "TASK_STATE_CANCELED",
  "TASK_STATE_REJECTED",
]);

export function newTaskId() {
  return `task-${crypto.randomUUID()}`;
}
export function newContextId() {
  return `ctx-${crypto.randomUUID()}`;
}
export function newMessageId() {
  return `msg-${crypto.randomUUID()}`;
}

export function agentMessage(text, extra = {}) {
  return {
    messageId: newMessageId(),
    role: "ROLE_AGENT",
    parts: [{ text }],
    ...extra,
  };
}

export class TaskStore {
  constructor(store) {
    this.store = store;
    this.tasks = new Map();
    this.subscribers = new Map(); // taskId -> Set<(eventObj) => void>
    this.pushConfigs = new Map(); // taskId -> [config]
    this._loadPushConfigs();
  }

  _loadPushConfigs() {
    const saved = this.store.readJson("push-configs.json", {});
    for (const [taskId, cfgs] of Object.entries(saved)) this.pushConfigs.set(taskId, cfgs);
  }

  _savePushConfigs() {
    this.store.writeJson("push-configs.json", Object.fromEntries(this.pushConfigs));
  }

  create({ agentId, creator, contextId, skillId, metadata }) {
    const task = {
      id: newTaskId(),
      contextId: contextId ?? newContextId(),
      agentId, // target agent
      creator, // requesting agent id
      skillId: skillId ?? null,
      status: {
        state: "TASK_STATE_SUBMITTED",
        timestamp: new Date().toISOString(),
      },
      artifacts: [],
      history: [],
      metadata: metadata ?? {},
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    this.tasks.set(task.id, task);
    this._log(task, "created");
    return task;
  }

  get(id) {
    return this.tasks.get(id);
  }

  listFor(principal) {
    return [...this.tasks.values()].filter(
      (t) =>
        t.creator === principal.agentId ||
        t.agentId === principal.agentId ||
        principal.approver,
    );
  }

  visibleTo(task, principal) {
    return (
      task.creator === principal.agentId ||
      task.agentId === principal.agentId ||
      principal.approver === true
    );
  }

  addHistory(task, message) {
    task.history.push(message);
    task.updatedAt = new Date().toISOString();
    this._log(task, "history", { messageId: message.messageId, role: message.role });
  }

  transition(task, state, statusMessage) {
    task.status = {
      state,
      ...(statusMessage ? { message: statusMessage } : {}),
      timestamp: new Date().toISOString(),
    };
    task.updatedAt = task.status.timestamp;
    this._log(task, "transition", { state });
    if (typeof this.onTransition === "function") {
      try {
        this.onTransition(task);
      } catch {
        /* ledger hooks must never break the task flow */
      }
    }
    this.emit(task, { statusUpdate: { taskId: task.id, contextId: task.contextId, status: task.status, final: TERMINAL.has(state) } });
    if (TERMINAL.has(state)) this._closeSubscribers(task.id);
    return task;
  }

  addArtifact(task, artifact) {
    task.artifacts.push(artifact);
    task.updatedAt = new Date().toISOString();
    this._log(task, "artifact", { artifactId: artifact.artifactId, name: artifact.name });
    this.emit(task, {
      artifactUpdate: { taskId: task.id, contextId: task.contextId, artifact, lastChunk: true },
    });
    return task;
  }

  // ---- streaming subscribers (SSE) ----
  subscribe(taskId, fn) {
    if (!this.subscribers.has(taskId)) this.subscribers.set(taskId, new Set());
    this.subscribers.get(taskId).add(fn);
    return () => this.subscribers.get(taskId)?.delete(fn);
  }

  _closeSubscribers(taskId) {
    const set = this.subscribers.get(taskId);
    if (set) for (const fn of set) fn(null); // null = end of stream
    this.subscribers.delete(taskId);
  }

  emit(task, event) {
    const set = this.subscribers.get(task.id);
    if (set) for (const fn of set) fn(event);
    this._push(task, event);
  }

  // ---- push notification configs ----
  createPushConfig(taskId, { url, token, authentication }) {
    const cfg = {
      id: `push-${crypto.randomUUID()}`,
      taskId,
      url,
      ...(token ? { token } : {}),
      ...(authentication ? { authentication } : {}),
    };
    const arr = this.pushConfigs.get(taskId) ?? [];
    arr.push(cfg);
    this.pushConfigs.set(taskId, arr);
    this._savePushConfigs();
    return cfg;
  }

  listPushConfigs(taskId) {
    return this.pushConfigs.get(taskId) ?? [];
  }

  getPushConfig(taskId, id) {
    return this.listPushConfigs(taskId).find((c) => c.id === id);
  }

  deletePushConfig(taskId, id) {
    const arr = this.listPushConfigs(taskId).filter((c) => c.id !== id);
    this.pushConfigs.set(taskId, arr);
    this._savePushConfigs();
  }

  async _push(task, event) {
    const cfgs = this.pushConfigs.get(task.id) ?? [];
    for (const cfg of cfgs) {
      try {
        const headers = { "content-type": "application/json" };
        // The server MUST include the configured credentials in the call.
        const cred = cfg.authentication?.credentials ?? cfg.token;
        if (cred) headers.authorization = `Bearer ${cred}`;
        await fetch(cfg.url, {
          method: "POST",
          headers,
          body: JSON.stringify({ task: this.publicTask(task), event }),
        });
      } catch (e) {
        this._log(task, "push-error", { url: cfg.url, error: String(e.message ?? e) });
      }
    }
  }

  /** Wire shape: the internal record minus gateway bookkeeping fields. */
  publicTask(task, { historyLength } = {}) {
    const { creator, skillId, ...rest } = task;
    const history =
      historyLength && historyLength > 0 ? task.history.slice(-historyLength) : task.history;
    return {
      ...rest,
      history,
      metadata: {
        ...(task.metadata ?? {}),
        "dev.dsect.agent": task.agentId,
        ...(skillId ? { "dev.dsect.skill": skillId } : {}),
      },
    };
  }

  _log(task, kind, extra = {}) {
    this.store.appendJsonl("task-events.jsonl", {
      at: new Date().toISOString(),
      taskId: task.id,
      contextId: task.contextId,
      agentId: task.agentId,
      creator: task.creator,
      kind,
      ...extra,
    });
  }
}
