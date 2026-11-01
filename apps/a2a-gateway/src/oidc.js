// OIDC bearer-token validation against any number of trusted issuers,
// each resolved through its JWKS. The verifier is issuer-agnostic: the
// production issuer (dsect-auth, iss https://mcp.dsect.net) and the dev
// issuer run through exactly the same code path.
//
// Profile claims (see docs/PROFILE.md):
//   sub        agent id (e.g. "cooper")
//   tier       trust tier 0..4 (number) — authorization input, set by issuer
//   scope      space-separated scopes, incl. per-skill "a2a:invoke:<skill>"
//              and "a2a:*"; approvers also carry scope "a2a:approve"
//   delegation optional string naming the authority behind an approver
//              (e.g. "scotty-standing") — approvals resolve to Scotty or to
//              an agent holding his recorded delegation, never further.
import { verifyCompactJws } from "../../../packages/a2a/src/jws.js";

export class OidcVerifier {
  constructor(issuers) {
    // issuers: [{ iss, jwksUrl, jwksFetcher? }] — jwksFetcher overrides the
    // fetch (used by the dev IdP to serve its own keys in-process).
    this.issuers = new Map(issuers.map((i) => [i.iss, { ...i, keys: null, fetchedAt: 0 }]));
  }

  addIssuer(iss, jwksUrl, jwksFetcher) {
    this.issuers.set(iss, { iss, jwksUrl, jwksFetcher, keys: null, fetchedAt: 0 });
  }

  async _keys(entry) {
    const now = Date.now();
    if (entry.keys && now - entry.fetchedAt < 5 * 60 * 1000) return entry.keys;
    let jwks;
    if (entry.jwksFetcher) {
      jwks = await entry.jwksFetcher();
    } else {
      const res = await fetch(entry.jwksUrl);
      if (!res.ok) throw new Error(`JWKS fetch failed for ${entry.iss}: HTTP ${res.status}`);
      jwks = await res.json();
    }
    entry.keys = new Map((jwks.keys ?? []).map((k) => [k.kid, k]));
    entry.fetchedAt = now;
    return entry.keys;
  }

  /** Health probe: can we fetch + parse this issuer's JWKS at all? */
  async probeIssuer(iss) {
    const entry = this.issuers.get(iss);
    if (!entry) return { iss, ok: false, error: "not trusted" };
    try {
      const keys = await this._keys(entry);
      return { iss, ok: true, keyCount: keys.size };
    } catch (e) {
      return { iss, ok: false, error: String(e.message ?? e) };
    }
  }

  /**
   * Validate a bearer token. Returns a principal:
   * { agentId, tier, scopes:Set<string>, approver, delegation, issuer }
   * Throws Error with .status = 401/403 on failure.
   */
  async validate(token) {
    if (!token) {
      const e = new Error("missing bearer token");
      e.status = 401;
      throw e;
    }
    let payload;
    try {
      // Decode iss unverified ONLY to route to the right JWKS; the
      // signature check below is what actually authenticates.
      const body = JSON.parse(
        Buffer.from(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8"),
      );
      const entry = this.issuers.get(body.iss);
      if (!entry) throw new Error(`untrusted issuer ${body.iss}`);
      const keys = await this._keys(entry);
      ({ payload } = verifyCompactJws(token, (kid) => keys.get(kid)));
    } catch (e) {
      e.status = 401;
      throw e;
    }
    const now = Math.floor(Date.now() / 1000);
    if (payload.exp && payload.exp < now) {
      const e = new Error("token expired");
      e.status = 401;
      throw e;
    }
    if (!payload.sub) {
      const e = new Error("token has no sub");
      e.status = 401;
      throw e;
    }
    const scopes = new Set(
      Array.isArray(payload.scope)
        ? payload.scope
        : String(payload.scope ?? "").split(/\s+/).filter(Boolean),
    );
    return {
      agentId: payload.sub,
      tier: typeof payload.tier === "number" ? payload.tier : 0,
      scopes,
      approver: scopes.has("a2a:approve"),
      delegation: payload.delegation ?? null,
      issuer: payload.iss,
      claims: payload,
    };
  }
}

/** Scope helper: does the principal hold invoke rights for a skill? */
export function hasInvokeScope(principal, skillId) {
  return (
    principal.scopes.has("a2a:*") ||
    principal.scopes.has(`a2a:invoke:${skillId}`) ||
    principal.scopes.has("a2a:invoke:*")
  );
}
