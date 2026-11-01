// DEV ISSUER — a local OIDC stand-in for the tailnet dev instance ONLY.
//
// Why this exists: the production issuer (dsect-auth via hub-api) supports
// only authorization_code + refresh_token grants — there is no
// client_credentials / token-exchange grant, so non-interactive agents
// cannot mint the profile's per-agent claim tokens (tier + per-skill
// scopes) against it headlessly. This module mints such tokens for a
// fixed set of TEST identities so the gateway's real JWKS validation path
// (identical code to production) can be exercised end to end.
//
// It is disabled unless A2A_DEV_IDP=1, its signing key lives in the state
// dir (0600, never in the repo), and minting requires a bootstrap secret
// from the state dir. Production migration path: register per-agent
// clients / add a machine grant to dsect-auth, then drop this issuer from
// the gateway's trust list (config only). See docs/PROFILE.md.
import crypto from "node:crypto";
import {
  generateRsaKeyPairPem,
  publicJwkFromPrivate,
  signCompactJws,
  b64url,
} from "../../../packages/a2a/src/jws.js";

// Test identities for the dev instance. Tiers/scopes mirror docs/TRUST.md.
export const DEV_IDENTITIES = {
  cooper: {
    tier: 3,
    scope: "a2a:* a2a:approve",
    delegation: "scotty-standing",
    note: "Cooper — fleet client + delegated approver (standing fences apply)",
  },
  qubit: {
    tier: 3,
    scope: "a2a:*",
    note: "Qubit — fleet agent (Hermes) behind the qubit adapter",
  },
  bookkeeper: {
    tier: 3,
    scope: "a2a:invoke:fleet-brief a2a:invoke:public-status",
    note: "Codex Bookkeeper — enrolled test identity (inbox adapter)",
  },
  "partner-demo": {
    tier: 2,
    scope: "a2a:invoke:public-status",
    note: "Partner-network demo — skill allowlist enforced by scopes",
  },
  "guest-demo": {
    tier: 1,
    scope: "a2a:invoke:public-status",
    note: "Registered-guest demo — open skills only, hard rate limits",
  },
};

export class DevIdp {
  constructor(store, issuerBaseUrl) {
    this.store = store;
    this.issuer = issuerBaseUrl; // e.g. http://100.66.182.7:8340/dev-idp
    if (!store.exists("dev-idp-key.pem")) {
      const { privatePem } = generateRsaKeyPairPem();
      store.writeText("dev-idp-key.pem", privatePem, 0o600);
    }
    this.privatePem = store.readText("dev-idp-key.pem");
    this.kid = "dev-idp-1";
    this.jwk = publicJwkFromPrivate(this.privatePem, this.kid);
    if (!store.exists("dev-idp-secret.txt")) {
      store.writeText("dev-idp-secret.txt", b64url(crypto.randomBytes(24)) + "\n", 0o600);
    }
    this.secret = store.readText("dev-idp-secret.txt").trim();
  }

  jwks() {
    return { keys: [this.jwk] };
  }

  discovery() {
    return {
      issuer: this.issuer,
      jwks_uri: `${this.issuer}/jwks.json`,
      token_endpoint: `${this.issuer}/token`,
      grant_types_supported: ["urn:dsect:dev-bootstrap"],
      note: "DEV ONLY stand-in issuer for the tailnet dev instance. Not dsect-auth.",
    };
  }

  /** Mint a token for a test identity. Throws on bad secret/identity. */
  mint(identity, bootstrapSecret) {
    if (bootstrapSecret !== this.secret) throw new Error("bad bootstrap secret");
    const spec = DEV_IDENTITIES[identity];
    if (!spec) throw new Error(`unknown dev identity ${identity}`);
    const now = Math.floor(Date.now() / 1000);
    const payload = {
      iss: this.issuer,
      sub: identity,
      aud: "a2a-gateway",
      iat: now,
      exp: now + 3600,
      tier: spec.tier,
      scope: spec.scope,
      ...(spec.delegation ? { delegation: spec.delegation } : {}),
    };
    return signCompactJws(payload, this.privatePem, this.kid);
  }
}
