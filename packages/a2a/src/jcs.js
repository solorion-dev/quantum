// RFC 8785 (JSON Canonicalization Scheme) — minimal, correct implementation
// for the JSON subset used by Agent Cards (objects, arrays, strings, numbers,
// booleans, null). Numbers rely on ECMAScript Number::toString semantics,
// which is exactly what RFC 8785 mandates and what JSON.stringify produces
// for finite numbers in V8.

function serializeString(str) {
  // JSON string escaping per RFC 8785 §3.2.2: only the mandatory escapes,
  // plus \u00xx lowercase-hex for control characters below 0x20 that have
  // no short escape. JSON.stringify already implements the RFC 8785 rules
  // for string literals (it escapes ", \, and control chars the same way).
  return JSON.stringify(str);
}

function serializeNumber(num) {
  if (!Number.isFinite(num)) {
    throw new Error("JCS: non-finite numbers are not allowed");
  }
  if (num === 0) return "0"; // covers -0 per RFC 8785
  return JSON.stringify(num);
}

export function canonicalize(value) {
  if (value === null) return "null";
  const t = typeof value;
  if (t === "boolean") return value ? "true" : "false";
  if (t === "number") return serializeNumber(value);
  if (t === "string") return serializeString(value);
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalize).join(",") + "]";
  }
  if (t === "object") {
    // Sort keys by UTF-16 code unit sequence (RFC 8785 §3.2.3), which is
    // what the default string comparison in JS gives us.
    const keys = Object.keys(value).sort();
    const parts = [];
    for (const k of keys) {
      const v = value[k];
      if (v === undefined) continue; // undefined is not a JSON value
      parts.push(serializeString(k) + ":" + canonicalize(v));
    }
    return "{" + parts.join(",") + "}";
  }
  throw new Error(`JCS: unsupported type ${t}`);
}
