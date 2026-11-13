# Adding a new form background (e.g. Community code 36)

The generator only ships the Home Support 33 background because that is the
only one measured pixel-for-pixel. To add another form:

1. **Extract a clean background.** Copy the production deck in Drive, open the
   copy, delete every text/shape element from one good slide of the wanted form
   (keep only the background image element), export the copy as PDF, and render
   page 1 at 200dpi: `pdftoppm -png -r 200 -f 1 -l 1 copy.pdf bg`. The result
   must be 1700x2200 px. Save as `assets/<code>.png` and trash the copy.
2. **Measure field positions.** From a production slide of that form, read each
   text element's `transform.translateX/translateY` via the Slides API and
   convert to pixels: `px = EMU * 1700/7772400`, `py = EMU * 10058400/2200`.
   Check AM/PM checkbox centers against the background image itself (crop and
   look) — the slide coordinates can be ~30px off from the rendered boxes.
3. **Add a FORMS entry** in `bin/wroc.py` mirroring the "33" block: background
   file, all field anchors, the 16 mark coordinates, font sizes. Keep the
   narrative/goal boxes inside the form's ruled lines and verify with a render.
4. **Test** by regenerating a known-good week and comparing page-by-page.

Lesson from Sept 2026: `replaceImage` on the Slides API silently fails to change
the rendered background (metadata updates, PDF keeps the old image). The
working swap is `deleteObject` + `createImage` (full-page 7772400x10058400 EMU)
+ `updatePageElementsZOrder` with operation `SEND_TO_BACK`. `lh7-rt`
slidesz contentUrls download as black placeholders; use
`lh3.googleusercontent.com/d/<fileId>=w3000` for Drive-hosted images
(needs anyoneWithLink reader).
