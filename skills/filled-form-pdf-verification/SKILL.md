---
name: filled-form-pdf-verification
version: 1.0.0
description: "Verify filled-form PDFs (WROC sheets and other pre-printed forms) at zoomed-crop resolution and deliver every revision under a fresh filename, so field-placement defects and stale cached attachments never reach the user."
tags: [quantum]
status: active
provenance: quantum
aliases: [local-filled-form-pdf-verification]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Filled-Form PDF Verification and Delivery

## Purpose
Catch the field-placement defects that a full-page view hides on pre-printed forms, and make sure the user actually receives the revised file — not a cached copy of the previous one.

## Workflow
1. Finish the PDF through its normal build path (for Scotty's weekly paperwork, the `wroc` skill), then run the general gates in the `artifact_testing` skill. A passing gate or a clean full-page render is not verification for a filled form.
2. Rasterize each page at high resolution and inspect zoomed crops of every field region, not just the full page: the header and name/date lines, each marks or checkbox row, the shift-time and totals rows, each narrative box, and the signature/total row.
3. In each crop, check placement, not just presence: marks are centered inside their boxes, text sits on its ruled line rather than floating above or dropping below it, date and time digits do not cross slashes or rules, totals land on the totals row (not the signature row), and no ruled line strikes through narrative text.
4. Fix defects in the source (the YAML or generator), never by hand-editing the PDF. Re-render, then re-inspect crops of the changed regions and their neighbours.
5. Verify the exact file that will be sent — the final render, under its final filename. Never verify an earlier render and send a later one, or vice versa.
6. Deliver every revision under a fresh filename (for example, append `-rev2`, `-rev3`, or a new date-time stamp). State the new filename in the message so the user can confirm they are looking at the new file.

## Output Contract
A filled-form PDF is reported as checked only when each field region has been inspected as a zoomed crop of the exact file being delivered, and the delivery names the fresh filename the revision was sent under.

## Operating Rules
1. A full-page thumbnail or screenshot never counts as verification for a form with ruled lines, boxes, or pre-printed fields.
2. Never claim the form was "checked line by line" unless the crops in step 2 were actually viewed.
3. Never resend a revised attachment under the same filename — the user's mail/chat app caches attachments by name and will show the stale version.
4. A one-character fix still gets a fresh filename and a fresh crop check of the affected region.
5. If the user reports seeing an old version or a misplaced field, treat that as the authoritative view: fix, re-render under a new filename, and re-verify the crops of the sent file before claiming it is fixed.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
