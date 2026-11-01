// a2a-gateway — dev instance bootstrap.
// Binds the configured host (tailnet IP by default): NO public listener,
// no Cloudflare involvement. Exposure changes are M4/M5 decisions.
import http from "node:http";
import { loadConfig } from "./config.js";
import { StateStore } from "./state.js";
import { OidcVerifier } from "./oidc.js";
import { DevIdp } from "./devidp.js";
import { Registry } from "./registry.js";
import { TaskStore } from "./tasks.js";
import { Ledger } from "./ledger.js";
import { GatewayCore, RpcError } from "./a2a.js";
import { RateLimiter } from "./policy.js";
import { HermesAdapter } from "./adapters/hermes.js";
import { InboxAdapter } from "./adapters/inbox.js";
import { handleMcp } from "./mcp.js";
import {
  generateRsaKeyPairPem,
  publicJwkFromPrivate,
} from "../../../packages/a2a/src/jws.js";

const config = loadConfig();
const store = new StateStore(config.stateDir);

// --- card signing key (gateway's own; public half served as JWKS) ---
if (!store.exists("card-signing-key.pem")) {
  store.writeText("card-signing-key.pem", generateRsaKeyPairPem().privatePem, 0o600);
}
const cardKeyPem = store.readText("card-signing-key.pem");
const cardKid = "gateway-cards-1";
const cardJwk = publicJwkFromPrivate(cardKeyPem, cardKid);

// --- identity: real issuer(s) + optional dev issuer ---
const verifier = new OidcVerifier(config.trustedIssuers);
let devIdp = null;
if (config.devIdp.enabled) {
  const issuer = `${config.baseUrl}${config.devIdp.issuerPath}`;
  devIdp = new DevIdp(store, issuer);
  verifier.addIssuer(issuer, `${issuer}/jwks.json`, async () => devIdp.jwks());
}

// --- domain objects ---
const registry = new Registry(store, config, { privatePem: cardKeyPem, kid: cardKid });
const tasks = new TaskStore(store);
const ledger = new Ledger(store, config);
const adapters = new Map();
adapters.set("qubit", new HermesAdapter(config, tasks));
adapters.set("cooper", new InboxAdapter(store, tasks, "cooper"));
adapters.set("bookkeeper", new InboxAdapter(store, tasks, "bookkeeper"));
const core = new GatewayCore({
  config,
  registry,
  tasks,
  ledger,
  adapters,
  rateLimiter: new RateLimiter(config.limits.perMinute),
});

// --- HTTP plumbing ---
function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(body) });
  res.end(body);
}

async function readBody(req, cap = 2 * 1024 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > cap) throw Object.assign(new Error("body too large"), { status: 413 });
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function principal(req) {
  const auth = req.headers.authorization ?? "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : null;
  return verifier.validate(token);
}

function rpcErrorBody(id, e) {
  if (e instanceof RpcError) return { code: e.code, message: e.message, data: e.data };
  if (e.rpcCode) return { code: e.rpcCode, message: e.message };
  return { code: -32603, message: String(e.message ?? e) };
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, config.baseUrl);
  const path = url.pathname;
  try {
    // ---- T0 surfaces (no auth): health, card JWKS, cards, registry ----
    if (req.method === "GET" && path === "/health") {
      const probes = {};
      for (const iss of verifier.issuers.keys()) probes[iss] = await verifier.probeIssuer(iss);
      return sendJson(res, 200, {
        ok: true,
        service: "a2a-gateway",
        profile: "0.1",
        baseUrl: config.baseUrl,
        agents: registry.list().map((a) => a.agentId),
        devIdp: !!devIdp,
        issuers: probes,
      });
    }
    if (req.method === "GET" && path === "/.well-known/jwks.json") {
      return sendJson(res, 200, { keys: [cardJwk] });
    }
    if (req.method === "GET" && path === "/registry/agents") {
      return sendJson(res, 200, { agents: registry.publicList() });
    }
    const cardMatch = path.match(/^\/agents\/([\w-]+)\/\.well-known\/agent-card\.json$/);
    if (req.method === "GET" && cardMatch) {
      const rec = registry.get(cardMatch[1]);
      if (!rec) return sendJson(res, 404, { error: "unknown agent" });
      return sendJson(res, 200, rec.card);
    }
    const regMatch = path.match(/^\/registry\/agents\/([\w-]+)$/);
    if (req.method === "GET" && regMatch) {
      const rec = registry.get(regMatch[1]);
      if (!rec) return sendJson(res, 404, { error: "unknown agent" });
      return sendJson(res, 200, { agentId: rec.agentId, card: rec.card });
    }

    // ---- dev issuer (dev instance only) ----
    if (devIdp && path.startsWith(config.devIdp.issuerPath)) {
      if (req.method === "GET" && path === `${config.devIdp.issuerPath}/.well-known/openid-configuration`)
        return sendJson(res, 200, devIdp.discovery());
      if (req.method === "GET" && path === `${config.devIdp.issuerPath}/jwks.json`)
        return sendJson(res, 200, devIdp.jwks());
      if (req.method === "POST" && path === `${config.devIdp.issuerPath}/token`) {
        const body = JSON.parse((await readBody(req)) || "{}");
        try {
          const token = devIdp.mint(body.identity, body.secret);
          return sendJson(res, 200, { access_token: token, token_type: "Bearer", expires_in: 3600 });
        } catch (e) {
          return sendJson(res, 401, { error: String(e.message ?? e) });
        }
      }
    }

    // ---- authenticated surfaces ----
    const agentMatch = path.match(/^\/agents\/([\w-]+)$/);
    if (req.method === "POST" && agentMatch) {
      const agentId = agentMatch[1];
      let who;
      try {
        who = await principal(req);
      } catch (e) {
        return sendJson(res, e.status ?? 401, { jsonrpc: "2.0", id: null, error: { code: -32009, message: e.message } });
      }
      const raw = await readBody(req);
      let body;
      try {
        body = JSON.parse(raw);
      } catch {
        return sendJson(res, 400, { jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } });
      }
      const { id, method, params } = body;
      // Streaming methods open an SSE response.
      if (method === "SendStreamingMessage" || method === "SubscribeToTask") {
        res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache", connection: "keep-alive" });
        const sink = (event) => {
          // A disconnected SSE client must never break task processing:
          // writes to a dead response are swallowed here.
          try {
            if (event === null) {
              res.end();
              return;
            }
            res.write(`data: ${JSON.stringify({ jsonrpc: "2.0", id, result: event })}\n\n`);
          } catch {
            /* client gone */
          }
        };
        try {
          await core.stream(who, agentId, params, sink, { subscribeOnly: method === "SubscribeToTask" });
        } catch (e) {
          res.write(`data: ${JSON.stringify({ jsonrpc: "2.0", id, error: rpcErrorBody(id, e) })}\n\n`);
          res.end();
        }
        return;
      }
      try {
        let result;
        switch (method) {
          case "SendMessage":
            result = await core.sendMessage(who, agentId, params);
            break;
          case "GetTask":
            result = core.getTask(who, agentId, params);
            break;
          case "ListTasks":
            result = core.listTasks(who, agentId, params);
            break;
          case "CancelTask":
            result = await core.cancelTask(who, agentId, params);
            break;
          case "CreateTaskPushNotificationConfig":
            result = core.createPushConfig(who, agentId, params);
            break;
          case "GetTaskPushNotificationConfig":
            result = core.getPushConfig(who, agentId, params);
            break;
          case "ListTaskPushNotificationConfigs":
            result = core.listPushConfigs(who, agentId, params);
            break;
          case "DeleteTaskPushNotificationConfig":
            result = core.deletePushConfig(who, agentId, params);
            break;
          case "GetExtendedAgentCard":
            result = core.getExtendedAgentCard(who, agentId, params);
            break;
          default:
            throw new RpcError(-32601, `method not found: ${method}`);
        }
        return sendJson(res, 200, { jsonrpc: "2.0", id, result });
      } catch (e) {
        const status = e.status ?? 200;
        return sendJson(res, status, { jsonrpc: "2.0", id, error: rpcErrorBody(id, e) });
      }
    }

    if (req.method === "POST" && path === "/mcp") {
      let who;
      try {
        who = await principal(req);
      } catch (e) {
        return sendJson(res, e.status ?? 401, { jsonrpc: "2.0", id: null, error: { code: -32009, message: e.message } });
      }
      const body = JSON.parse((await readBody(req)) || "{}");
      const out = await handleMcp(core, registry, who, body);
      if (out === null) {
        res.writeHead(202);
        return res.end();
      }
      if (req.headers["mcp-session-id"]) res.setHeader("mcp-session-id", req.headers["mcp-session-id"]);
      return sendJson(res, 200, out);
    }

    return sendJson(res, 404, { error: "not found", path });
  } catch (e) {
    return sendJson(res, e.status ?? 500, { error: String(e.message ?? e) });
  }
});

server.listen(config.port, config.host, () => {
  console.log(
    JSON.stringify({
      msg: "a2a-gateway listening",
      baseUrl: config.baseUrl,
      agents: registry.list().map((a) => a.agentId),
      devIdp: !!devIdp,
      stateDir: config.stateDir,
    }),
  );
});
