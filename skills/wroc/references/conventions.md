# WROC conventions (standing, from Sept 2026)

## Hours
- Use actual Paycom punches, never estimates.
- 0.25-hour admin paperwork blocks are mentioned in the day's narrative but
  excluded from the WROC shift totals (direct-support hours only).
- Weekly total = sum of direct-support hours. (Week of 9/21/26: 41.00 direct + 0.50 paperwork = 41.50.)

## Service codes
- Home Support = code 33. Community Membership = code 36.
- The header program code on the form must match the Paycom service code for that shift.
- If a week mixes codes, each day renders on its own code's form: the week-level `program_code` is the default and any day can override it with its own `program_code`.
- The 36 form has 7 care rows (14 marks) and three narrative sections (`narrative_services`, `narrative_job`, `narrative_choices`) instead of one narrative box. Its baked goal reads "Goal: I would like to develop relationships with others in the community and develop a valued role." — the YAML `goal` holds the progress text after it, same as the 33 form.

## Narratives ("Describe services")
- ~500–660 characters so the text fills the box without overflowing.
- Fresh wording every week: compare against the prior week's YAML before finalizing.
- No em dashes or en dashes.
- Third person: "staff"/"JC", never the full name.
- Mention the 0.25-hr paperwork block where it happened (e.g. "After the shift, staff completed client documentation from 8:00 to 8:15 PM.").

## Goal progress
- Keep under ~200 characters so it fits in two lines above the next "Goal:" label; the generator warns past that.
- Format: "Goal: Develop ADLS skills." is baked into the form; the YAML holds the progress text after it.

## Care marks
- 8 rows x 2 columns, codes: T (Total Care), PA (Physical Assist), VP (Verbal Prompt), M (Monitor), D (Decline).
- Every box gets a mark, every day.

## Rendering (generator field map)
- Body font is **EB Garamond** (`assets/fonts/EBGaramond-Regular.ttf`), matching
  the Slides version. It is a *static instance* pinned from the variable font
  with `fonttools varLib.instancer` — PIL/FreeType mis-renders the raw variable
  font (some glyphs come out slanted), so never use the variable TTF directly.
- Narrative and goal text use `anchor="ls"` with baselines snapped 12px above
  the form's actual ruled lines (detected in the bg image, not copied from
  Slides). The 12px = 9px descender depth of EB Garamond at 28px + 3px
  clearance; at 5px the ruled line struck through descenders (fixed Oct 13,
  2026, after Scotty caught it on the week-of-10/05 render).
- Date digits sit in the cells *between* the form's baked "/" separators.
  Digits drawn on top of a "/" look slanted/broken (the slash shows through),
  so keep them clear. Slash x-positions measured on the bg scans (both forms):
  header dates 168-175 and 277-284; DSP sign date 1489-1492 and 1548-1551.
  The Total Hours blank is its own short line at y455, x1535-1616 — not the
  totals row at y486. (All re-measured Oct 13, 2026; the old map had day/year
  digits on the slashes and the day total 32px too low.)
- **Verify renders at zoom, not thumbnail.** A full-page glance passed the
  broken 10/05 render twice; Scotty caught the defects zoomed in on his
  phone. Crop the header dates, totals/sign-date, narrative, and goal at
  200 dpi and read each crop before calling a render final.
- **Deliver each revision under a NEW filename** (…-rev2, -rev3, …). Scotty's
  client caches attachments by name — re-sending the same filename showed
  him stale versions twice on Oct 13, 2026 even though the file on disk was
  current. A fresh name every delivery, plus a rendered page image, ends it.
- X marks use `anchor="mm"` centered in the checkbox interiors, measured from
  the bg image (AM ~860, PM ~980 for shift 1; +437px for shift 2).
- Shift-total values sit on the underline at y=487 (baseline 482).
