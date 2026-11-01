// TEST FIXTURE ONLY — a stand-in for the Hermes gateway API used to test
// the qubit adapter locally. It is never deployed and never presented as
// a real agent: the production adapter talks to the live Hermes gateway
// on Tritium (see src/adapters/hermes.js). Behaviors are keyed off the
// adapter's prompts: JSON for public-status, brief-file write for
// fleet-brief, summary for gated-file-read.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const PORT = Number(process.env.MOCK_HERMES_PORT ?? 18642);
const KEY = process.env.MOCK_HERMES_KEY ?? "mock-key";
const WORKSPACE = process.env.MOCK_WORKSPACE ?? "/tmp/mock-hermes-workspace";

const server = http.createServer(async (req, res) => {
  if (req.headers.authorization !== `Bearer ${KEY}`) {
    res.writeHead(401, { "content-type": "application/json" });
    return res.end(JSON.stringify({ error: { message: "Invalid gateway API key (API_SERVER_KEY)" } }));
  }
  if (req.method === "GET" && req.url === "/v1/models") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ data: [{ id: "qwen3.6-35b-a3b" }] }));
  }
  if (req.method === "POST" && req.url === "/v1/chat/completions") {
    let raw = "";
    for await (const c of req) raw += c;
    const body = JSON.parse(raw);
    const user = body.messages?.filter((m) => m.role === "user").pop()?.content ?? "";
    let reply;
    if (user.includes("ONLY a JSON object")) {
      reply = JSON.stringify({ total: 3, names: ["mock-alpha", "mock-beta", "mock-gamma"] });
    } else if (user.includes("fleet status brief")) {
      const m = user.match(/file (a2a\/[\w.-]+\.md) inside your workspace/);
      const brief = "# Fleet brief (mock fixture)\n\nUptime nominal. 3 containers running (mock).\n";
      if (m) {
        const p = path.join(WORKSPACE, m[1]);
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, brief);
      }
      reply = brief;
    } else if (user.includes("delegated approver")) {
      reply = 'Summary of the file: it sets the agent standard. One exact line: "Mock quote line for verification."\n';
    } else if (user.includes("WROTE")) {
      reply = "WROTE";
    } else {
      reply = "Mock reply.";
    }
    if (body.stream) {
      res.writeHead(200, { "content-type": "text/event-stream" });
      const pieces = reply.match(/.{1,24}/gs) ?? [reply];
      for (const piece of pieces) {
        res.write(`data: ${JSON.stringify({ choices: [{ delta: { content: piece } }] })}\n\n`);
      }
      res.write("data: [DONE]\n\n");
      return res.end();
    }
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ choices: [{ message: { content: reply } }] }));
  }
  res.writeHead(404);
  res.end();
});

server.listen(PORT, "127.0.0.1", () => console.log(`mock-hermes on ${PORT}`));
