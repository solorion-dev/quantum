// A small A2A 1.0 client for the fleet's JSON-RPC profile.
// fetch card -> (optionally) verify its JWS signature -> SendMessage /
// GetTask / ListTasks / CancelTask / SubscribeToTask (SSE) / push configs.
import { verifyCardSignature } from "./jws.js";

export class A2AError extends Error {
  constructor(message, code, data) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

let rpcSeq = 0;

export class A2AClient {
  /**
   * opts: { baseUrl (agent JSON-RPC endpoint), token (bearer) | tokenProvider,
   *         jwksUrl (gateway card-signing JWKS for signature verification) }
   */
  constructor(opts) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.token = opts.token ?? null;
    this.tokenProvider = opts.tokenProvider ?? null;
    this.jwksUrl = opts.jwksUrl ?? null;
    this._jwks = null;
  }

  async _bearer() {
    if (this.tokenProvider) return this.tokenProvider();
    return this.token;
  }

  async _headers(extra = {}) {
    const h = { "content-type": "application/json", "a2a-version": "1.0", ...extra };
    const t = await this._bearer();
    if (t) h.authorization = `Bearer ${t}`;
    return h;
  }

  /** Fetch the Agent Card from a well-known URL or an agent base URL. */
  async fetchCard(cardUrlOrBase) {
    const url = cardUrlOrBase.endsWith("agent-card.json")
      ? cardUrlOrBase
      : `${cardUrlOrBase.replace(/\/+$/, "")}/.well-known/agent-card.json`;
    const res = await fetch(url, { headers: await this._headers() });
    if (!res.ok) throw new A2AError(`card fetch failed: HTTP ${res.status}`, res.status);
    return res.json();
  }

  /** Verify a card's signatures against the gateway JWKS. Returns boolean. */
  async verifyCard(card) {
    if (!card.signatures?.length) return false;
    if (!this._jwks) {
      if (!this.jwksUrl) throw new Error("jwksUrl required to verify cards");
      const res = await fetch(this.jwksUrl);
      if (!res.ok) throw new A2AError(`jwks fetch failed: HTTP ${res.status}`, res.status);
      this._jwks = await res.json();
    }
    const byKid = new Map((this._jwks.keys ?? []).map((k) => [k.kid, k]));
    return card.signatures.every((sig) =>
      verifyCardSignature(card, sig, (kid) => byKid.get(kid)),
    );
  }

  async rpc(method, params, { stream = false } = {}) {
    const res = await fetch(this.baseUrl, {
      method: "POST",
      headers: await this._headers(stream ? { accept: "text/event-stream" } : {}),
      body: JSON.stringify({ jsonrpc: "2.0", id: ++rpcSeq, method, params }),
    });
    if (!res.ok && !stream)
      throw new A2AError(`HTTP ${res.status} from ${this.baseUrl}`, res.status);
    return res;
  }

  async call(method, params) {
    const res = await this.rpc(method, params);
    const body = await res.json().catch(() => null);
    if (!body) throw new A2AError("empty response", res.status);
    if (body.error) throw new A2AError(body.error.message, body.error.code, body.error.data);
    return body.result;
  }

  sendMessage(message, configuration) {
    return this.call("SendMessage", { message, configuration });
  }

  getTask(id, historyLength) {
    return this.call("GetTask", { id, historyLength });
  }

  listTasks(params = {}) {
    return this.call("ListTasks", params);
  }

  cancelTask(id) {
    return this.call("CancelTask", { id });
  }

  createPushConfig(config) {
    return this.call("CreateTaskPushNotificationConfig", config);
  }

  listPushConfigs(taskId) {
    return this.call("ListTaskPushNotificationConfigs", { taskId });
  }

  deletePushConfig(taskId, id) {
    return this.call("DeleteTaskPushNotificationConfig", { taskId, id });
  }

  /**
   * Streaming send: yields parsed stream events
   * ({task} | {message} | {statusUpdate} | {artifactUpdate} shapes as sent
   * by the server inside JSON-RPC result payloads).
   */
  async *sendStreaming(message, configuration) {
    const res = await this.rpc("SendStreamingMessage", { message, configuration }, { stream: true });
    yield* parseSseJsonRpc(res);
  }

  /** Subscribe to an existing task's stream. */
  async *subscribe(taskId) {
    const res = await this.rpc("SubscribeToTask", { id: taskId }, { stream: true });
    yield* parseSseJsonRpc(res);
  }
}

export async function* parseSseJsonRpc(res) {
  if (!res.body) throw new A2AError("no stream body", 0);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const dataLines = frame
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trim());
      if (!dataLines.length) continue;
      const payload = JSON.parse(dataLines.join(""));
      if (payload.error) throw new A2AError(payload.error.message, payload.error.code);
      yield payload.result;
    }
  }
}

export function textMessage({ text, contextId, taskId, metadata, role = "ROLE_USER" }) {
  return {
    messageId: `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`,
    role,
    parts: [{ text }],
    ...(contextId ? { contextId } : {}),
    ...(taskId ? { taskId } : {}),
    ...(metadata ? { metadata } : {}),
  };
}

export function messageText(message) {
  if (!message?.parts) return "";
  return message.parts.map((p) => p.text ?? "").filter(Boolean).join("\n");
}

export function taskArtifactsText(task) {
  const out = [];
  for (const a of task?.artifacts ?? []) {
    for (const p of a.parts ?? []) if (p.text) out.push(p.text);
  }
  return out.join("\n");
}
