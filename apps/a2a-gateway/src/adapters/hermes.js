// Hermes adapter — the real receiving end for Qubit.
// Delivers A2A tasks into the LIVE Hermes gateway (the agent Scotty's
// fleet actually runs) through its OpenAI-compatible API, and turns the
// agent's work into A2A artifacts. Qubit does the work with its own
// tools; this adapter only translates protocols and enforces policy.
//
// Policy is re-checked HERE, at the receiving adapter, in addition to
// the gateway's check (defense in depth: a gateway bug must not become
// a skeleton key — docs/TRUST.md).
//
// The Hermes API_SERVER_KEY is read from a 0600 file at call time. It is
// never logged, never placed in a task, never committed.
import fs from "node:fs";
import path from "node:path";
import { agentMessage, TERMINAL } from "../tasks.js";
import { hasInvokeScope } from "../oidc.js";

const ALLOWLIST_HOME_FILES = ["AGENT_STANDARD.md", "SOUL.md"];
const NEEDS_INPUT = "[NEEDS-INPUT]";

export class HermesAdapter {
  constructor(config, tasks) {
    this.cfg = config.hermes;
    this.tasks = tasks;
    this.inflight = new Map(); // taskId -> AbortController
    this.chain = Promise.resolve(); // serialize work: one local 35B agent
    this.model = this.cfg.model;
  }

  _key() {
    if (!this.cfg.keyFile) throw new Error("A2A_HERMES_KEY_FILE not configured");
    return fs.readFileSync(this.cfg.keyFile, "utf8").trim();
  }

  async _resolveModel() {
    if (this.model) return this.model;
    const res = await fetch(`${this.cfg.apiBase}/v1/models`, {
      headers: { authorization: `Bearer ${this._key()}` },
    });
    if (!res.ok) throw new Error(`hermes /v1/models HTTP ${res.status}`);
    const body = await res.json();
    const ids = (body.data ?? []).map((m) => m.id).filter(Boolean);
    this.model = ids.find((i) => /qubit/i.test(i)) ?? ids[0] ?? undefined;
    return this.model;
  }

  deliver(ctx) {
    return this._enqueue(ctx, false);
  }

  continue(ctx) {
    return this._enqueue(ctx, true);
  }

  _enqueue(ctx, isContinue) {
    const run = this.chain.then(() => this._run(ctx, isContinue));
    // keep the chain alive even when a run throws
    this.chain = run.catch(() => {});
    return run;
  }

  async cancel({ task }) {
    this.inflight.get(task.id)?.abort();
  }

  async _run({ task, principal, skillMeta, approved }, isContinue) {
    const T = this.tasks;
    if (TERMINAL.has(task.status.state)) return;

    // --- adapter-side policy re-check (independent of the gateway's) ---
    if (principal.tier < skillMeta.minTier || !hasInvokeScope(principal, task.skillId)) {
      T.transition(
        task,
        "TASK_STATE_REJECTED",
        agentMessage(
          `Adapter policy re-check failed: tier/scope insufficient for ${task.skillId}.`,
          { taskId: task.id, contextId: task.contextId },
        ),
      );
      return;
    }

    // --- approval gate: pause BEFORE any work reaches the agent ---
    if (skillMeta.requiresApproval && !approved) {
      T.transition(
        task,
        "TASK_STATE_AUTH_REQUIRED",
        agentMessage(
          `Approval required before Qubit runs "${task.skillId}". An approver (Scotty, or an agent holding his recorded delegation — scope a2a:approve) must approve in-task; the executor cannot approve its own work.`,
          { taskId: task.id, contextId: task.contextId },
        ),
      );
      return;
    }

    // --- allowlist gate for gated-file-read (adapter-side, pre-agent) ---
    if (task.skillId === "gated-file-read") {
      const wanted = requestedPath(task);
      if (wanted && !ALLOWLIST_HOME_FILES.includes(wanted)) {
        T.transition(
          task,
          "TASK_STATE_REJECTED",
          agentMessage(
            `Requested file "${wanted}" is not on the adapter allowlist (${ALLOWLIST_HOME_FILES.join(", ")}). Rejected before any agent work.`,
            { taskId: task.id, contextId: task.contextId },
          ),
        );
        return;
      }
    }

    T.transition(
      task,
      "TASK_STATE_WORKING",
      agentMessage(
        isContinue ? "Resuming work on your answer." : `Qubit received the task (${task.skillId}). Working…`,
        { taskId: task.id, contextId: task.contextId },
      ),
    );

    try {
      const reply = await this._chat(task);
      if (TERMINAL.has(task.status.state)) return; // canceled mid-flight
      // An empty completion is a failure, never a silent success: the
      // agent's model backend can be down while its API still answers
      // (observed live: 0-token completions). fleet-brief is exempt —
      // its evidence is the file on disk, checked below.
      if (!reply && task.skillId !== "fleet-brief") {
        T.transition(
          task,
          "TASK_STATE_FAILED",
          agentMessage(
            "Hermes returned an empty completion (no content) — the agent's model backend appears unavailable. Failing honestly rather than completing with an empty artifact.",
            { taskId: task.id, contextId: task.contextId },
          ),
        );
        return;
      }
      if (reply.includes(NEEDS_INPUT)) {
        const question = reply.replaceAll(NEEDS_INPUT, "").trim();
        T.transition(
          task,
          "TASK_STATE_INPUT_REQUIRED",
          agentMessage(question, { taskId: task.id, contextId: task.contextId }),
        );
        return;
      }
      await this._completeWithSkillArtifact(task, reply);
    } catch (e) {
      if (TERMINAL.has(task.status.state)) return;
      T.transition(
        task,
        "TASK_STATE_FAILED",
        agentMessage(`Hermes adapter error: ${String(e.message ?? e)}`, {
          taskId: task.id,
          contextId: task.contextId,
        }),
      );
    }
  }

  /** One streamed chat-completions call to the live Hermes gateway. */
  async _chat(task) {
    const model = await this._resolveModel();
    const controller = new AbortController();
    this.inflight.set(task.id, controller);
    const timer = setTimeout(() => controller.abort(), this.cfg.timeoutMs);
    let heartbeat;
    try {
      const res = await fetch(`${this.cfg.apiBase}/v1/chat/completions`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${this._key()}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          ...(model ? { model } : {}),
          stream: true,
          messages: [
            { role: "system", content: systemPrompt(task) },
            { role: "user", content: userPrompt(task, this.cfg) },
          ],
        }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`hermes chat HTTP ${res.status}: ${(await res.text().catch(() => "")).slice(0, 200)}`);
      }
      // Working heartbeats so SSE subscribers see a live agent, not a hang.
      const started = Date.now();
      heartbeat = setInterval(() => {
        if (!TERMINAL.has(task.status.state)) {
          this.tasks.transition(
            task,
            "TASK_STATE_WORKING",
            agentMessage(`Qubit is working… (${Math.round((Date.now() - started) / 1000)}s)`, {
              taskId: task.id,
              contextId: task.contextId,
            }),
          );
        }
      }, 30000);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let content = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 1);
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trim();
          if (data === "[DONE]") continue;
          try {
            const chunk = JSON.parse(data);
            const delta = chunk.choices?.[0]?.delta ?? chunk.choices?.[0]?.message ?? {};
            const c = delta.content;
            if (typeof c === "string") content += c;
            else if (Array.isArray(c)) {
              for (const part of c) if (typeof part?.text === "string") content += part.text;
            }
          } catch {
            /* partial frame — ignore */
          }
        }
      }
      return content.trim();
    } finally {
      clearTimeout(timer);
      clearInterval(heartbeat);
      this.inflight.delete(task.id);
    }
  }

  async _completeWithSkillArtifact(task, reply) {
    const T = this.tasks;
    const short = task.id.slice(5, 13);
    if (task.skillId === "public-status") {
      let parsed = null;
      const m = reply.match(/\{[\s\S]*\}/);
      if (m) {
        try {
          parsed = JSON.parse(m[0]);
        } catch {
          parsed = null;
        }
      }
      const names = Array.isArray(parsed?.names) ? parsed.names : [];
      const total = typeof parsed?.total === "number" ? parsed.total : names.length;
      T.addArtifact(task, {
        artifactId: `art-${short}`,
        name: `host-status-${short}.md`,
        parts: [
          {
            text: `# Host status (via Qubit)\n\n${total} containers running${names.length ? `:\n\n${names.map((n) => `- ${n}`).join("\n")}` : "."}\n`,
          },
        ],
      });
      T.transition(task, "TASK_STATE_COMPLETED");
      return;
    }

    if (task.skillId === "fleet-brief") {
      const rel = path.posix.join("a2a", `${task.id}.md`);
      const hostPath = path.join(this.cfg.workspaceDir, rel);
      let fileText = null;
      if (fs.existsSync(hostPath)) fileText = fs.readFileSync(hostPath, "utf8");
      if (fileText === null) {
        // One targeted retry: ask Qubit to write the exact file now.
        const retry = await this._chatRaw(task, [
          {
            role: "user",
            content:
              `The brief file was not found at workspace path ${rel}. ` +
              `Write the brief you just produced to that exact file now (create directories as needed), then reply with only the word WROTE.`,
          },
        ]).catch(() => "");
        if (fs.existsSync(hostPath)) fileText = fs.readFileSync(hostPath, "utf8");
        void retry;
      }
      if (fileText === null) {
        T.transition(
          task,
          "TASK_STATE_FAILED",
          agentMessage(
            `Qubit replied but the artifact file ${rel} was not written; failing honestly rather than presenting an unverifiable artifact. Reply excerpt: ${reply.slice(0, 300)}`,
            { taskId: task.id, contextId: task.contextId },
          ),
        );
        return;
      }
      T.addArtifact(task, {
        artifactId: `art-${short}`,
        name: `fleet-brief-${short}.md`,
        description: "Brief written by Qubit to its workspace; verified on disk by the adapter.",
        parts: [
          { file: { name: `fleet-brief-${short}.md`, mediaType: "text/markdown", fileWithUri: `file://${hostPath}` } },
          { text: fileText },
        ],
      });
      T.transition(task, "TASK_STATE_COMPLETED");
      return;
    }

    if (task.skillId === "gated-file-read") {
      T.addArtifact(task, {
        artifactId: `art-${short}`,
        name: `file-summary-${short}.md`,
        parts: [{ text: reply }],
      });
      T.transition(task, "TASK_STATE_COMPLETED");
      return;
    }

    // Generic completion: the reply itself is the artifact.
    T.addArtifact(task, {
      artifactId: `art-${short}`,
      name: `result-${short}.md`,
      parts: [{ text: reply }],
    });
    T.transition(task, "TASK_STATE_COMPLETED");
  }

  /** Non-streaming helper for short follow-up calls (retry writes). */
  async _chatRaw(task, extraMessages) {
    const model = await this._resolveModel();
    const res = await fetch(`${this.cfg.apiBase}/v1/chat/completions`, {
      method: "POST",
      headers: { authorization: `Bearer ${this._key()}`, "content-type": "application/json" },
      body: JSON.stringify({
        ...(model ? { model } : {}),
        messages: [
          { role: "system", content: systemPrompt(task) },
          { role: "user", content: userPrompt(task, this.cfg) },
          ...extraMessages,
        ],
      }),
    });
    if (!res.ok) throw new Error(`hermes chat HTTP ${res.status}`);
    const body = await res.json();
    return (body.choices?.[0]?.message?.content ?? "").trim();
  }
}

function historyText(task) {
  return task.history
    .map((m) => {
      const text = (m.parts ?? []).map((p) => p.text ?? "").filter(Boolean).join("\n");
      const data = (m.parts ?? []).find((p) => p.data)?.data;
      return `${m.role === "ROLE_AGENT" ? "Agent" : "Client"}: ${text}${data ? `\n[structured data: ${JSON.stringify(data)}]` : ""}`;
    })
    .join("\n");
}

function requestedPath(task) {
  for (const m of task.history) {
    for (const p of m.parts ?? []) {
      if (p.data?.path) return p.data.path;
      const hit = (p.text ?? "").match(/[\w.-]+\.md/);
      if (hit) return hit[0];
    }
  }
  return null;
}

function systemPrompt(task) {
  return [
    `You are Qubit, a Team Quantum fleet agent. You are executing a delegated task received over the A2A protocol (task ${task.id}, skill ${task.skillId}).`,
    `Do the work with your own tools and report results faithfully. If — and only if — you genuinely cannot proceed without information only the requester has, reply with the marker ${NEEDS_INPUT} followed by one precise question, and nothing else.`,
    `Never invent output: if a tool fails, say so plainly.`,
  ].join("\n");
}

function userPrompt(task, cfg) {
  const convo = historyText(task);
  switch (task.skillId) {
    case "public-status":
      return [
        `Conversation so far:\n${convo}`,
        `Task: report what is running on this host. Run exactly this command with your terminal tool: docker ps --format '{{.Names}}'`,
        `Then reply with ONLY a JSON object of the form {"total": <number>, "names": [<container names>]}. No other text.`,
      ].join("\n\n");
    case "fleet-brief": {
      const rel = `a2a/${task.id}.md`;
      // Field lesson (2026-10-25, two live attempts): Qubit's API turns
      // end early on long multi-step gathering — the agent narrated its
      // fact-finding and the turn closed before the file was written.
      // This prompt is therefore deliberately lean: two commands, then
      // the file write is the deliverable, narration forbidden.
      return [
        `Conversation so far:\n${convo}`,
        `Task: produce a SHORT fleet status brief. Work in as few steps as possible — do not narrate between steps, act.`,
        `Step 1: run exactly these two commands: (a) uptime (b) cat host-status.json 2>/dev/null || echo no-host-status-file. Do NOT run docker — the daemon is not reachable from inside your container.`,
        `Step 2: IMMEDIATELY write the brief as markdown (max 150 words, only facts you actually observed in step 1) to the file ${rel} inside your workspace (create the a2a directory if needed).`,
        `Step 3: reply with the brief text only. The file in step 2 is the deliverable — if you run low on steps, write the file first and skip the reply text.`,
      ].join("\n\n");
    }
    case "gated-file-read": {
      const wanted = requestedPath(task) ?? "AGENT_STANDARD.md";
      const allowed = ALLOWLIST_HOME_FILES.includes(wanted);
      return [
        `Conversation so far:\n${convo}`,
        allowed
          ? `Task (approved by a delegated approver): read the file ${wanted} in your home directory with your tools and reply with a faithful summary of at most 200 words. Quote one exact line from the file so the summary is verifiable.`
          : `Task: the requested file "${wanted}" is not allow-listed. Reply explaining that you cannot read it.`,
      ].join("\n\n");
    }
    default:
      return `Conversation so far:\n${convo}\n\nTask: complete the request described above (skill ${task.skillId}) and reply with the result.`;
  }
}
