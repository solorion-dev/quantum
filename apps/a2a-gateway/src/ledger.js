// Ledger mirroring — the gateway's side-effect, never the agents' burden.
// Every task is mirrored to:
//   (a) the Tracker (one item per task, transitions as comments), and
//   (b) the Hive / Quantum Memory (a terminal-state summary memory).
// This is our pragmatic answer to cross-channel correlation: the whole
// exchange is reconstructible from the Tracker item alone.
// Mirroring is best-effort: failures are captured to ledger-errors.jsonl
// and NEVER fail the task itself. Successes land in ledger-map.json:
//   taskId -> { trkId, hiveId }
import { execFile } from "node:child_process";

function run(cmd, args, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, { timeout: timeoutMs }, (err, stdout, stderr) => {
      if (err) reject(new Error(`${cmd} ${args[0]} failed: ${stderr || err.message}`));
      else resolve(stdout);
    });
  });
}

export class Ledger {
  constructor(store, config) {
    this.store = store;
    this.config = config;
    this.map = new Map(Object.entries(store.readJson("ledger-map.json", {})));
    this.mcpSession = null;
    this.mcpSeq = 0;
  }

  _saveMap() {
    this.store.writeJson("ledger-map.json", Object.fromEntries(this.map));
  }

  _fail(taskId, where, error) {
    this.store.appendJsonl("ledger-errors.jsonl", {
      at: new Date().toISOString(),
      taskId,
      where,
      error: String(error?.message ?? error),
    });
  }

  ref(taskId) {
    return this.map.get(taskId) ?? {};
  }

  async taskCreated(task) {
    const ref = {};
    // --- Tracker ---
    try {
      const title = `A2A task ${task.id.slice(0, 13)}… ${task.skillId ?? "message"} → ${task.agentId}`;
      const body = [
        `A2A task mirrored from the a2a-gateway dev instance.`,
        `task: ${task.id}`,
        `context: ${task.contextId}`,
        `from: ${task.creator}  to: ${task.agentId}  skill: ${task.skillId ?? "(none)"}`,
        `epic: ${this.config.tracker.epicId}`,
      ].join("\n");
      const out = await run("python3", [
        this.config.tracker.cli,
        "add",
        "--kind",
        "task",
        "--status",
        "in_progress",
        "--parent",
        this.config.tracker.epicId,
        "--body",
        body,
        title,
      ]);
      const m = out.match(/TRK-\d+/);
      if (m) {
        ref.trkId = m[0];
      } else {
        this._fail(task.id, "tracker-add", new Error(`no TRK id in output: ${out.slice(0, 200)}`));
      }
    } catch (e) {
      this._fail(task.id, "tracker-add", e);
    }
    this.map.set(task.id, ref);
    this._saveMap();
    return ref;
  }

  async taskTransition(task) {
    // Mirror only meaningful transitions: repeated WORKING heartbeats
    // would spam the Tracker. State CHANGES and terminal states mirror.
    if (!this.lastState) this.lastState = new Map();
    const prev = this.lastState.get(task.id);
    if (prev === task.status.state && task.status.state === "TASK_STATE_WORKING") return;
    this.lastState.set(task.id, task.status.state);
    const ref = this.map.get(task.id) ?? {};
    if (ref.trkId) {
      try {
        await run("python3", [
          this.config.tracker.cli,
          "comment",
          ref.trkId,
          `A2A ${task.id}: → ${task.status.state}${task.status.message ? ` — ${truncate(textOf(task.status.message), 300)}` : ""}`,
        ]);
      } catch (e) {
        this._fail(task.id, "tracker-comment", e);
      }
    }
    const isTerminalState = ["TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"].includes(task.status.state);
    if (isTerminalState) {
      // Terminal ledgering must happen exactly once per task+state —
      // duplicate transition events (observed live) must not double-write.
      if (!this.terminalSeen) this.terminalSeen = new Set();
      const key = `${task.id}:${task.status.state}`;
      if (this.terminalSeen.has(key)) return;
      this.terminalSeen.add(key);
      await this._hiveSummary(task, ref);
      if (ref.trkId) {
        try {
          await run("python3", [
            this.config.tracker.cli,
            "set",
            ref.trkId,
            "--status",
            task.status.state === "TASK_STATE_COMPLETED" ? "done" : "blocked",
          ]);
        } catch (e) {
          this._fail(task.id, "tracker-set", e);
        }
      }
    }
  }

  async _hiveSummary(task, ref) {
    if (!this.config.hive.enabled) return;
    const content = [
      `A2A task ${task.id} (${task.skillId ?? "message"}) from ${task.creator} to ${task.agentId} finished ${task.status.state}.`,
      `context ${task.contextId}; tracker ${ref.trkId ?? "unmirrored"}; artifacts: ${task.artifacts.map((a) => a.name ?? a.artifactId).join(", ") || "none"}.`,
      task.artifacts.length ? `Result excerpt: ${truncate(artifactText(task), 600)}` : "",
    ]
      .filter(Boolean)
      .join(" ");
    try {
      const id = await this._memoryCall("add_memory", {
        content,
        agent: "cooper",
        kind: "event",
        tier: "project",
        importance: 0.6,
        tags: ["a2a", "ledger", `agent:${task.agentId}`],
      });
      if (id) {
        ref.hiveId = id;
        this.map.set(task.id, ref);
        this._saveMap();
      }
    } catch (e) {
      this._fail(task.id, "hive-add", e);
      // Outbox: the summary is preserved even if the Hive write failed.
      this.store.appendJsonl("hive-outbox.jsonl", {
        at: new Date().toISOString(),
        taskId: task.id,
        content,
      });
    }
  }

  /** Minimal MCP client for the loopback Quantum Memory server. */
  async _memoryCall(tool, args, attempt = 0) {
    const url = this.config.hive.mcpUrl;
    const baseHeaders = { "content-type": "application/json", accept: "application/json, text/event-stream" };
    if (this.config.hive.tokenFile) {
      try {
        const { readFileSync } = await import("node:fs");
        baseHeaders.authorization = `Bearer ${readFileSync(this.config.hive.tokenFile, "utf8").trim()}`;
      } catch {
        /* token file unreadable — the call will fail and be outboxed */
      }
    }
    // The session header must be attached per-request from the CURRENT
    // session value — building headers once up front meant the
    // initialize-captured session never reached tools/call, and the
    // server answered every call "Session not found" (observed live).
    const post = async (body) => {
      const headers = { ...baseHeaders };
      if (this.mcpSession) headers["mcp-session-id"] = this.mcpSession;
      const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
      if (res.headers.get("mcp-session-id")) this.mcpSession = res.headers.get("mcp-session-id");
      const text = await res.text();
      if (!text.trim()) return {}; // e.g. 202 Accepted for notifications
      // Streamable-HTTP servers may answer with SSE framing.
      const dataLine = text
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trim())
        .pop();
      return JSON.parse(dataLine ?? text);
    };
    if (!this.mcpSession) {
      const init = await post({
        jsonrpc: "2.0",
        id: ++this.mcpSeq,
        method: "initialize",
        params: {
          protocolVersion: "2025-03-26",
          capabilities: {},
          clientInfo: { name: "a2a-gateway-ledger", version: "0.1" },
        },
      });
      if (init.error) throw new Error(`memory MCP initialize: ${init.error.message}`);
      await post({ jsonrpc: "2.0", method: "notifications/initialized" }).catch(() => {});
    }
    const res = await post({
      jsonrpc: "2.0",
      id: ++this.mcpSeq,
      method: "tools/call",
      params: { name: tool, arguments: args },
    });
    if (res.error) {
      // Stale/rejected session: drop it and retry the handshake once.
      if (attempt === 0 && /session/i.test(res.error.message ?? "")) {
        this.mcpSession = null;
        return this._memoryCall(tool, args, 1);
      }
      throw new Error(`memory MCP ${tool}: ${res.error.message}`);
    }
    const text = res.result?.content?.map((c) => c.text ?? "").join("") ?? "";
    if (res.result?.isError) throw new Error(`memory MCP ${tool} returned error: ${text.slice(0, 200)}`);
    try {
      const parsed = JSON.parse(text);
      return parsed.id ?? parsed.memory_id ?? text.slice(0, 60);
    } catch {
      return text.slice(0, 60) || true;
    }
  }
}

function textOf(message) {
  return (message?.parts ?? []).map((p) => p.text ?? "").filter(Boolean).join(" ");
}

function artifactText(task) {
  return task.artifacts
    .flatMap((a) => (a.parts ?? []).map((p) => p.text ?? ""))
    .filter(Boolean)
    .join("\n");
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
