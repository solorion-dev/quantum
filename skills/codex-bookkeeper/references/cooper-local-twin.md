# Cooper local twin (pre-reconciliation)

Seeded from Codex `codex-bookkeeper`; this is the divergent local copy (`local-codex-bookkeeper`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# Codex Bookkeeper

## Orient before touching anything

- Find the vault first. On Tritium it is the live mount at /home/scott/codex, elsewhere it is the Google Drive folder Quantum Codex. The real folder holds Quantum Codex Master Index.md, projects and system, and a decoy folder of the same name sits nested inside it. Read references/access-modes.md when you are not on Tritium.

- Read the normative documents fresh every session and let them override this skill. They are Quantum Codex Rules and Guidelines, system/codex_structure.md, the project and goal system docs plus templates, system/tag_taxonomy.md, and the structure rationale note. Memory of them never beats the current text.

- Read the latest dated report in Bookkeeping/reports before starting, and carry forward anything it left open.

## Keep every note conformant

- Use Markdown only and never let Drive convert a note to a Google Doc.

- Give every note full frontmatter in canonical order, quoting dates and times so YAML does not misread them. Bump last_updated, time_updated and last_edited_by on every edit, and version on meaningful changes. Exempted files are agent SOUL.md files, skill-manifest.md, Bookkeeping/logs, machine output in Bookkeeping/reports, _templates and skill files.

- Write from the templates, never from memory, and let a system template win when a Templater template disagrees with it. Never invent a rationale template because the vault deliberately has none.

- Keep filenames free of brackets, pipes, hash, caret, colon, backslash, slash, star, question mark, less-than and greater-than characters. Dated notes use the YYYY-MM-DD Title form and goal files use the ABBR-NNN CODENAME form followed by a short name.

- Link to facts instead of copying them, and quote a number only with its date. Path-qualify wikilinks such as OVERVIEW, ROADMAP and INDEX with their project folder so they never resolve to the wrong file.

- Archive superseded material with status Archived and a successor pointer instead of deleting it. Delete only regenerable junk such as caches, .pyc files, empty folders and diffed sync conflicts.

- Never store secrets in the vault. When you find one, redact it in place, record the file path and secret type in your report, and flag that it must be rotated because it has already synced to Drive.

- Keep a spec row in system/codex_structure.md section 1 for every top-level folder you create. A folder with no spec row is how stray folders happened before.

- Stay in your lane and record what was disproven. You organize and conform but never decide: leave other agents SOUL.md files, live config, decision-tier items and the private Haven space alone, and write decision needs as answerable questions. Say in your report what you checked and found fine so the next bookkeeper does not recheck it. Sign your work with your own agent name, never Scotty.

## Check conformance with a script that exists

- Run the conformance linter only when the script file actually exists in the skill copy you are using. If the installed copy has no scripts folder, look for the script in the canonical Codex copy or apply the same checks by reading. Never claim a lint run you did not run.

- Aim the linter at the folder you were asked to audit or the files you touched, never at the whole vault in one walk. A whole-vault walk stalls every other reader of the Drive mount for minutes.

- With the links flag, check for unresolved wikilinks. Run the secrets scan from Bookkeeping/tools/vault_secret_scan.py when checking for secrets.

- Fix mechanical issues such as missing or misordered frontmatter fields, bad dates, wrong statuses and mistyped goal phases. When renaming a file, update every inbound wikilink in the same session, and if you cannot update them all, do not rename the file.

## File rough notes and keep the maps true

- Turn rough notes into correct notes before touching anything else. Sources are CLUTTERED DOCS, spill notes, notes flagged action/needs-triage and loose files at the root. The ideas_inbox folder is machine watched, so leave it alone unless asked.

- Split each rough note into items of one idea, request, fact or decision each. Classify each item with references/note-types.md, which maps the item to its template and destination folder.

- Search projects/README.md, the project INDEX.md, projects/Proposals and the DSECT Handbook before creating anything. Append to the existing home as a task or log entry and never start a parallel note.

- Create or extend the note from its template, keeping Scotty intent and avoiding padding. Tasks addressed to an agent become Tasks-plugin checkboxes on the right goal with the assignee kept.

- Leave a trail in the source note with dated filed entries that link where each item went. Mark triaged yes only when every item is filed, and archive the source only when Scotty note says it is done with.

- After creating, moving, renaming or archiving anything, update every map that points at it. Those are projects/README.md, the project INDEX.md goals table, the DSECT Handbook and Portfolio when a project changes, Quantum Codex Master Index.md for new top-level hubs, Skills/SKILL INDEX.md for new skills, the Template Catalogue for new templates and Plugin Index.md for plugin changes.

- Use only tags from system/tag_taxonomy.md. Propose a missing tag in the taxonomy proposed table and mention it in your report rather than using it silently.

- Create a template in _templates only after the same note shape was written by hand three times. Start it with the Templater script block and put no frontmatter of its own above that block.

## Fold Quantum Memory and close the report

- Open memory with list_memories for agent fleet, tier durable, ordered by recent. Fold near duplicates into one note instead of keeping a second durable row.

- When two live decisions contradict, write a correction naming both memory ids. Never delete either row in the same session.

- Dry run prune_memories for expired rows first, and confirm only on an assigned bookkeeper pass. A durable delete of a live row is bookkeeper-only and never unassigned.

- Write the dated report at Bookkeeping/reports/YYYY-MM-DD Bookkeeper Report - <agent>.md with full frontmatter and the team-quantum, report and bookkeeping tags. Append a dated section when one from you already exists for today.

- Cover scope, filed items, fixes, checked and fine items, needs Scotty questions, and left open work for a successor. Post a one line summary of the report path to the hive as a note, with no balances in the stamp.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Use the local-quantum skill for other fleet routing such as systems, mail, goals or todos before this skill. The old Quantum Bookkeeper pointer now lives here: file, lint, fold memory and report under this one skill.