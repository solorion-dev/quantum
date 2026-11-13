# Skill bundle tooling

Tooling for the canonical skills tree at `skills/` in this repo (TRK-0674).

- `validate.mjs` — frontmatter schema lint (name == directory, semver,
  description, status/provenance enums, dependencies shape), secret scan,
  forbidden-artifact check (no `.git`, no `__pycache__`), and the 1 MB file
  rule with `allowlist.json` as the only escape hatch.
- `build-manifest.mjs` — walks `skills/`, validates frontmatter by reading it,
  and emits `skills/manifest.json` with a per-file sha256, per-skill totals,
  the bundle version (`v2026.11.0` at seed) and the bundle commit.
- `frontmatter.mjs` — the small shared frontmatter parser both tools use.

## Usage

```sh
node tools/skill-bundle/validate.mjs
node tools/skill-bundle/build-manifest.mjs   # BUNDLE_COMMIT=<sha> to pin
```

`skills/manifest.json` is generated, never hand-edited. CI
(`.github/workflows/skills-validate-manifest.yml`) validates on every PR that
touches `skills/**` and regenerates the manifest on merge to `main`.
