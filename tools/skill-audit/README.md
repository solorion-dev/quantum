# skill-audit

**Find dead references in agent skill files before they rot.**

Skills (`SKILL.md` and their reference files) point at real things: files on
disk, helper scripts, sibling documents, GitHub repos. Those things move,
get renamed, or live on a different machine. When a skill silently references
something that no longer exists, the agent following it fails mid-task —
usually at the worst moment. `skill-audit` scans skill Markdown, extracts
the references, and verifies them.

Born from a real pattern: a fleet whose skills accumulated stale paths
across machines (a home server, a laptop, an agent VM) until nobody could
tell which instructions still described reality.

## What it checks

| Reference kind | How it's found | How it's verified |
| --- | --- | --- |
| Absolute / `~/` paths | path patterns in prose and code | exists on this host |
| Skill-folder refs | backticked `references/…`, `scripts/…`, `assets/…`, `templates/…` | exists under the skill root |
| Markdown links | `[text](target)` with a local target | exists relative to the linking file |
| GitHub repos | `github.com/owner/repo`, backticked `` `owner/repo` ``, `gh -R owner/repo` | `gh repo view` (only with `--check-repos`) |

## Host awareness (the important part)

A path can be *unverifiable* rather than dead, and the tool says so instead
of crying wolf:

- Paths under another user's home (`/home/scott/…` when you are not Scott)
  are **unverified — different host/user**, not dead. Skills written for a
  home server shouldn't fail an audit run on an agent VM.
- Paths under `--remote-prefix` mounts (default `/mnt/`) are unverified.
- `/tmp/…` paths are **skipped** — ephemeral by definition.
- Template and date placeholders (`{{NAME}}`, `week-YYYY-MM-DD.yaml`,
  `${VAR}`) are **skipped**, not dead.
- **Declared host-scoped paths** are **unverified**, not dead (see below).
  Some paths legitimately live on only one host — e.g. a skill about a
  home server referencing `~/.cloudflared/` in prose that itself says
  the config lives on that server. The heuristic rules above can't know
  that, so the skill author declares it, in either of two ways:

  1. **Inline directive** — put the HTML comment
     `<!-- skill-audit: host-scoped -->` on the *same line* as the
     reference:

     ```markdown
     Derive names from the tunnel configs (`~/.cloudflared/`) on Tritium. <!-- skill-audit: host-scoped -->
     ```

     The directive covers only path, skill-folder, and link references
     extracted from that line (not GitHub repo references). A directive
     on its own line declares nothing.

  2. **Per-skill ignore file** — a `.skill-audit-ignore` file in the
     skill root, one entry per line: a path prefix exactly as references
     are written, optionally followed by `# reason`:

     ```text
     # Tritium host only
     ~/.cloudflared/ # cloudflared configs live on Tritium
     ```

     Blank lines and comment-only lines are ignored. A reference whose
     written value starts with a listed prefix is covered.

  Either way the contract is narrow: a declared path that *does* exist
  on this host still reports `ok`; a declared path missing here reports
  `unverified` with a detail naming the declaration (and the ignore-file
  reason, when given); an *undeclared* missing path still reports
  `dead` and still fails the run (exit `1`). Declarations never rescue
  anything else, and `--strict` still fails on the resulting
  `unverified` findings if you want declared paths to stay visible.

Statuses: `ok`, `dead`, `unverified`, `skipped`. Exit code is `1` when any
reference is dead, `0` when clean, `2` on usage error. `--strict` also
fails on unverified references. `--json` emits a machine-readable report.

## Usage

```bash
# Audit the default skill locations (~/workspace/custom-skills, /opt/muse/skills)
python3 src/skill_audit.py

# Audit specific roots, including GitHub repo checks
python3 src/skill_audit.py ~/workspace/custom-skills --check-repos

# JSON for automation / CI
python3 src/skill_audit.py ~/workspace/custom-skills --json > report.json
```

No dependencies beyond Python 3.10+ (stdlib only). Repo checks shell out to
the GitHub CLI (`gh`) when asked; without it, repos report as unverified.

## First real run (2026-10-17, the author's fleet)

33 custom skills scanned. Repo check: 7 distinct GitHub repos referenced,
all resolve. After host-awareness filtering, three path findings worth a
human's attention:

- `local-codex-bookkeeper` references `scripts/codex_lint.py`, which does
  not exist in the installed copy — genuine rot.
- `local-codex-bookkeeper` references `~/.claude/skills/codex-bookkeeper/`
  (a Claude Code install on another machine) with a `~/` that only resolves
  on that machine.
- Container-internal paths (e.g. a Docker volume target `:/home/agent`) can
  surface as false positives; they are visible in the report and easy to
  eyeball.

An early version of the repo extractor also flagged file paths wearing a
repo costume (`` `references/access-modes.md` ``, `` `projects/README.md` ``)
— 57 phantom "dead repos." The shipped extractor filters folder-name
owners and file-extension names; that failure mode is covered by tests.

## Known limitations

- Bare `owner/repo` detection is heuristic (backticked tokens and `gh`
  usages); a denylist filters common non-repos like `text/plain`.
- Paths inside shell snippets that are *created* by the skill's own steps
  will read as dead until they exist.
- No HTTP checking of non-GitHub URLs — offline by design.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## License

GPL-3.0.
