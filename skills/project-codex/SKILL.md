---
name: project-codex
version: 1.0.0
description: "Plan, organise and track project work in the Quantum Codex — the shared Obsidian vault in Google Drive. Use this whenever you are given a substantial goal, start or pick up a project, need to know what work is already in flight, or are about to write a plan, roadmap, overview or status document. Also use it before."
tags: [quantum]
status: active
provenance: quantum
aliases: [local-project-codex]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Project & Goal system — Quantum Codex

The Codex is a shared Obsidian vault, synced through Google Drive, that every agent in this
fleet reads and writes. It has a governance document with ten commandments and a normative
directory spec. **Those rules win over anything here.** This skill is the practical procedure
for the part they leave to you: how to name a goal, where to file it, and what it must say.

Read the vault's own rules when you need detail:

- `Quantum Codex Rules and Guidelines.md` — the ten commandments
- `system/codex_structure.md` — the normative directory spec
- `system/project_goal_system.md` — the spec this skill implements
- `projects/README.md` — **the authoritative project and goal index**

## Locate the vault first

The Codex is `Quantum Codex` in Google Drive, folder id `1U5p03fRWPjbx2VtaBCaoL186ZdXthanf`.

> [!warning] There are two folders called "Quantum Codex".
> A second, nearly-empty one (`1uOutqcHeGhWhG8qrRFrDmIwgYAU-Ilmc`) is nested *inside* the real
> one. The real vault is the one containing `Quantum Codex Master Index.md`, `projects/` and
> `system/`. Confirm before writing, or your note lands somewhere nobody reads.

Useful folder ids:

| path | id |
|---|---|
| vault root | `1U5p03fRWPjbx2VtaBCaoL186ZdXthanf` |
| `projects/` | `1VdtkCPT2wGSsL8LUpEl6K4pud31zDlQP` |
| `projects/project_rationales/` | `1nL6WiWm2IWrGHyc2kyu7YsSENvE5GJ9A` |
| `system/` | `1tPkORH7yn7ZhTEp_EjaTGr9_8XoAjXPZ` |
| `Skills/` | `1yT6DX9xWjWCEW6xM_eb3NuYDH-LuK8fm` |

## Naming a goal

Substantial work gets an identifier:

```
[ABBR-NNN] "CODENAME" — Short Name
```

- **ABBR** — 2–4 uppercase letters, one per project, registered in `projects/README.md`.
- **NNN** — zero-padded, monotonic within the project, **never reused** even after cancellation.
- **CODENAME** — one uppercase word, unique across every project. This is what you say out loud.
- **Short Name** — plain language, ≤ 8 words.

Example: `[NEB-002] "CODA" — Local Audio Generation`

### The filename must NOT use that form

> [!warning] `[`, `]` and `"` break Obsidian and Windows. This is the single most common way to
> create a note nobody can link to.
> Obsidian WikiLink targets cannot contain `[ ] | # ^` — `[[[NEB-001] "GAUGE" — …]]` terminates
> at the first `]` and silently resolves to nothing. And `"` is an **illegal filename character
> on Windows**, where most of this fleet runs with the vault at `G:\My Drive\Notebooks\`.

| where | form |
|---|---|
| filename | `NEB-002 CODA — Local Audio Generation.md` |
| `title:` frontmatter and `# H1` | `[NEB-002] "CODA" — Local Audio Generation` |
| link | `[[NEB-002 CODA — Local Audio Generation]]` |

Never put `" [ ] | # ^ : \ / * ? < >` in a filename. The em dash `—` is safe everywhere.

### What earns an ID

More than one sitting of work, or something another agent may need to pick up. A one-line fix
does not. When unsure, give it one — an unused ID costs a table row; untracked work costs the
reasoning behind it.

## The project folder tree

Every project under `projects/<Project Name>/` has the same shape, so an agent dropped into any
project finds the same things in the same places:

```
projects/<Project Name>/
├── OVERVIEW.md      what this is, who leads it, where the code lives, what is true today
├── ROADMAP.md       phases and sequencing; the long range
├── INDEX.md         this project's goals table and document map
├── goals/           one note per goal, named as above
├── reference/       measured facts and specs that outlive any single goal
└── archive/         superseded docs, never deleted
```

**These three are different documents and must not be merged.** Overview answers "what is
this?", roadmap "in what order?", index "where is everything?". Merged, none stays current.

The **rationale does not live here** — per Commandment 3 it is
`projects/project_rationales/Rationale <Project Name>.md`. One home, one copy.

Templates are in `system/`: `template_project_overview.md`, `template_project_roadmap.md`,
`template_project_index.md`, `template_goal.md`.

## Linking

- Cross-references use WikiLinks (Commandment 8).
- **Path-qualify `OVERVIEW` / `ROADMAP` / `INDEX`** — every project has files with those names,
  so `[[ROADMAP]]` is ambiguous. Write `[[projects/<Project Name>/ROADMAP]]`.
- Goal notes carry their ID in the filename and are globally unique, so they may be linked bare.
- **Prefer a link over a copy, always.** This vault has repeatedly grown a second stored copy of
  something and then drifted — `kanban_relay.md`, `Team Quantum/A2A_COMM.md`, `skills_library/`.
  Each was a link that should have stayed a link.
- Facts that live in code or a repo document stay there. Quote a number here only with a date
  attached. A restated number goes stale silently — a disk figure in this fleet read 99% for
  weeks while the disk sat at 73%.

## Frontmatter

Every note carries the full Commandment 2 schema — **all thirteen fields, no partial subsets**:

```yaml
---
title: "…"
author_agent: "…"
agent_id: "…"
last_edited_by: "…"
date_created: "YYYY-MM-DD"
time_created: "HH:MM:SS"
last_updated: "YYYY-MM-DD"
time_updated: "HH:MM:SS"
status: "Draft | Active | Pending Review | Completed | Archived"
maintained_by: "Qubit (Tritium Orchestrator)"
version: "1.0.0"
tags: [...]
related_files: ["[[…]]"]
---
```

Goal notes add `goal_id`, `codename`, `project`, `phase` — these are what make a goals table
generable rather than hand-maintained.

## What a goal note must contain

1. **Why this exists** — the problem in the user's terms, not the solution. If this is hard to
   write, it is probably a task on some other goal.
2. **Acceptance** — how *anyone* can tell it is done, checkable without asking the author.
   "Fast" is not acceptance; "a view lands in under a minute on the RTX" is.
3. **Constraints inherited** — the project rules this work must not break.
4. **Tasks** — a checklist, kept current.
5. **Log** — dated: what was tried, what was measured, **what was disproven**.

> The disproven half is the valuable half. A note recording only what worked forces the next
> agent to re-run every dead end. Investigations in this fleet have been repeated for exactly
> this reason.

## Lifecycle

```
Draft → Active → Pending Review → Completed
                              └─→ Archived (superseded or cancelled)
```

- `Completed` requires the acceptance criteria actually checked off. If acceptance changed, say
  so in the log first — otherwise the status is a lie.
- `Archived` requires a **successor pointer** in `related_files` or an inline callout. An
  archive with no forwarding address is a dead end.
- IDs are never reused. A cancelled `NEB-004` stays cancelled.

## Operational facts about writing to the Codex

- **Markdown only.** Create files as `text/markdown` with `disableConversionToGoogleType: true`,
  or Drive turns them into Google Docs and breaks Commandment 1.
- **The Drive connector cannot update file content** — only create, rename, move and trash. To
  change a document: create the new version with the same title in the same folder, then trash
  the old file id. Trash is recoverable for 30 days, so nothing is lost. Do not leave both.
- **No secrets, ever, anywhere in the vault.** Everything under it syncs to Drive. This rule has
  already been broken once — nine live API keys sat in cleartext until 2026-08-28 and had to be
  rotated. Secrets are referenced by path, never by value.
- **No code or state artifacts** under the vault: no `.venv/`, `__pycache__/`, `node_modules/`,
  `.pytest_cache/`, no SQLite databases. Local disk is truth; the Codex is published Markdown,
  one way.
- **Dated notes** are named `YYYY-MM-DD <Title>.md`.

## Procedure — starting a goal

1. Find the project in `projects/README.md`. **If it is not there, it does not exist to the
   team** — add it with a rationale first.
2. Take or register the project `ABBR`. Take the next `NNN`. Pick a `CODENAME` not used anywhere.
3. Copy `system/template_goal.md` into `projects/<Project>/goals/` with the bracket-free
   filename.
4. Fill **Why this exists** and **Acceptance** *before writing any code*. If you cannot state
   acceptance, you do not understand the goal yet — go ask.
5. Add the row to the project's `INDEX.md` **and** to `projects/README.md`.
6. Work. Log what you measure, including the failures.
7. On completion: check acceptance, set `status: Completed`, update both indexes.

## Procedure — starting a project

1. Write `projects/project_rationales/Rationale <Project>.md` first. No rationale, no project.
2. Create `projects/<Project Name>/` with `OVERVIEW.md`, `ROADMAP.md`, `INDEX.md` from the
   templates, plus an empty `goals/`.
3. Register it in `projects/README.md` with its ABBR.
4. Then start goal `ABBR-001`.

## Common mistakes

| mistake | consequence |
|---|---|
| Brackets or quotes in a filename | Unlinkable in Obsidian; uncreatable on Windows |
| Bare `[[ROADMAP]]` | Resolves to some other project's roadmap |
| Partial frontmatter | Non-conformant; the vault linter flags it |
| A second copy instead of a link | The documented, repeated failure mode of this vault |
| Restating a number from code | Goes stale silently and misleads a future decision |
| `Archived` with no successor | A dead end for whoever follows the link |
| Skipping the rationale | The project "does not exist to the team" |

## Worked example

Scott: *"Let's add real-time disk usage to the Machine tab."*

1. Nebula is in `projects/README.md`, ABBR `NEB`. Next number is 001.
2. Codename **GAUGE** — not used anywhere else.
3. File: `projects/Nebula (Art Generation)/goals/NEB-001 GAUGE — Machine Tab and Live Disk View.md`
4. Title inside: `[NEB-001] "GAUGE" — Machine Tab and Live Disk View`
5. **Why**: disk has been quoted stale twice and drove real decisions wrongly; checking the box
   means SSH and `htop`.
6. **Acceptance**: values match `df -h` at the same moment; the tab keeps updating *while a
   render runs on both cards*.
7. Rows added to `projects/Nebula (Art Generation)/INDEX.md` and `projects/README.md`.
8. Then, and only then, write code.
