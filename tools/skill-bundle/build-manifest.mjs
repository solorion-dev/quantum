#!/usr/bin/env node
// Build skills/manifest.json from the canonical skills/ tree (TRK-0674).
// Usage: node tools/skill-bundle/build-manifest.mjs [skillsDir]
// bundle_commit: env BUNDLE_COMMIT, else `git rev-parse HEAD` at the repo root,
// else "unknown". bundle_version: env BUNDLE_VERSION, else v2026.11.0.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { readSkill, walkFiles } from "./frontmatter.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const skillsDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(repoRoot, "skills");

let bundleCommit = process.env.BUNDLE_COMMIT || "";
if (!bundleCommit) {
  try { bundleCommit = execSync("git rev-parse HEAD", { cwd: repoRoot, encoding: "utf8" }).trim(); }
  catch { bundleCommit = "unknown"; }
}
const bundleVersion = process.env.BUNDLE_VERSION || "v2026.11.0";

const dirs = fs.readdirSync(skillsDir, { withFileTypes: true })
  .filter((d) => d.isDirectory()).map((d) => d.name).sort();

const skills = [];
for (const name of dirs) {
  const dir = path.join(skillsDir, name);
  if (!fs.existsSync(path.join(dir, "SKILL.md"))) continue;
  const { meta } = readSkill(dir);
  const files = [];
  let total = 0;
  for (const rel of walkFiles(dir)) {
    const buf = fs.readFileSync(path.join(dir, rel));
    const sha256 = crypto.createHash("sha256").update(buf).digest("hex");
    files.push({ path: rel, sha256, bytes: buf.length });
    total += buf.length;
  }
  const deps = (meta.dependencies && typeof meta.dependencies === "object" && !Array.isArray(meta.dependencies))
    ? { tools: meta.dependencies.tools || [], repos: meta.dependencies.repos || [], urls: meta.dependencies.urls || [] }
    : { tools: [], repos: [], urls: [] };
  skills.push({
    name,
    version: meta.version || "1.0.0",
    description: String(meta.description || ""),
    tags: Array.isArray(meta.tags) ? meta.tags : [],
    status: meta.status || "active",
    provenance: meta.provenance || "quantum",
    aliases: Array.isArray(meta.aliases) ? meta.aliases : [],
    dependencies: deps,
    files,
    total_bytes: total,
  });
}

const manifest = {
  schema: 1,
  generated_at: new Date().toISOString(),
  bundle_commit: bundleCommit,
  bundle_version: bundleVersion,
  bundle_tag: bundleVersion,
  skills,
};
const out = path.join(skillsDir, "manifest.json");
fs.writeFileSync(out, JSON.stringify(manifest, null, 2) + "\n");
const q = skills.filter((s) => s.provenance === "quantum").length;
console.log(`Wrote ${out}: ${skills.length} skills (quantum=${q}, imported=${skills.length - q}), bundle ${bundleVersion} @ ${bundleCommit}`);
