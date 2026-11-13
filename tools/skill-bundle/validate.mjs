#!/usr/bin/env node
// Validate the canonical skills/ tree (TRK-0674).
// Checks: SKILL.md present, frontmatter schema, name == directory, semver,
// description present, status/provenance enums, dependencies shape,
// secret scan, no .git/__pycache__, no file > 1 MB without an allowlist entry.
// Usage: node tools/skill-bundle/validate.mjs [skillsDir]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readSkill, walkFiles } from "./frontmatter.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const skillsDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(repoRoot, "skills");
const allowlistPath = path.join(here, "allowlist.json");
const allowlist = fs.existsSync(allowlistPath) ? JSON.parse(fs.readFileSync(allowlistPath, "utf8")) : {};
const ONE_MB = 1024 * 1024;

const SECRET_PATTERNS = [
  [/ghp_[A-Za-z0-9]{20,}/, "GitHub personal access token"],
  [/github_pat_[A-Za-z0-9_]{20,}/, "GitHub fine-grained token"],
  [/sk-[A-Za-z0-9]{24,}/, "API key (sk-...)"],
  [/AKIA[0-9A-Z]{16}/, "AWS access key id"],
  [/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/, "private key material"],
  [/\bBearer\s+[A-Za-z0-9_\-.]{24,}/, "bearer token value"],
  [/(?:api[_-]?key|client[_-]?secret|password|passwd|secret|token)\s*[:=]\s*["'][A-Za-z0-9_\-\/+.=]{16,}["']/i, "credential assignment with a value"],
  [/hsurr:[A-Za-z0-9_\-]{16,}/, "surrogate credential"],
];

const errors = [];
const warnings = [];
const dirs = fs.readdirSync(skillsDir, { withFileTypes: true })
  .filter((d) => d.isDirectory()).map((d) => d.name).sort();

let fileCount = 0;
for (const name of dirs) {
  const dir = path.join(skillsDir, name);
  const skillMd = path.join(dir, "SKILL.md");
  if (!fs.existsSync(skillMd)) { errors.push(`${name}: missing SKILL.md`); continue; }
  let parsed;
  try { parsed = readSkill(dir); } catch (e) { errors.push(`${name}: cannot parse SKILL.md: ${e.message}`); continue; }
  const { meta } = parsed;
  if (meta.name !== name) errors.push(`${name}: frontmatter name '${meta.name}' != directory name`);
  if (!/^\d+\.\d+\.\d+$/.test(meta.version || "")) errors.push(`${name}: version '${meta.version}' is not semver`);
  if (!meta.description || String(meta.description).trim().length < 10) errors.push(`${name}: description missing or too short`);
  if (!["active", "deprecated", "archived"].includes(meta.status)) errors.push(`${name}: status '${meta.status}' not in active|deprecated|archived`);
  if (!["quantum", "imported"].includes(meta.provenance)) errors.push(`${name}: provenance '${meta.provenance}' not in quantum|imported`);
  if (!Array.isArray(meta.tags)) errors.push(`${name}: tags must be a list`);
  if (!Array.isArray(meta.maintainers) || meta.maintainers.length === 0) errors.push(`${name}: maintainers must be a non-empty list`);
  const deps = meta.dependencies;
  if (!deps || typeof deps !== "object" || Array.isArray(deps)) errors.push(`${name}: dependencies must be a mapping`);
  else for (const k of ["tools", "repos", "urls"]) if (!Array.isArray(deps[k])) errors.push(`${name}: dependencies.${k} must be a list`);
  if (meta.aliases !== undefined && !Array.isArray(meta.aliases)) errors.push(`${name}: aliases must be a list`);

  for (const rel of walkFiles(dir)) {
    fileCount++;
    const full = path.join(dir, rel);
    if (rel.split("/").includes(".git") || rel.split("/").includes("__pycache__") || rel.endsWith(".pyc"))
      errors.push(`${name}/${rel}: forbidden VCS/cache artifact`);
    const bytes = fs.statSync(full).size;
    if (bytes > ONE_MB && !(allowlist.files && allowlist.files[`${name}/${rel}`]))
      errors.push(`${name}/${rel}: ${bytes} bytes exceeds 1 MB without an allowlist entry`);
    // secret scan on text-ish files only
    if (/\.(md|txt|json|ya?ml|mjs|js|ts|py|sh|toml|ini|cfg)$/i.test(rel) && bytes < ONE_MB) {
      const content = fs.readFileSync(full, "utf8");
      for (const [re, label] of SECRET_PATTERNS)
        if (re.test(content)) errors.push(`${name}/${rel}: secret scan hit (${label})`);
    }
  }
}

console.log(`Validated ${dirs.length} skills, ${fileCount} files under ${skillsDir}`);
if (warnings.length) { console.log("Warnings:"); for (const w of warnings) console.log("  - " + w); }
if (errors.length) {
  console.log(`FAILED with ${errors.length} error(s):`);
  for (const e of errors) console.log("  - " + e);
  process.exit(1);
}
console.log("OK: all skills valid, secret scan clean.");
