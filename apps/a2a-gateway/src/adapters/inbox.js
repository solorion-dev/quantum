// Hosted-inbox adapter — for agents that sleep, roam, or run in sessions
// (Cooper is the archetype). The gateway accepts the task, marks it
// WORKING/queued, and holds it in the agent's inbox. The agent drains its
// inbox through the MCP facade (a2a_inbox) and completes tasks with
// a2a_respond. This is the survey's hosted-endpoint pattern, implemented
// honestly: delivery is queued, never faked as synchronous execution.
import { agentMessage } from "../tasks.js";

export class InboxAdapter {
  constructor(store, tasks, agentId) {
    this.store = store;
    this.tasks = tasks;
    this.agentId = agentId;
    this.key = `inbox-${agentId}.json`;
  }

  _queue() {
    return this.store.readJson(this.key, []);
  }

  _saveQueue(q) {
    this.store.writeJson(this.key, q);
  }

  async deliver({ task }) {
    const q = this._queue();
    if (!q.includes(task.id)) q.push(task.id);
    this._saveQueue(q);
    this.tasks.transition(
      task,
      "TASK_STATE_WORKING",
      agentMessage(
        `Queued in ${this.agentId}'s A2A inbox. This agent works asynchronously (session-based); the task completes when the agent responds via its inbox.`,
        { taskId: task.id, contextId: task.contextId },
      ),
    );
  }

  async continue({ task }) {
    // Follow-up messages on an inbox task: history already appended by the
    // dispatcher; just (re)queue and note it.
    const q = this._queue();
    if (!q.includes(task.id)) q.push(task.id);
    this._saveQueue(q);
    this.tasks.transition(
      task,
      "TASK_STATE_WORKING",
      agentMessage(`Follow-up noted in ${this.agentId}'s inbox queue.`, {
        taskId: task.id,
        contextId: task.contextId,
      }),
    );
  }

  async cancel({ task }) {
    this._saveQueue(this._queue().filter((id) => id !== task.id));
  }

  /** Agent-side: list this agent's queued (WORKING, inbox-held) tasks. */
  pending() {
    return this._queue()
      .map((id) => this.tasks.get(id))
      .filter(Boolean)
      .filter((t) => t.status.state === "TASK_STATE_WORKING");
  }

  /** Agent-side: complete a queued task with an artifact (a2a_respond). */
  respond(task, text) {
    this._saveQueue(this._queue().filter((id) => id !== task.id));
    this.tasks.addArtifact(task, {
      artifactId: `art-${task.id.slice(5, 13)}`,
      name: `inbox-response-${task.id.slice(5, 13)}.md`,
      parts: [{ text }],
    });
    this.tasks.transition(task, "TASK_STATE_COMPLETED");
  }
}
