---
name: wroc
version: 1.0.0
description: "Build Scotty''s weekly WROC paperwork: from Paycom punches to a validated, supervisor-ready PDF. Triggers on WROC, weekly notes, timesheet paperwork, Living Innovations documentation."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-wroc]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# WROC Builder

## Purpose
Produce the weekly WROC (Weekly Record of Client Services) PDF for Scotty's DSP work at Living Innovations without touching Google Slides. Structured YAML in, validated PDF out.

## Workflow
1. **Pull Paycom punches** for the week (Mon–Fri). See `references/paycom.md`. Use real punches, never estimates. Note the service code per shift: 33 = Home Support, 36 = Community.
2. **Write the week YAML.** Copy `assets/week-template.yaml` to `~/workspace/wroc/weeks/week-YYYY-MM-DD.yaml` and fill it: dates, shift start/end times, the care marks (8+8 for code 33, 7+7 for code 36; codes T/PA/VP/M/D), the narrative sections (one ~500–660 char Describe-services narrative for 33; three shorter sections for 36: services/job/choices), and the goal-progress text. Conventions in `references/conventions.md`.
3. **Generate:** `python3 bin/wroc.py ~/workspace/wroc/weeks/week-YYYY-MM-DD.yaml -o ~/workspace/wroc/weeks/JC-WROCs-Week-of-MM-DD-YY.pdf`
4. **Verify visually.** Open the PDF and check every page: header code matches the service code, dates/times/totals, all 16 marks, narratives inside their boxes, no text collisions. Fix the YAML and re-run; never hand-edit the PDF.
5. **Email** per the standing format (to Lindsay Bryant at lbryant@livinginnovations.com, subject `Scott Venable - Weekly WROCs (JC) [M/D/YY]`, body from the Aug 2026 template). Show Scotty the exact recipient/subject/body/attachment and get explicit approval before sending. Send from his Gmail, no CC.

## Output Contract
- One PDF, one page per workday, US Letter, official form backgrounds.
- Validation runs before every render: shift math (end > start, totals computed), marks count per form (8+8 for 33, 7+7 for 36) with legal codes, non-empty narrative sections and goal, narrative length and dash warnings, goal-length warning. Errors block rendering unless `--force`.

## Operating Rules
- **Program codes 33 and 36.** Both the Home Support background (`assets/hs33.png`) and the Community background (`assets/c36.png`) are measured. Each day renders on its own code's form: set the week-level `program_code` as the default and override per day (`program_code: "36"`) for mixed weeks like a Friday Community shift. If a future code is needed, follow `references/adding-a-form.md` — do not fake it on another form.
- Paycom is read-only unless Scotty explicitly asks for edits/submission.
- 0.25-hr paperwork blocks go in the narrative; shift totals show direct-support hours only.
- Never store credentials, last-4s, or one-time codes in the YAML, notes, or memory. Paycom login lives in Secure Vault; the 6-digit email code is manual each time.
- Keep last week's YAML for wording comparison so narratives stay fresh.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
