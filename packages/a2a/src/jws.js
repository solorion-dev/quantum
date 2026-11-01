// JWS (RFC 7515) RS256 helpers for Agent Card signatures.
// Cards carry signatures in the A2A form: card.signatures[] entries of
// { protected: base64url(header), signature: base64url(sig) } where the
// JWS signing input is ASCII(protected) + '.' + the RFC 8785 canonical
// form of the card WITHOUT its `signatures` member (per A2A spec §8).
import crypto from "node:crypto";
import { canonicalize } from "./jcs.js";

export function b64url(buf) {
  return Buffer.from(buf)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

export function b64urlDecode(str) {
  const pad = str.length % 4 === 0 ? "" : "=".repeat(4 - (str.length % 4));
  return Buffer.from(str.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64");
}

export function importPrivateKey(pem) {
  return crypto.createPrivateKey(pem);
}

export function importPublicJwk(jwk) {
  return crypto.createPublicKey({ key: jwk, format: "jwk" });
}

export function publicJwkFromPrivate(pem, kid) {
  const key = crypto.createPrivateKey(pem);
  const jwk = crypto.createPublicKey(key).export({ format: "jwk" });
  return { ...jwk, kid, alg: "RS256", use: "sig" };
}

/** Sign a card object; returns a new signatures[] entry. */
export function signCard(cardWithoutSignatures, privateKeyPem, kid) {
  const header = { alg: "RS256", kid, typ: "JOSE" };
  const protectedB64 = b64url(Buffer.from(JSON.stringify(header), "utf8"));
  const payload = canonicalize(cardWithoutSignatures);
  const signingInput = Buffer.from(`${protectedB64}.${payload}`, "utf8");
  const sig = crypto.sign("sha256", signingInput, {
    key: privateKeyPem,
    padding: crypto.constants.RSA_PKCS1_V1_5_PADDING,
  });
  return { protected: protectedB64, signature: b64url(sig) };
}

/**
 * Verify one signature entry against a card and a resolver
 * (kid) -> JWK | undefined. Returns true/false; never throws on bad input.
 */
export function verifyCardSignature(card, signatureEntry, resolveJwk) {
  try {
    const header = JSON.parse(b64urlDecode(signatureEntry.protected).toString("utf8"));
    if (header.alg !== "RS256" || !header.kid) return false;
    const jwk = resolveJwk(header.kid);
    if (!jwk) return false;
    const { signatures, ...rest } = card;
    const payload = canonicalize(rest);
    const signingInput = Buffer.from(`${signatureEntry.protected}.${payload}`, "utf8");
    return crypto.verify(
      "sha256",
      signingInput,
      { key: importPublicJwk(jwk), padding: crypto.constants.RSA_PKCS1_V1_5_PADDING },
      b64urlDecode(signatureEntry.signature),
    );
  } catch {
    return false;
  }
}

/** Verify a compact JWS (header.payload.signature) — used for OIDC JWTs. */
export function verifyCompactJws(token, resolveJwk) {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("not a compact JWS");
  const header = JSON.parse(b64urlDecode(parts[0]).toString("utf8"));
  if (header.alg !== "RS256") throw new Error(`unsupported alg ${header.alg}`);
  const jwk = resolveJwk(header.kid);
  if (!jwk) throw new Error(`unknown kid ${header.kid}`);
  const ok = crypto.verify(
    "sha256",
    Buffer.from(`${parts[0]}.${parts[1]}`, "utf8"),
    { key: importPublicJwk(jwk), padding: crypto.constants.RSA_PKCS1_V1_5_PADDING },
    b64urlDecode(parts[2]),
  );
  if (!ok) throw new Error("signature verification failed");
  return { header, payload: JSON.parse(b64urlDecode(parts[1]).toString("utf8")) };
}

/** Sign a compact JWS — used by the dev IdP and card-adjacent test flows. */
export function signCompactJws(payload, privateKeyPem, kid) {
  const header = { alg: "RS256", kid, typ: "JWT" };
  const h = b64url(Buffer.from(JSON.stringify(header), "utf8"));
  const p = b64url(Buffer.from(JSON.stringify(payload), "utf8"));
  const sig = crypto.sign("sha256", Buffer.from(`${h}.${p}`, "utf8"), {
    key: privateKeyPem,
    padding: crypto.constants.RSA_PKCS1_V1_5_PADDING,
  });
  return `${h}.${p}.${b64url(sig)}`;
}

export function generateRsaKeyPairPem() {
  const { privateKey, publicKey } = crypto.generateKeyPairSync("rsa", {
    modulusLength: 2048,
  });
  return {
    privatePem: privateKey.export({ type: "pkcs8", format: "pem" }),
    publicPem: publicKey.export({ type: "spki", format: "pem" }),
  };
}
