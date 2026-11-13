---
name: draft-gumroad-listing-copy-and-pricing-page
version: 1.0.0
description: "Draft Gumroad listing copy and pricing page"
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
# Draft Gumroad listing copy and pricing page

## When to use

Use when a kanban task matches the shape of "Draft Gumroad listing copy and pricing page" for the pulsar profile.

## Inputs

- `{{RELATED_TASK_ID}}` — a sibling/related kanban task id referenced during the run
- `{{TASK_ID}}` — the kanban task id this routine was originally run for

## Steps

1. **`kanban_attachments`**
   - Rationale: Good. Now let me check the architecture doc from the sibling task for product details, and check what the workspace already contains.
   - Arguments: `{"task_id": "{{RELATED_TASK_ID}}"}`
2. **`read_file`**
   - Rationale: Let me read the architecture doc and redaction manifest for product context.
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\attachments\\{{RELATED_TASK_ID}}\\ARCHITECTURE.md"}`
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\attachments\\{{RELATED_TASK_ID}}\\REDACTION_MANIFEST.md"}`
3. **`write_file`**
   - Rationale: Now I have full context. The product is an "Agent-Fleet Starter Kit" — a redacted template for self-hosted local-LLM agent fleets. Let me now create both files in the workspace.
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\workspaces\\{{TASK_ID}}\\LISTING_COPY.md", "content": "<literal content, 3421 chars — omitted from draft>"}`
4. **`write_file`**
   - Rationale: Now I have full context. The product is an "Agent-Fleet Starter Kit" — a redacted template for self-hosted local-LLM agent fleets. Let me now create both files in the workspace.
   - Arguments: `{"path": "C:\\Users\\scott\\AppData\\Local\\hermes\\kanban\\workspaces\\{{TASK_ID}}\\PRICING.md", "content": "<literal content, 1390 chars — omitted from draft>"}`
5. **`terminal`**
   - Rationale: Both files written and verified. Let me verify they exist and read back the content to confirm integrity.
   - Arguments: `{"command": "ls -la C:/Users/scott/AppData/Local/hermes/kanban/workspaces/{{TASK_ID}}/"}`
6. **`kanban_request_review`**
   - Rationale: Both files are in place. Now let me request review since this task has specific deliverables (listing copy + pricing) that should be reviewed before completion.
   - Arguments: `{"summary": "Created listing copy (LISTING_COPY.md) and pricing page (PRICING.md) for the Agent-Fleet Starter Kit product. Pricing set at $19 Personal / $39 Team tiers. Listing copy uses a pragmatic builder voice targeting developers and technical founders — covers what's included, FAQ, and refund policy. Pricing page includes a feature comparison table and rationale for the price points.", "metadata": {"changed_files": ["LISTING_COPY.md", "PRICING.md"], "deliverables": "Listing copy + pricing page for Gumroad-style product listing"}, "reviewer": "pulsar"}`

## Success criteria

copy fits Gumroad's 5000-char limit; pricing table clear; no references to internal codenames or unpublished infra.

## Provenance

- Source task: `t_4e895ec6`
- Source session: `20260901_173003_ea4f40`
- Source agent: `pulsar`
- Captured: 2026-09-01T23:55:09Z
- Run summary: Created listing copy (LISTING_COPY.md) and pricing page (PRICING.md) for the Agent-Fleet Starter Kit product. Pricing set at $19 Personal / $39 Team tiers. Listing copy uses a pragmatic builder voice targeting developers and technical founders — covers what's included, FAQ, and refund policy. Pricing page includes a feature comparison table and rationale for the price points.
- Changed files in source run: LISTING_COPY.md, PRICING.md

_This is an auto-captured DRAFT (routine_capture.py v1). Review before promoting — copy into `profiles/<agent>/skills/<slug>/SKILL.md` once verified, and drop the `source_task`/`captured_at`/`status` scaffolding fields._
