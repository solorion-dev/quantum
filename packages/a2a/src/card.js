// Agent Card construction + validation for our A2A profile (A2A 1.0).
// The profile's card requirements: JSON-RPC interface only, OIDC security
// scheme, JWS-signed, honest capability flags. See docs/PROFILE.md.

export const PROFILE_VERSION = "0.1";
export const A2A_VERSION = "1.0";

/**
 * Build an unsigned Agent Card.
 * spec: {
 *   name, description, version, providerOrg, providerUrl, documentationUrl,
 *   baseUrl (agent endpoint root; JSON-RPC POST target is baseUrl itself),
 *   oidcDiscoveryUrl, streaming, pushNotifications,
 *   skills: [{ id, name, description, tags, examples, inputModes, outputModes,
 *              minTier, requiresApproval? }]
 * }
 * Profile extensions (minTier / requiresApproval) are NOT put on the wire
 * card skill objects (the spec's skill schema is fixed); they ride in the
 * card-level `metadata` of the registry record instead. The wire card stays
 * vanilla so any conforming client can parse it.
 */
export function buildCard(spec) {
  const card = {
    protocolVersions: [A2A_VERSION],
    name: spec.name,
    description: spec.description,
    version: spec.version ?? "1.0.0",
    provider: { organization: spec.providerOrg, url: spec.providerUrl },
    documentationUrl: spec.documentationUrl,
    supportedInterfaces: [
      { url: spec.baseUrl, protocolBinding: "JSONRPC", protocolVersion: A2A_VERSION },
    ],
    capabilities: {
      streaming: !!spec.streaming,
      pushNotifications: !!spec.pushNotifications,
      extendedAgentCard: false,
    },
    securitySchemes: {
      dsectOidc: {
        openIdConnectSecurityScheme: {
          description:
            "OIDC bearer token. Fleet/partner tokens are issued by dsect-auth; the tailnet dev instance also trusts its local dev issuer (see PROFILE.md).",
          discoveryUrl: spec.oidcDiscoveryUrl,
        },
      },
    },
    securityRequirements: [{ schemes: { dsectOidc: {} } }],
    defaultInputModes: ["text/plain", "application/json"],
    defaultOutputModes: ["text/plain", "application/json", "text/markdown"],
    skills: (spec.skills ?? []).map((s) => ({
      id: s.id,
      name: s.name,
      description: s.description,
      tags: s.tags ?? [],
      examples: s.examples ?? [],
      inputModes: s.inputModes ?? ["text/plain", "application/json"],
      outputModes: s.outputModes ?? ["text/markdown", "text/plain"],
    })),
  };
  return card;
}

/** Minimal structural validation — enough to catch authoring mistakes. */
export function validateCard(card) {
  const problems = [];
  if (!card || typeof card !== "object") return ["card is not an object"];
  if (!Array.isArray(card.protocolVersions) || !card.protocolVersions.includes(A2A_VERSION))
    problems.push("protocolVersions must include 1.0");
  if (!card.name) problems.push("name missing");
  if (!Array.isArray(card.supportedInterfaces) || card.supportedInterfaces.length === 0)
    problems.push("supportedInterfaces missing");
  for (const iface of card.supportedInterfaces ?? []) {
    if (iface.protocolBinding !== "JSONRPC")
      problems.push(`profile allows JSONRPC only, saw ${iface.protocolBinding}`);
  }
  if (!Array.isArray(card.skills)) problems.push("skills missing");
  const ids = new Set();
  for (const s of card.skills ?? []) {
    if (!s.id || ids.has(s.id)) problems.push(`skill id missing/duplicate: ${s.id}`);
    ids.add(s.id);
  }
  return problems;
}
