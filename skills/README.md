# Quantum Official Skills

This tree is the canonical home of the fleet's official skills for
`solorion-dev/quantum`. A skill is **official iff it is on `main` under
`skills/`** — merged through a reviewed PR. Consumers (fleet agents) pull
skills through the Quantum MCP tools (`quantum_skills_list`,
`quantum_skills_find`, `quantum_skills_get`), verify each file's sha256
against `manifest.json`, and pin `(name, version, bundle_commit)` locally.

## Layout

- One directory per skill; the directory name **is** the canonical skill name
  and must equal the `name` in `SKILL.md` frontmatter.
- `SKILL.md` is required. Supporting material lives in `references/`,
  `scripts/`, `evals/`, and `assets/` as needed.
- `manifest.json` is **generated** by `tools/skill-bundle/build-manifest.mjs`
  (CI regenerates it on merge to `main`); never hand-edit it.

## Frontmatter contract

```yaml
---
name: quantum-systems            # must equal directory name
version: 1.0.0                   # per-skill semver
description: "One or two lines: what this skill is for and when to use it."
tags: [quantum, fleet]
status: active                   # active | deprecated | archived
provenance: quantum              # quantum (fleet-authored) | imported (third-party set)
aliases: []                      # retired names that should still resolve (e.g. local-*)
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
```

## Rules

- No secrets by value, ever — reference credentials by vault location only.
  The validator's secret scan enforces this.
- No `.git` internals, no `__pycache__`, no file over 1 MB without an
  explicit allowlist entry in `tools/skill-bundle/allowlist.json`.
- Skill PRs are **never** docs-only auto-merges: a skill change is a behavior
  change for every agent that pulls it, and gets the same review as code.
- `provenance: imported` skills are third-party sets kept as-is (descriptions
  normalized at import); they are present so this tree holds all skills, and
  are never presented as fleet-authored.

## Proposing a change

Open a PR against `skills/<name>/` from a `worker/<agent>/...` branch, run
`node tools/skill-bundle/validate.mjs`, and bump the skill's semver
(patch = wording fixes, minor = new sections/capabilities, major = procedure
or contract change). Local edits on a consumer are drafts — the path back is
a PR here, where review happens once for the whole fleet.
