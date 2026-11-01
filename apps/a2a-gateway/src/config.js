// Gateway configuration — all from environment, with dev-instance defaults.
// The production shape (dsect-auth only, public door) is a config change,
// not a code change. See docs/PROFILE.md §operations.
import path from "node:path";
import os from "node:os";

export function loadConfig(env = process.env) {
  const stateDir =
    env.A2A_STATE_DIR ?? path.join(os.homedir(), ".local", "share", "a2a-gateway");
  const port = Number(env.A2A_PORT ?? 8340);
  const host = env.A2A_HOST ?? "100.66.182.7"; // tailnet-only by default
  const baseUrl = env.A2A_BASE_URL ?? `http://${host}:${port}`;
  return {
    port,
    host,
    baseUrl,
    stateDir,
    // Issuer that cards advertise in their OIDC scheme (the real dsect-auth).
    oidcDiscoveryUrl:
      env.A2A_OIDC_DISCOVERY_URL ?? "https://mcp.dsect.net/.well-known/openid-configuration",
    // Issuers whose JWTs the gateway verifies. Each: { iss, jwksUrl }.
    // The dsect-auth JWKS is fetched over loopback on Tritium (its public
    // issuer string stays https://mcp.dsect.net).
    trustedIssuers: [
      {
        iss: "https://mcp.dsect.net",
        jwksUrl: env.A2A_DSECT_JWKS_URL ?? "http://127.0.0.1:8091/.well-known/jwks.json",
      },
    ],
    devIdp: {
      enabled: env.A2A_DEV_IDP === "1",
      // path segment under the gateway origin: {baseUrl}/dev-idp
      issuerPath: "/dev-idp",
    },
    hermes: {
      // Port map (verified live 2026-10-25): the Hermes container serves
      // one API per profile — 8642 is the DEFAULT profile (which returns
      // empty completions), 8643 is the QUBIT profile (model id "qubit").
      apiBase: env.A2A_HERMES_API_BASE ?? "http://127.0.0.1:8643",
      // File containing ONLY the Hermes gateway API_SERVER_KEY (0600).
      // The key value is never logged, committed, or printed by this code.
      keyFile: env.A2A_HERMES_KEY_FILE ?? null,
      workspaceDir:
        env.A2A_HERMES_WORKSPACE ?? "/srv/ai/state/hermes/workspace",
      model: env.A2A_HERMES_MODEL ?? null, // null = gateway default profile model
      timeoutMs: Number(env.A2A_HERMES_TIMEOUT_MS ?? 900000),
    },
    tracker: {
      cli: env.A2A_TRACKER_CLI ?? "/mnt/fast/tracker/tracker.py",
      epicId: env.A2A_TRACKER_EPIC ?? "TRK-0424",
    },
    hive: {
      // The Quantum Memory MCP server (loopback on Tritium). It requires
      // a bearer token ($QUANTUM_MEMORY_MCP_TOKEN on that service); the
      // gateway reads its copy from a 0600 file, never from the repo.
      mcpUrl: env.A2A_HIVE_MCP_URL ?? "http://127.0.0.1:8083/mcp",
      tokenFile: env.A2A_HIVE_TOKEN_FILE ?? null,
      enabled: env.A2A_HIVE_ENABLED !== "0",
    },
    limits: {
      // per-identity requests/minute by tier (T0 handled separately: reads)
      perMinute: { 1: 5, 2: 30, 3: 120, 4: 120 },
      maxMessageBytes: { 1: 8192, 2: 65536, 3: 262144, 4: 262144 },
    },
  };
}
