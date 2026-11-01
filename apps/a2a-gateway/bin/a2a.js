#!/usr/bin/env node
// a2a CLI — the operator/client tool for the gateway dev instance.
// Runs on Tritium (it reads the dev-IdP bootstrap secret from the state
// dir to mint test-identity tokens). Identity via A2A_IDENTITY
// (default: cooper). Gateway via A2A_BASE_URL (default: tailnet dev URL).
//
//   a2a token <identity>                 print a dev token
//   a2a discover [--skill <id>]          search the registry (via MCP facade)
//   a2a send <agent> <skill> <text...>   send a task (non-blocking)
//   a2a send ... --blocking              wait for terminal/paused state
//   a2a status <taskId>                  task status via MCP facade
//   a2a approve <taskId> approved|denied approve/deny an auth-required task
//   a2a inbox                            your queued inbox tasks
//   a2a respond <taskId> <text...>       complete an inbox task
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const BASE = process.env.A2A_BASE_URL ?? "http://100.66.182.7:8340";
const STATE_DIR = process.env.A2A_STATE_DIR ?? path.join(os.homedir(), ".local", "share", "a2a-gateway");
const IDENTITY = process.env.A2A_IDENTITY ?? "cooper";

async function mint(identity) {
  const secret = fs.readFileSync(path.join(STATE_DIR, "dev-idp-secret.txt"), "utf8").trim();
  const res = await fetch(`${BASE}/dev-idp/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ identity, secret }),
  });
  if (!res.ok) throw new Error(`mint failed: HTTP ${res.status} ${await res.text()}`);
  return (await res.json()).access_token;
}

async function mcp(token, name, args) {
  const res = await fetch(`${BASE}/mcp`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${token}`, accept: "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }),
  });
  const body = await res.json();
  if (body.error) throw new Error(body.error.message);
  const text = body.result?.content?.[0]?.text ?? "";
  if (body.result?.isError) throw new Error(text);
  return JSON.parse(text);
}

const [cmd, ...rest] = process.argv.slice(2);
const identity = rest.includes("--as")
  ? rest[rest.indexOf("--as") + 1]
  : IDENTITY;

try {
  if (cmd === "token") {
    console.log(await mint(rest[0] ?? identity));
  } else if (cmd === "discover") {
    const token = await mint(identity);
    const skill = rest.includes("--skill") ? rest[rest.indexOf("--skill") + 1] : undefined;
    console.log(JSON.stringify(await mcp(token, "a2a_discover", { ...(skill ? { skill } : {}) }), null, 2));
  } else if (cmd === "send") {
    const [agent, skill, ...textParts] = rest.filter((a) => a !== "--blocking");
    const token = await mint(identity);
    const out = await mcp(token, "a2a_send_task", {
      agent,
      skill,
      text: textParts.join(" "),
      blocking: rest.includes("--blocking"),
    });
    console.log(JSON.stringify(out, null, 2));
  } else if (cmd === "status") {
    const token = await mint(identity);
    console.log(JSON.stringify(await mcp(token, "a2a_task_status", { taskId: rest[0] }), null, 2));
  } else if (cmd === "approve") {
    const token = await mint(identity);
    console.log(JSON.stringify(await mcp(token, "a2a_approve", { taskId: rest[0], decision: rest[1] ?? "approved" }), null, 2));
  } else if (cmd === "inbox") {
    const token = await mint(identity);
    console.log(JSON.stringify(await mcp(token, "a2a_inbox", {}), null, 2));
  } else if (cmd === "respond") {
    const token = await mint(identity);
    console.log(JSON.stringify(await mcp(token, "a2a_respond", { taskId: rest[0], text: rest.slice(1).join(" ") }), null, 2));
  } else {
    console.error("usage: a2a token|discover|send|status|approve|inbox|respond ...");
    process.exit(2);
  }
} catch (e) {
  console.error(`error: ${e.message}`);
  process.exit(1);
}
