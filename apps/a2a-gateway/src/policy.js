// Tier policy enforcement (gateway side). The receiving adapter re-checks
// the same rules before executing (defense in depth — see adapters/).
// Rules per docs/TRUST.md:
//   T0 stranger      — public card reads only; cannot send tasks at all.
//   T1 guest         — open skills (minTier<=1) + token scope, hard limits.
//   T2 partner       — skill allowlist carried as token scopes.
//   T3 fleet         — full published surface minus destructive classes.
//   T4 operator-del. — T3 breadth + may approve auth-required in-task.
import { hasInvokeScope } from "./oidc.js";

export class RateLimiter {
  constructor(perMinuteByTier) {
    this.perMinute = perMinuteByTier;
    this.buckets = new Map(); // agentId -> [timestamps]
  }

  check(principal) {
    const limit = this.perMinute[principal.tier] ?? 5;
    const now = Date.now();
    const arr = (this.buckets.get(principal.agentId) ?? []).filter((t) => now - t < 60000);
    if (arr.length >= limit) {
      const e = new Error(`rate limit exceeded for ${principal.agentId} (tier ${principal.tier})`);
      e.status = 429;
      throw e;
    }
    arr.push(now);
    this.buckets.set(principal.agentId, arr);
  }
}

export function checkInvoke(principal, agentRecord, skillId, config) {
  const meta = agentRecord.skillMeta[skillId];
  if (!meta) {
    const e = new Error(`agent ${agentRecord.agentId} has no skill ${skillId}`);
    e.status = 404;
    e.rpcCode = -32602;
    throw e;
  }
  if (principal.tier < meta.minTier) {
    const e = new Error(
      `tier ${principal.tier} may not invoke ${skillId} (requires T${meta.minTier})`,
    );
    e.status = 403;
    e.rpcCode = -32009;
    throw e;
  }
  if (!hasInvokeScope(principal, skillId)) {
    const e = new Error(`token lacks scope a2a:invoke:${skillId}`);
    e.status = 403;
    e.rpcCode = -32009;
    throw e;
  }
  return meta;
}

export function checkMessageSize(principal, bytes, config) {
  const max = config.limits.maxMessageBytes[principal.tier] ?? 8192;
  if (bytes > max) {
    const e = new Error(`message too large for tier ${principal.tier} (${bytes} > ${max} bytes)`);
    e.status = 413;
    e.rpcCode = -32602;
    throw e;
  }
}

/**
 * The auth-required approval rule (survey §7, Scotty's fences):
 * an approval is honored ONLY from a principal holding the a2a:approve
 * scope — which issuers grant to Scotty or to an agent carrying his
 * recorded delegation (claims.delegation). Never "whichever agent is
 * downstream": the task's creator and the executing agent cannot approve.
 */
export function checkApproval(principal, task) {
  if (!principal.approver) return false;
  // The A2A auth-required chain is fulfilled from the CLIENT side, so the
  // task's creator may approve — but only when they hold the approve scope
  // via Scotty's delegation (checked above). The executing agent can never
  // approve its own task, and no uninvolved downstream agent can either:
  // they would lack the scope in the first place.
  if (principal.agentId === task.agentId) return false;
  return true;
}
