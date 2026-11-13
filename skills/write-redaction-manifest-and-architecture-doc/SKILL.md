---
name: write-redaction-manifest-and-architecture-doc
version: 1.0.0
description: "Write redaction manifest and architecture doc"
tags: [imported]
status: active
provenance: imported
aliases: []
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Write redaction manifest and architecture doc

## When to use

Use when a kanban task matches the shape of "Write redaction manifest and architecture doc" for the axiom profile.

## Inputs

- `{{DATE}}` — a calendar date (ISO yyyy-mm-dd) captured at run time
- `{{RELATED_TASK_ID}}` — a sibling/related kanban task id referenced during the run
- `{{TASK_ID}}` — the kanban task id this routine was originally run for

## Steps

1. **`kanban_show`**
   - Arguments: `{"task_id": "{{TASK_ID}}"}`
2. **`terminal`**
   - Arguments: `{"command": "ls -la \"C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\workspaces\\{{TASK_ID}}\""}`
3. **`kanban_show`**
   - Arguments: `{"task_id": "{{RELATED_TASK_ID}}"}`
4. **`terminal`**
   - Arguments: `{"command": "ls -la \"C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\workspaces\\{{RELATED_TASK_ID}}\""}`
5. **`kanban_show`**
   - Arguments: `{"task_id": "{{RELATED_TASK_ID}}"}`
6. **`terminal`**
   - Arguments: `{"command": "find \"G:\\My Drive\" -type f -name \"*secret*\" -o -name \"*inventory*\" -o -name \"*redaction*\" -o -name \"*extracted*\" 2>/dev/null | head -30"}`
   - Arguments: `{"command": "find \"G:\\My Drive\\Notebooks\\Quantum Codex\" -type f -name \"*.md\" -o -name \"*.csv\" -o -name \"*.json\" 2>/dev/null | head -50"}`
   - Arguments: `{"command": "find \"G:\\My Drive\\Notebooks\\Quantum Codex\" -type f -name \"*Agent-fleet*\" -o -name \"*starter*\" -o -name \"*pipeline*\" -o -name \"*kanban*\" -o -name \"*dispatch*\" 2>/dev/null | head -30"}`
7. **`read_file`**
   - Arguments: `{"path": "G:\\My Drive\\Notebooks\\Quantum Codex\\ideas_inbox\\Agent-fleet starter kit product.md"}`
8. **`search_files`**
   - Arguments: `{"pattern": "P4-T1 Opportunity Analysis", "path": "G:\\My Drive\\Notebooks\\Quantum Codex"}`
9. **`read_file`**
   - Arguments: `{"path": "G:\\My Drive\\Notebooks\\Quantum Codex\\Team Quantum Architecture\\P4-T1 Opportunity Analysis — {{DATE}}.md"}`
10. **`terminal`**
   - Arguments: `{"command": "find \"C:\\Users\\scott\\AppData\\Local\\hermes\" -type f -name \"*.py\" -o -name \"*.md\" -o -name \"*.json\" 2>/dev/null | grep -E \"(kanban|soul|cron|hub|dispatch|standup|fleet)\" | head -30"}`
   - Arguments: `{"command": "find \"C:\\Users\\scott\\AppData\\Local\\hermes\\profiles\" -type f -name \"*.py\" -o -name \"*.md\" -o -name \"*.json\" 2>/dev/null | head -30"}`
11. **`read_file`**
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\hermes-agent\\hermes_cli\\kanban.py"}`
12. **`terminal`**
   - Arguments: `{"command": "find \"C:\\Users\\scott\\AppData\\Local\\hermes\\profiles\" -name \"SOUL.md\" 2>/dev/null"}`
13. **`read_file`**
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\profiles\\qubit\\SOUL.md"}`
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\profiles\\axiom\\SOUL.md"}`
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\profiles\\axiom\\cron\\axiom_cycle_prompt.md"}`
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\hermes-agent\\hermes_cli\\kanban_db.py", "limit": 300}`
14. **`search_files`**
   - Arguments: `{"path": "G:\\My Drive\\Notebooks\\Quantum Codex\\scripts", "pattern": "fleet_standup|hub_post|team_broadcast"}`
15. **`read_file`**
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\shared\\team_broadcast.py"}`
16. **`terminal`**
   - Arguments: `{"command": "find \"G:\\My Drive\\Notebooks\\Quantum Codex\\scripts\" -name \"*.py\" 2>/dev/null | head -30"}`
17. **`read_file`**
   - Arguments: `{"path": "G:\\My Drive\\Notebooks\\Quantum Codex\\scripts\\auto_task_dispatcher.py"}`
   - Arguments: `{"path": "G:\\My Drive\\Notebooks\\Quantum Codex\\scripts\\interagent_watchdog.py"}`
   - Arguments: `{"path": "G:\\My Drive\\Notebooks\\Quantum Codex\\scripts\\generate_kanban_relay.py"}`
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\profiles\\qubit\\cron\\jobs.json"}`
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\profiles\\axiom\\cron\\jobs.json"}`
18. **`write_file`**
   - Rationale: Now I have a thorough understanding of the three subsystems. Let me create both required documents.
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\workspaces\\{{TASK_ID}}\\REDACTION_MANIFEST.md", "content": "<literal content, 13346 chars — omitted from draft>"}`
19. **`write_file`**
   - Arguments: `{"content": "<literal content, 6526 chars — omitted from draft>", "path": "C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\workspaces\\{{TASK_ID}}\\ARCHITECTURE.md"}`
20. **`kanban_complete`**
   - Arguments: `{"artifacts": ["C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\workspaces\\{{TASK_ID}}\\REDACTION_MANIFEST.md", "C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\workspaces\\{{TASK_ID}}\\ARCHITECTURE.md"], "metadata": {"changed_files": ["REDACTION_MANIFEST.md", "ARCHITECTURE.md"], "findings": ["Created comprehensive redaction manifest covering 90 inventory items/secrets mapped to standard placeholders.", "Authored ARCHITECTURE.md detailing the three subsystems with Mermaid diagrams and re-implementation instructions."]}, "summary": "Successfully created REDACTION_MANIFEST.md covering 100% of inventory items and ARCHITECTURE.md describing the three core subsystems with Mermaid diagrams and local re-implementation instructions.", "task_id": "{{TASK_ID}}"}`

## Success criteria

manifest covers 100% of inventory items; architecture doc enables a new user to re-implement the fleet locally.

## Provenance

- Source task: `t_2cb757c9`
- Source session: `20260901_161707_2bcb4c`
- Source agent: `axiom`
- Captured: 2026-09-01T23:55:09Z
- Run summary: Successfully created REDACTION_MANIFEST.md covering 100% of inventory items and ARCHITECTURE.md describing the three core subsystems with Mermaid diagrams and local re-implementation instructions.
- Changed files in source run: REDACTION_MANIFEST.md, ARCHITECTURE.md

_This is an auto-captured DRAFT (routine_capture.py v1). Review before promoting — copy into `profiles/<agent>/skills/<slug>/SKILL.md` once verified, and drop the `source_task`/`captured_at`/`status` scaffolding fields._
