// Minimal frontmatter parser shared by validate.mjs and build-manifest.mjs.
// Handles the envelope written by the seed (and the common shapes found in the
// source trees): plain/quoted scalars, folded (>) and literal (|) blocks,
// inline lists, block lists, and a nested dependencies mapping.
import fs from "node:fs";

export function parseFrontmatter(text) {
  if (!text.startsWith("---")) return { meta: {}, body: text };
  const end = text.indexOf("\n---", 3);
  if (end === -1) return { meta: {}, body: text };
  const raw = text.slice(3, end);
  const body = text.slice(end + 4);
  const meta = {};
  const lines = raw.split("\n");
  let curKey = null;
  let curParent = null;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const indent = line.match(/^\s*/)[0].length;
    const m = line.match(/^\s*([A-Za-z_][\w-]*):\s*(.*)$/);
    if (m && indent === 0) {
      curKey = m[1]; curParent = null;
      const val = m[2].trim();
      if (val === ">" || val === ">-" || val === "|" || val === "|-") {
        const folded = val.startsWith(">");
        const buf = [];
        i++;
        while (i < lines.length && (/^\s/.test(lines[i]) || !lines[i].trim())) { buf.push(lines[i].trim()); i++; }
        i--;
        meta[curKey] = buf.join(folded ? " " : "\n").trim();
      } else if (val.startsWith("[") && val.endsWith("]")) {
        meta[curKey] = val.slice(1, -1).split(",").map((x) => x.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
      } else if (val === "") {
        meta[curKey] = {};
      } else {
        meta[curKey] = val.replace(/^["']|["']$/g, "");
      }
      continue;
    }
    if (m && indent >= 2 && curKey) {
      // nested key (dependencies.*)
      if (typeof meta[curKey] !== "object" || Array.isArray(meta[curKey])) meta[curKey] = {};
      const val = m[2].trim();
      if (val.startsWith("[") && val.endsWith("]")) {
        meta[curKey][m[1]] = val.slice(1, -1).split(",").map((x) => x.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
      } else {
        meta[curKey][m[1]] = val.replace(/^["']|["']$/g, "");
      }
      curParent = m[1];
      continue;
    }
    const li = line.match(/^\s+-\s+(.*)$/);
    if (li && curKey) {
      const item = li[1].trim().replace(/^["']|["']$/g, "");
      if (curParent && typeof meta[curKey] === "object" && !Array.isArray(meta[curKey])) {
        if (!Array.isArray(meta[curKey][curParent])) meta[curKey][curParent] = [];
        meta[curKey][curParent].push(item);
      } else {
        if (!Array.isArray(meta[curKey])) meta[curKey] = [];
        meta[curKey].push(item);
      }
      continue;
    }
    // wrapped plain scalar continuation
    if (indent > 0 && curKey && typeof meta[curKey] === "string" && meta[curKey]) {
      meta[curKey] = meta[curKey] + " " + line.trim();
    }
  }
  return { meta, body };
}

export function readSkill(skillDir) {
  const p = skillDir + "/SKILL.md";
  const text = fs.readFileSync(p, "utf8");
  return parseFrontmatter(text);
}

export function walkFiles(dir, base = dir, out = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = dir + "/" + ent.name;
    if (ent.isDirectory()) walkFiles(full, base, out);
    else if (ent.isFile()) out.push(full.slice(base.length + 1));
  }
  return out.sort();
}
