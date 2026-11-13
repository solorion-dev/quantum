#!/usr/bin/env python3
"""WROC generator: render a weekly WROC PDF from a structured YAML file.

Usage:
    wroc.py week.yaml -o output.pdf [--dpi 200]

The YAML describes each day's shifts, care marks, and narratives (see
assets/week-template.yaml). The script validates the data (hours math,
narrative length, mark codes, service code) and overlays text onto the
official form backgrounds to produce a supervisor-ready PDF.

No Google Slides, no manual layout. Fix the data, re-run, done.
"""
import argparse
import datetime
import re
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent
ASSETS = BASE / "assets"
FONT = str(ASSETS / "fonts" / "EBGaramond-Regular.ttf")

VALID_MARKS = {"T", "PA", "VP", "M", "D"}

# ---------------------------------------------------------------------------
# Form geometry: pixel positions on the 1700x2200 background scans.
# Measured from the production deck (Sept 2026). (x, y) = top-left anchor.
# ---------------------------------------------------------------------------
HS33 = "hs33.png"
C36 = "c36.png"
FORMS = {
    "33": {
        "bg": HS33,
        "fields": {
            # (x, baseline_y); drawn with anchor="ls" unless noted
            # date digits are CENTERED in the cells between the baked "/" separators
            # (Scotty asked for a rightward nudge Oct 13, 2026; a literal
            # half-inch would cross the slashes, centering is the clean max)
            # (slashes measured on the bg scan at x 168-175 and 277-284;
            # segments: month 95-163, day 180-272, year 289-355)
            "date_m": (115, 328), "date_d": (218, 328), "date_y": (308, 328),
            "we_m": (115, 408), "we_d": (218, 408), "we_y": (308, 408),
            "s1_start": (642, 336), "s1_end": (642, 416),  # baselines flush: lines at y340-345 and y420-422 (were 318/398, floated ~22px)
            "s2_start": (1079, 336), "s2_end": (1079, 416),
            # X marks: checkbox centers measured on the bg scan (boxes are
            # 22x22: x 843-865/969-991 and 1280-1303/1407-1429, y 313-335
            # and 393-416). The old centers sat ~10px too high, so the X
            # straddled the box's top edge (Scotty, Oct 13, 2026).
            "s1_start_am": (854, 324), "s1_start_pm": (980, 324),
            "s1_end_am": (854, 405), "s1_end_pm": (980, 405),
            "s2_start_am": (1291, 324), "s2_start_pm": (1418, 324),
            "s2_end_am": (1291, 405), "s2_end_pm": (1418, 405),
            "s1_total": (841, 482), "s2_total": (1269, 482),
            # Total Hours blank is its own short line at y455, x1535-1616
            # (measured on the bg scan Oct 13, 2026), NOT the totals row
            "day_total": (1540, 450),
            "printed_name": (294, 551),  # baseline matches the sign-date row; line is at y563 (was 532: floated 31px above the line)
            # sign-date slashes measured at x 1489-1492 and 1548-1551
            "sign_m": (1430, 551), "sign_d": (1502, 551), "sign_y": (1563, 551),
            "goal": (104, 1648), "goal_width": 1490,
            "goal_lines": [1692, 1737],
        },
        # narrative sections: (yaml_key, x, width, ruled-line y's);
        # text baselines sit 5px above each ruled line
        "narrative_sections": [
            ("narrative", 101, 1495, [1133, 1174, 1216, 1257, 1299, 1340, 1381]),
        ],
        # 8 rows x 2 columns, top to bottom
        "marks_left_x": 104,
        "marks_right_x": 884,
        "marks_y": [699, 739, 776, 816, 856, 896, 936, 976],
        "marks_per_side": 8,
        "font_size": 28,
        "small_font_size": 27,
        "goal_font_size": 28,
    },
    "36": {
        "bg": C36,
        "fields": {
            # Community 64/36/37 form; geometry measured Oct 2026 from the
            # 09/07/26 production deck (bg extracted at 200dpi, 1700x2200).
            # Checkbox centers measured on the bg image itself.
            "date_m": (115, 328), "date_d": (218, 328), "date_y": (308, 328),
            "we_m": (115, 408), "we_d": (218, 408), "we_y": (308, 408),
            "s1_start": (642, 336), "s1_end": (642, 416),  # baselines flush: lines at y340-345 and y420-422 (were 318/398, floated ~22px)
            "s2_start": (1079, 336), "s2_end": (1079, 416),
            # X marks: checkbox centers measured on the bg scan (same
            # geometry as the 33 form; see the note there)
            "s1_start_am": (854, 324), "s1_start_pm": (980, 324),
            "s1_end_am": (854, 405), "s1_end_pm": (980, 405),
            "s2_start_am": (1291, 324), "s2_start_pm": (1418, 324),
            "s2_end_am": (1291, 405), "s2_end_pm": (1418, 405),
            "s1_total": (841, 482), "s2_total": (1269, 482),
            "day_total": (1540, 450),
            "printed_name": (294, 551),  # baseline matches the sign-date row; line is at y563 (was 532: floated 31px above the line)
            "sign_m": (1430, 551), "sign_d": (1502, 551), "sign_y": (1563, 551),
            "goal": (101, 1648), "goal_width": 1490,
            # progress text goes on the lines below the baked goal sentence
            "goal_lines": [1794, 1838],
        },
        # ruled lines detected in the bg image; text baselines sit 5px above
        "narrative_sections": [
            ("narrative_services", 101, 1495, [1091, 1132, 1174, 1216, 1257, 1298]),
            ("narrative_job", 101, 1495, [1384, 1428, 1472]),
            ("narrative_choices", 101, 1495, [1560, 1604, 1648]),
        ],
        # 7 rows x 2 columns, top to bottom
        "marks_left_x": 104,
        "marks_right_x": 884,
        "marks_y": [699, 739, 776, 817, 856, 896, 936],
        "marks_per_side": 7,
        "font_size": 28,
        "small_font_size": 27,
        "goal_font_size": 28,
    },
}

# Soft length bands for validation warnings: (min, max) chars per narrative key.
# The 33 narrative fills 7 ruled lines; the 36 sections are smaller.
NARRATIVE_BANDS = {
    "narrative": (500, 660),
    "narrative_services": (300, 620),
    "narrative_job": (60, 340),
    "narrative_choices": (60, 340),
}

# ---------------------------------------------------------------------------
# Parsing / validation
# ---------------------------------------------------------------------------
TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AaPp])[Mm]?\s*$")


def parse_time(s):
    m = TIME_RE.match(s or "")
    if not m:
        raise ValueError(f"bad time {s!r}, expected like '10:00 AM'")
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if ap == "P" and h != 12:
        h += 12
    if ap == "A" and h == 12:
        h = 0
    ampm = "AM" if m.group(3).upper() == "A" else "PM"
    return h * 60 + mi, f"{m.group(1)}:{m.group(2)}", ampm


def fmt_hours(minutes):
    h = minutes / 60
    s = f"{h:.2f}"
    return s


def split_date(s):
    parts = s.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"bad date {s!r}, expected M/D/YY")
    return parts[0], parts[1], parts[2]


def validate_week(data):
    errors, warnings = [], []
    week_code = str(data.get("program_code", ""))
    if week_code not in FORMS:
        errors.append(f"program_code {week_code!r} has no form background (have: {sorted(FORMS)})")
        return errors, warnings
    days = data.get("days", [])
    if not days:
        errors.append("no days in week file")
    total_min = 0
    for i, day in enumerate(days, 1):
        tag = f"day {i} ({day.get('date', '?')})"
        code = str(day.get("program_code", week_code))
        form = FORMS.get(code)
        if form is None:
            errors.append(f"{tag}: program_code {code!r} has no form background (have: {sorted(FORMS)})")
            continue
        tag = f"{tag} [code {code}]"
        try:
            split_date(day["date"])
        except (KeyError, ValueError) as e:
            errors.append(f"{tag}: {e}")
        for sk in ("shift1", "shift2"):
            sh = day.get(sk)
            if not sh:
                continue
            try:
                s_min, _, _ = parse_time(sh["start"])
                e_min, _, _ = parse_time(sh["end"])
            except (KeyError, ValueError) as e:
                errors.append(f"{tag} {sk}: {e}")
                continue
            if e_min <= s_min:
                errors.append(f"{tag} {sk}: end must be after start")
            else:
                total_min += e_min - s_min
        nmarks = form["marks_per_side"]
        for side in ("marks_left", "marks_right"):
            marks = day.get(side, [])
            if len(marks) != nmarks:
                errors.append(f"{tag} {side}: need {nmarks} marks, got {len(marks)}")
            for mk in marks:
                if mk not in VALID_MARKS:
                    errors.append(f"{tag} {side}: invalid mark {mk!r}")
        for key, _x, _w, _lines in form["narrative_sections"]:
            nar = day.get(key, "")
            lo, hi = NARRATIVE_BANDS[key]
            if not nar.strip():
                errors.append(f"{tag}: {key} is empty")
            elif not (lo <= len(nar) <= hi):
                warnings.append(f"{tag}: {key} is {len(nar)} chars (target {lo}-{hi})")
            if "—" in nar or "–" in nar:
                warnings.append(f"{tag}: {key} contains em/en dash")
        if not day.get("goal", "").strip():
            errors.append(f"{tag}: goal text is empty")
        elif len(day["goal"]) > 200:
            warnings.append(f"{tag}: goal is {len(day['goal'])} chars; over ~200 may collide with the next Goal label")
    data["_total_hours"] = total_min / 60
    return errors, warnings


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_day(form, day, week_ending, printed_name):
    f = form["fields"]
    img = Image.open(ASSETS / form["bg"]).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, form["font_size"])
    small = ImageFont.truetype(FONT, form["small_font_size"])

    def put(key, text, use_small=False):
        draw.text(f[key], text, font=small if use_small else font,
                  fill="black", anchor="ls")

    def put_x(key):
        # Drawn as two strokes, not a font glyph: the EB Garamond X at
        # checkbox size sat high in its em box and overflowed the 22px
        # checkbox. Strokes are centered by construction (half=7 inside
        # the 22px box, ~4px inset).
        cx, cy = f[key]
        h = 7
        draw.line([(cx - h, cy - h), (cx + h, cy + h)], fill="black", width=3)
        draw.line([(cx - h, cy + h), (cx + h, cy - h)], fill="black", width=3)

    m, d, y = split_date(day["date"])
    put("date_m", m); put("date_d", d); put("date_y", y)
    wm, wd, wy = split_date(week_ending)
    put("we_m", wm); put("we_d", wd); put("we_y", wy)

    day_min = 0
    for n, sk in (("1", "shift1"), ("2", "shift2")):
        sh = day.get(f"shift{n}")
        if not sh:
            continue
        s_min, s_txt, s_ap = parse_time(sh["start"])
        e_min, e_txt, e_ap = parse_time(sh["end"])
        day_min += e_min - s_min
        put(f"s{n}_start", s_txt)
        put_x(f"s{n}_start_am" if s_ap == "AM" else f"s{n}_start_pm")
        put(f"s{n}_end", e_txt)
        put_x(f"s{n}_end_am" if e_ap == "AM" else f"s{n}_end_pm")
        put(f"s{n}_total", fmt_hours(e_min - s_min))
    put("day_total", fmt_hours(day_min))
    put("printed_name", printed_name)
    sm, sd, sy = split_date(day["date"])
    put("sign_m", sm); put("sign_d", sd); put("sign_y", sy)

    for row, mk in enumerate(day["marks_left"]):
        draw.text((form["marks_left_x"], form["marks_y"][row]), mk, font=small, fill="black")
    for row, mk in enumerate(day["marks_right"]):
        draw.text((form["marks_right_x"], form["marks_y"][row]), mk, font=small, fill="black")

    for key, nx, nwidth, nlines_y in form["narrative_sections"]:
        text = day.get(key, "")
        nlines = wrap(draw, text, font, nwidth)
        if len(nlines) > len(nlines_y):
            print(f"WARNING: {key} needs {len(nlines)} lines but the form has "
                  f"{len(nlines_y)} ruled lines; text will run past them",
                  file=sys.stderr)
        for i, line in enumerate(nlines):
            # baseline sits 12px above the ruled line: EB Garamond at 28px
            # has a 9px descender depth, so -5 left the rule striking
            # through descenders (fixed Oct 13, 2026)
            baseline = nlines_y[min(i, len(nlines_y) - 1)] - 12
            # extra lines continue at the same leading past the last ruled line
            if i >= len(nlines_y):
                baseline = nlines_y[-1] - 12 + (i - len(nlines_y) + 1) * 41
            draw.text((nx, baseline), line, font=font, fill="black", anchor="ls")
    gx, _ = f["goal"]
    gfont = ImageFont.truetype(FONT, form["goal_font_size"])
    glines = wrap(draw, day["goal"], gfont, f["goal_width"])
    for i, line in enumerate(glines[:len(f["goal_lines"])]):
        draw.text((gx, f["goal_lines"][i] - 12), line, font=gfont, fill="black", anchor="ls")
    if len(glines) > len(f["goal_lines"]):
        print(f"WARNING: goal needs {len(glines)} lines but only "
              f"{len(f['goal_lines'])} fit; truncating", file=sys.stderr)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weekfile")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--force", action="store_true", help="render even with validation errors")
    args = ap.parse_args()

    data = yaml.safe_load(open(args.weekfile))
    errors, warnings = validate_week(data)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        if not args.force:
            print("Refusing to render. Fix the errors or pass --force.", file=sys.stderr)
            sys.exit(1)

    week_code = str(data["program_code"])
    pages = []
    for i, day in enumerate(data["days"], 1):
        code = str(day.get("program_code", week_code))
        form = FORMS.get(code)
        if form is None:
            print(f"ERROR: day {i}: program_code {code!r} has no form background (have: {sorted(FORMS)})", file=sys.stderr)
            print("Refusing to render. Fix the program_code.", file=sys.stderr)
            sys.exit(1)
        pages.append(render_day(form, day, data["week_ending"], data.get("printed_name", "Scott Venable")))
    pages[0].save(args.output, save_all=True, append_images=pages[1:], resolution=args.dpi)
    total = data.get("_total_hours", 0)
    print(f"Wrote {args.output}: {len(pages)} pages, {total:.2f} total hours")


if __name__ == "__main__":
    main()
