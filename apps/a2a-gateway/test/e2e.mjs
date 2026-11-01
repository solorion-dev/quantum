// End-to-end verification for the a2a-gateway dev instance.
// Runs against a LIVE gateway (A2A_BASE_URL) and the dev-IdP test
// identities. Exercises: discovery + card signature verification, T0/T1/T2
// policy denials, a real task lifecycle, SSE streaming, the auth-required
// approval chain (unauthorized attempt, delegated approval, denial),
// cancel, push notification configs + a real webhook delivery, the MCP
// facade (discover/send/status/inbox/respond), and ledger mirroring.
//
// Env: A2A_BASE_URL (default http://100.66.182.7:8340),
//      A2A_STATE_DIR (default ~/.local/share/a2a-gateway),
//      A2A_E2E_STRICT=1 — assert Tracker TRK ids + dsect issuer probe
//      (Tritium evidence runs; local mock runs leave it off).
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import http from "node:http";
import { A2AClient, textMessage, taskArtifactsText } from "../../../packages/a2a/src/client.js";

const BASE = (process.env.A2A_BASE_URL ?? "http://100.66.182.7:8340").replace(/\/+$/, "");
const STATE_DIR = process.env.A2A_STATE_DIR ?? path.join(os.homedir(), ".local", "share", "a2a-gateway");
const STRICT = process.env.A2A_E2E_STRICT === "1";
const POLL_MS = 3000;
const TASK_TIMEOUT_MS = Number(process.env.A2A_E2E_TASK_TIMEOUT_MS ?? 20 * 60 * 1000);

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`[${ok ? "PASS" : "FAIL"}] ${name}${detail ? ` — ${detail}` : ""}`);
}
function note(name, detail) {
  results.push({ name, ok: true, reportOnly: true, detail });
  console.log(`[INFO] ${name} — ${detail}`);
}

async function mint(identity) {
  const secret = fs.readFileSync(path.join(STATE_DIR, "dev-idp-secret.txt"), "utf8").trim();
  const res = await fetch(`${BASE}/dev-idp/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ identity, secret }),
  });
  if (!res.ok) throw new Error(`mint ${identity}: HTTP ${res.status}`);
  return (await res.json()).access_token;
}

function client(agentId, token) {
  return new A2AClient({ baseUrl: `${BASE}/agents/${agentId}`, token, jwksUrl: `${BASE}/.well-known/jwks.json` });
}

async function waitState(c, taskId, states, timeoutMs = TASK_TIMEOUT_MS) {
  const deadline = Date.now() + timeoutMs;
  let task;
  while (Date.now() < deadline) {
    task = await c.getTask(taskId);
    if (states.includes(task.status.state)) return task;
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
  throw new Error(`task ${taskId} did not reach ${states.join("|")} (last: ${task?.status?.state})`);
}

async function expectError(promise) {
  try {
    await promise;
    return null;
  } catch (e) {
    return e;
  }
}

async function mcpCall(token, name, args) {
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

async function main() {
  console.log(`E2E against ${BASE} (strict=${STRICT})`);
  const health = await (await fetch(`${BASE}/health`)).json();
  check("health", health.ok === true && health.agents.includes("qubit"), `agents=${health.agents}`);

  // --- tokens ---
  const [cooperTok, qubitTok, guestTok, partnerTok] = await Promise.all([
    mint("cooper"),
    mint("qubit"),
    mint("guest-demo"),
    mint("partner-demo"),
  ]);
  const cooperQubit = client("qubit", cooperTok);
  const guestQubit = client("qubit", guestTok);
  const partnerQubit = client("qubit", partnerTok);

  // --- discovery + signatures ---
  const anon = new A2AClient({ baseUrl: `${BASE}/agents/qubit`, jwksUrl: `${BASE}/.well-known/jwks.json` });
  const card = await anon.fetchCard(`${BASE}/agents/qubit`);
  check("card-fetch-t0", card.name === "Qubit" && card.skills.length === 3, `skills=${card.skills.map((s) => s.id)}`);
  check("card-signature-valid", (await anon.verifyCard(card)) === true);
  const tampered = { ...card, name: "NotQubit" };
  check("card-signature-tamper-detected", (await anon.verifyCard(tampered)) === false);

  // --- T0 cannot send ---
  const t0Err = await expectError(
    anon.sendMessage(textMessage({ text: "hello", metadata: { "dev.dsect.skill": "public-status" } })),
  );
  check("t0-send-rejected", !!t0Err, t0Err ? `code=${t0Err.code}` : "no error!");

  // --- T1 guest: open skill works ---
  const guestTask = await guestQubit.sendMessage(
    textMessage({ text: "status please", metadata: { "dev.dsect.skill": "public-status" } }),
  );
  const guestDone = await waitState(guestQubit, guestTask.id, ["TASK_STATE_COMPLETED", "TASK_STATE_FAILED"]);
  check(
    "t1-public-status-completes",
    guestDone.status.state === "TASK_STATE_COMPLETED" && taskArtifactsText(guestDone).includes("containers running"),
    `state=${guestDone.status.state}`,
  );

  // --- T1 guest: fleet skill denied ---
  const guestDeny = await expectError(
    guestQubit.sendMessage(textMessage({ text: "brief", metadata: { "dev.dsect.skill": "fleet-brief" } })),
  );
  check("t1-fleet-brief-denied", !!guestDeny, guestDeny ? guestDeny.message.slice(0, 80) : "no error!");

  // --- T2 partner: allowlist enforced by scope ---
  const partnerDeny = await expectError(
    partnerQubit.sendMessage(textMessage({ text: "brief", metadata: { "dev.dsect.skill": "fleet-brief" } })),
  );
  check("t2-fleet-brief-denied", !!partnerDeny, partnerDeny ? partnerDeny.message.slice(0, 80) : "no error!");
  const partnerTask = await partnerQubit.sendMessage(
    textMessage({ text: "status", metadata: { "dev.dsect.skill": "public-status" } }),
  );
  const partnerDone = await waitState(partnerQubit, partnerTask.id, ["TASK_STATE_COMPLETED", "TASK_STATE_FAILED"]);
  check("t2-public-status-completes", partnerDone.status.state === "TASK_STATE_COMPLETED", `state=${partnerDone.status.state}`);

  // --- T3 fleet: the real brief (live agent work + artifact file) ---
  const briefTask = await cooperQubit.sendMessage(
    textMessage({ text: "Produce the fleet status brief.", metadata: { "dev.dsect.skill": "fleet-brief" } }),
  );
  const briefDone = await waitState(cooperQubit, briefTask.id, ["TASK_STATE_COMPLETED", "TASK_STATE_FAILED"]);
  const filePart = briefDone.artifacts?.[0]?.parts?.find((p) => p.file);
  check(
    "t3-fleet-brief-completes-with-artifact-file",
    briefDone.status.state === "TASK_STATE_COMPLETED" && !!filePart,
    `state=${briefDone.status.state} uri=${filePart?.file?.fileWithUri ?? "none"}`,
  );

  // --- streaming (SSE) ---
  const events = [];
  for await (const ev of guestQubit.sendStreaming(
    textMessage({ text: "status, streamed", metadata: { "dev.dsect.skill": "public-status" } }),
  )) {
    events.push(ev);
  }
  const finals = events.filter((e) => e.statusUpdate?.final);
  check(
    "sse-streaming-lifecycle",
    events.some((e) => e.task) && finals.length >= 1,
    `events=${events.length} finals=${finals.length}`,
  );

  // --- auth-required chain ---
  const gated = await cooperQubit.sendMessage({
    ...textMessage({
      text: "Please summarize AGENT_STANDARD.md from your home directory.",
      metadata: { "dev.dsect.skill": "gated-file-read" },
    }),
    parts: [{ text: "Please summarize AGENT_STANDARD.md from your home directory." }, { data: { path: "AGENT_STANDARD.md" } }],
  });
  const paused = await waitState(cooperQubit, gated.id, ["TASK_STATE_AUTH_REQUIRED", "TASK_STATE_FAILED", "TASK_STATE_COMPLETED"]);
  check("gated-task-pauses-auth-required", paused.status.state === "TASK_STATE_AUTH_REQUIRED", `state=${paused.status.state}`);
  // unauthorized approval attempt (guest is not even a participant -> error; state must not move)
  await expectError(
    guestQubit.sendMessage({
      ...textMessage({ text: "approved by guest", taskId: gated.id, contextId: gated.contextId }),
      metadata: { "dev.dsect.approval": { decision: "approved", by: "guest-demo" } },
    }),
  );
  const stillPaused = await cooperQubit.getTask(gated.id);
  check("unauthorized-approval-does-not-resume", stillPaused.status.state === "TASK_STATE_AUTH_REQUIRED", `state=${stillPaused.status.state}`);
  // delegated approver (Cooper, delegation claim) approves
  await cooperQubit.sendMessage({
    ...textMessage({ text: "Approved under Scotty's standing delegation.", taskId: gated.id, contextId: gated.contextId }),
    metadata: { "dev.dsect.approval": { decision: "approved", by: "cooper" } },
  });
  const gatedDone = await waitState(cooperQubit, gated.id, ["TASK_STATE_COMPLETED", "TASK_STATE_FAILED"]);
  check(
    "delegated-approval-resumes-to-completion",
    gatedDone.status.state === "TASK_STATE_COMPLETED" && taskArtifactsText(gatedDone).length > 20,
    `state=${gatedDone.status.state} artifactChars=${taskArtifactsText(gatedDone).length}`,
  );

  // --- denial path ---
  const gated2 = await cooperQubit.sendMessage(
    textMessage({ text: "Summarize SOUL.md", metadata: { "dev.dsect.skill": "gated-file-read" } }),
  );
  await waitState(cooperQubit, gated2.id, ["TASK_STATE_AUTH_REQUIRED"]);
  await cooperQubit.sendMessage({
    ...textMessage({ text: "Denied.", taskId: gated2.id, contextId: gated2.contextId }),
    metadata: { "dev.dsect.approval": { decision: "denied", by: "cooper" } },
  });
  const denied = await waitState(cooperQubit, gated2.id, ["TASK_STATE_REJECTED"]);
  check("approval-denial-rejects", denied.status.state === "TASK_STATE_REJECTED");

  // --- cancel path ---
  const gated3 = await cooperQubit.sendMessage(
    textMessage({ text: "Summarize AGENT_STANDARD.md", metadata: { "dev.dsect.skill": "gated-file-read" } }),
  );
  await waitState(cooperQubit, gated3.id, ["TASK_STATE_AUTH_REQUIRED"]);
  const canceled = await cooperQubit.cancelTask(gated3.id);
  check("cancel-paused-task", canceled.status.state === "TASK_STATE_CANCELED", `state=${canceled.status.state}`);

  // --- push notification configs + real webhook delivery ---
  const hookHits = [];
  const hook = http.createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      hookHits.push({ auth: req.headers.authorization ?? null, body: raw });
      res.writeHead(200);
      res.end();
    });
  });
  await new Promise((r) => hook.listen(0, "127.0.0.1", r));
  const hookPort = hook.address().port;
  // Use an approval-gated task so the task is guaranteed in-flight when the
  // config is registered; approving it then produces push-delivered events.
  const pushTask = await cooperQubit.sendMessage(
    textMessage({ text: "Summarize AGENT_STANDARD.md (push test)", metadata: { "dev.dsect.skill": "gated-file-read" } }),
  );
  await waitState(cooperQubit, pushTask.id, ["TASK_STATE_AUTH_REQUIRED"]);
  const cfg = await cooperQubit.createPushConfig({
    taskId: pushTask.id,
    url: `http://127.0.0.1:${hookPort}/hook`,
    authentication: { schemes: ["Bearer"], credentials: "e2e-webhook-secret" },
  });
  check("push-config-create", !!cfg.id, `id=${cfg.id}`);
  await cooperQubit.sendMessage({
    ...textMessage({ text: "Approved (push test).", taskId: pushTask.id, contextId: pushTask.contextId }),
    metadata: { "dev.dsect.approval": { decision: "approved", by: "cooper" } },
  });
  await waitState(cooperQubit, pushTask.id, ["TASK_STATE_COMPLETED", "TASK_STATE_FAILED"]);
  await new Promise((r) => setTimeout(r, 1500));
  check(
    "push-webhook-delivered-with-credentials",
    hookHits.some((h) => h.body.includes(pushTask.id) && h.auth === "Bearer e2e-webhook-secret"),
    `hits=${hookHits.length}`,
  );
  const listed = await cooperQubit.listPushConfigs(pushTask.id);
  check("push-config-list", listed.length === 1, `count=${listed.length}`);
  await cooperQubit.deletePushConfig(pushTask.id, cfg.id);
  const afterDelete = await cooperQubit.listPushConfigs(pushTask.id);
  check("push-config-delete", afterDelete.length === 0, `count=${afterDelete.length}`);
  hook.close();

  // --- MCP facade ---
  const initRes = await fetch(`${BASE}/mcp`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${cooperTok}`, accept: "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-03-26" } }),
  }).then((r) => r.json());
  check("mcp-initialize", initRes.result?.serverInfo?.name === "a2a-gateway", JSON.stringify(initRes.result?.serverInfo ?? {}));
  const toolsRes = await fetch(`${BASE}/mcp`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${cooperTok}`, accept: "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }),
  }).then((r) => r.json());
  const toolNames = (toolsRes.result?.tools ?? []).map((t) => t.name);
  check(
    "mcp-tools-list",
    ["a2a_discover", "a2a_send_task", "a2a_task_status", "a2a_inbox", "a2a_respond", "a2a_approve"].every((t) => toolNames.includes(t)),
    toolNames.join(","),
  );
  const discovered = await mcpCall(cooperTok, "a2a_discover", { skill: "fleet-brief" });
  check(
    "mcp-discover-finds-qubit",
    discovered.some((d) => d.agentId === "qubit" && d.policy?.minTier === 3),
    JSON.stringify(discovered.map((d) => d.agentId)),
  );
  const mcpTask = await mcpCall(guestTok, "a2a_send_task", { agent: "qubit", skill: "public-status", text: "status via MCP", blocking: true });
  check("mcp-send-task-completes", mcpTask.status?.state === "TASK_STATE_COMPLETED", `state=${mcpTask.status?.state}`);

  // inbox round trip: Qubit leaves Cooper a coordination note; Cooper drains + responds.
  const inboxTask = await mcpCall(qubitTok, "a2a_send_task", {
    agent: "cooper",
    skill: "coordination-notes",
    text: "Note from Qubit via A2A: inbox round-trip verification.",
  });
  check("inbox-task-queued-working", inboxTask.status?.state === "TASK_STATE_WORKING", `state=${inboxTask.status?.state}`);
  const inbox = await mcpCall(cooperTok, "a2a_inbox", {});
  check("mcp-inbox-lists-task", inbox.some((t) => t.id === inboxTask.id), `inbox=${inbox.length}`);
  const responded = await mcpCall(cooperTok, "a2a_respond", { taskId: inboxTask.id, text: "Acknowledged by Cooper (via MCP facade inbox)." });
  check("mcp-respond-completes-task", responded.status?.state === "TASK_STATE_COMPLETED", `state=${responded.status?.state}`);
  const inboxAfter = await mcpCall(cooperTok, "a2a_inbox", {});
  check("mcp-inbox-drained", !inboxAfter.some((t) => t.id === inboxTask.id), `inbox=${inboxAfter.length}`);

  // --- ledger mirroring ---
  const ledgerMap = JSON.parse(fs.readFileSync(path.join(STATE_DIR, "ledger-map.json"), "utf8"));
  const briefRef = ledgerMap[briefTask.id] ?? {};
  const gatedRef = ledgerMap[gated.id] ?? {};
  if (STRICT) {
    check("ledger-tracker-mirrored", /^TRK-\d+$/.test(briefRef.trkId ?? "") && /^TRK-\d+$/.test(gatedRef.trkId ?? ""), `brief=${briefRef.trkId} gated=${gatedRef.trkId}`);
  } else {
    note("ledger-tracker-mirrored", `brief=${briefRef.trkId ?? "(local: tracker unavailable, see ledger-errors.jsonl)"} gated=${gatedRef.trkId ?? "?"}`);
  }
  note("ledger-hive", `brief hive=${briefRef.hiveId ?? "(see hive-outbox.jsonl)"} gated hive=${gatedRef.hiveId ?? "(see hive-outbox.jsonl)"}`);

  // --- production issuer probe (JWKS fetch + parse of the real dsect-auth) ---
  const probe = health.issuers?.["https://mcp.dsect.net"];
  if (STRICT) check("dsect-issuer-jwks-probe", probe?.ok === true, JSON.stringify(probe));
  else note("dsect-issuer-jwks-probe", JSON.stringify(probe));

  const failed = results.filter((r) => !r.ok);
  console.log(`\n==== E2E SUMMARY: ${results.filter((r) => r.ok).length}/${results.length} checks passed, ${failed.length} failed ====`);
  console.log(JSON.stringify({ base: BASE, strict: STRICT, results }, null, 2));
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => {
  console.error(`E2E crashed: ${e.stack ?? e}`);
  process.exit(2);
});
