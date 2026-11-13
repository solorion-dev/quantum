---
name: ender3-printer
version: 1.0.0
description: "Operating Scotty's 3D printer: ORIGINAL Creality Ender 3 driven by OctoPrint 1.11.8 on scottypi3, controlled through the quantum_printer_* Quantum MCP tools, Home Assistant, and PrusaSlicer with the checked-in Ender 3 + Geeetech PLA profile. Use whenever the work mentions the Ender 3, OctoPrint, 3D printing, slicing."
tags: [quantum]
status: active
provenance: quantum
aliases: [local-ender3-printer]
dependencies:
  tools: [quantum_printer_connect, quantum_printer_cooldown, quantum_printer_delete_file, quantum_printer_files, quantum_printer_home, quantum_printer_job, quantum_printer_move, quantum_printer_set_temps, quantum_printer_slice, quantum_printer_start_print, quantum_printer_status, quantum_printer_upload]
  repos: [dsect-net/hub-api]
  urls: []
maintainers: [cooper]
---
# Ender 3 Printer — operations

Custom fleet skill, authored Nov 11, 2026 by Cooper, from the verified
OctoPrint bring-up (Nov 7) and the quantum_printer_* MCP build (TRK-0659).

## 1. Machine facts (verified Nov 7–11, 2026)

- **Printer: ORIGINAL Creality Ender 3** — not Pro/V2/Neo. Verified from
  Scotty's Walmart order (placed Dec 6, 2023, $169.13). Stock 0.4 mm
  nozzle, Bowden extruder, PTFE-lined hotend (never exceed 240 °C),
  bead-type thermistor, carborundum glass bed, 220×220×250 mm build volume.
- **Filament:** Geeetech PLA Black, 1.75 mm, sold as "Toughness Enhanced"
  (Walmart order #2000154-67533358, $17.40, arrived Nov 9, 2026).
- **OctoPrint 1.11.8 on scottypi3** (Pi 3B): LAN `192.168.6.252:5000`,
  Tailscale `100.87.67.93:5000`. **No dsect.net hostname exists.** Printer
  profile in OctoPrint: "Ender 3" (`_default`).
- Serial: `/dev/ttyUSB0` @ 115200, autoconnect ON, Connected/Operational
  when the printer is powered.
- OctoPrint user **cooper** (admins group). **Application Key for
  automation lives ONLY at `/home/scott/.cooper/octoprint-api-key` (600)
  on Tritium — POINTER ONLY. Never print it, log it, commit it, or copy
  it anywhere.** The hub tools read it from that file at call time.
- Pi SSH is closed to Cooper.

## 2. SAFETY — TRK-0657 thermistor fault (read before heating/moving)

- The hotend thermistor circuit is **intermittent**: Scotty's wiggle test
  spiked readings **200→250 °C**. The same fault can read **low while the
  block overheats**, which defeats thermal-runaway trust.
- **The printer must NOT run unattended until the thermistor is
  replaced.** Replacement spec (drop-in): **HT-NTC100K (3950, XH2.54
  2-pin, 3×15 mm capsule)** — Creality's own stock spec for this
  bead-type block. A screw-in M3 stud thermistor does NOT fit the stock
  bead-type block.
- The `quantum_printer_*` heat/move/start tools carry a
  **temperature-plausibility guard because of this fault**: two samples
  ~600 ms apart; refusal (`printer_unsafe_temp_reading`) on missing or
  out-of-range readings, a >10 °C jump between samples, or a reading
  stuck at ambient while a target is set. **Do not bypass the guard.**
  Cooldown is never guard-blocked (turning heat off is always safe).
- Locating the break: wiggle the thermistor wire run section by section
  while watching OctoPrint's temperature graph; the spike marks the bad
  stretch (classically at the glass bead in the block, or where the
  retention screw bites the insulation).

## 3. Quantum MCP tools (hub-api, TRK-0659)

All developer tier, served by hub-api at mcp.dsect.net once PR #128 is
merged and hub-api restarted. Implementation: `lib/mcp-printer-tools.js`
+ `lib/mcp-printer-schemas.js` in `dsect-net/hub-api`; they talk to
OctoPrint's REST API directly (not through Home Assistant).

| Tool | Does |
|---|---|
| `quantum_printer_status` | Connection state, hotend/bed actual+target, job, progress % |
| `quantum_printer_connect` | Serial connect/disconnect (saved /dev/ttyUSB0 @ 115200) |
| `quantum_printer_set_temps` | Hotend (0–240 °C) and/or bed (0–100 °C) targets — GUARDED |
| `quantum_printer_cooldown` | Both targets to 0 — never guard-blocked |
| `quantum_printer_move` | Jog (≤60 mm/axis/call) or absolute move (clamped to build volume), idle only — GUARDED |
| `quantum_printer_home` | Home x/y/z (or a subset), idle only — GUARDED |
| `quantum_printer_files` | List OctoPrint local + SD files, flattened |
| `quantum_printer_upload` | .gcode/.gco → OctoPrint; .stl/.3mf/.obj → hub slicing spool. Never auto-prints |
| `quantum_printer_delete_file` | Delete a file from OctoPrint local or SD |
| `quantum_printer_start_print` | Start a file already on OctoPrint — GUARDED, attended only |
| `quantum_printer_job` | pause / resume / cancel / restart (restart is guarded) |
| `quantum_printer_slice` | Slice a spooled model with the Ender 3 PLA profile, upload the .gcode, report time/filament. `print: true` also starts (guarded); default is slice-only |

Typical flow: upload model → `quantum_printer_slice` → check the
estimate → `quantum_printer_start_print` (or slice with `print: true`) →
watch via `quantum_printer_status`. Config envs on the hub (all optional;
defaults are the live values): `OCTOPRINT_BASE`, `OCTOPRINT_API_KEY`,
`OCTOPRINT_API_KEY_FILE`, `PRINTER_SLICER_BIN`, `PRINTER_PROFILE`,
`PRINTER_WORK_DIR` (default `~/printer-spool`).

## 4. Slicing — Ender 3 + Geeetech PLA profile

- **Profile:** `config/printer/ender3-geeetech-pla.ini` in the hub-api
  repo (flat PrusaSlicer config; notes in `config/printer/README.md`
  beside it). Authored new Nov 11, 2026 — no slicer or profile existed
  on Tritium before this — and verified by slicing a 20 mm cube with
  PrusaSlicer 2.9.4 (start temps and estimates correct in the output).
- **Values:** first-layer nozzle 205 °C, then 200 °C; bed 60 °C;
  layer height 0.2 mm; perimeters 3; infill 20% grid; retraction
  **5 mm @ 45 mm/s** (stock Bowden); speeds perimeter 40 / infill 50 /
  travel 120 / first layer 20 mm/s; fan 100% after layer 3; standard
  Ender start/end G-code with prime lines.
- **Slicer:** PrusaSlicer CLI. Not installed on Tritium by default —
  deploy via `scripts/install-printer-slicer.sh` in hub-api (apt,
  prusa-slicer 2.9.4). Slicing runs on Tritium (the hub host).
- Manual re-slice: `prusa-slicer --export-gcode --load
  config/printer/ender3-geeetech-pla.ini --output out.gcode model.stl`.

## 5. Home Assistant surface

- OctoPrint integration is live (21 entities, incl. pause/resume/stop
  buttons) — good for glanceable control; the MCP tools are the
  automation-grade surface.
- Printer page: **https://home.dsect.net/devices-panel/printer** — a tab
  in the consolidated Devices dashboard (YAML-mode,
  `dashboards/devices.yaml`, slug `devices-panel`; Atlas and Resources
  are sibling tabs). An "Open OctoPrint" button at the top links to
  `http://192.168.6.252:5000/`. Temperatures shown in Celsius.
- Cooper's HA user is ADMIN. TRK-0607 / TRK-0594 / TRK-0655 cover this
  surface and sit in_review pending Scotty's visual check.

## 6. Troubleshooting (established)

- **Thermal runaway / heating-failed errors:** assume the TRK-0657
  thermistor fault first (see §2). Do not "fix" by raising temps.
- **Filament snapping at the extruder entrance:** bend test a free
  length — snaps like dry spaghetti = brittle/wet spool; dry PLA at
  45–50 °C for 4–6 h. Also check: groove worn into the stock plastic
  extruder inlet, spool cross-wraps, cracked idler arm.
- **Ghosting / residue on the carborundum glass bed:** heat bed to
  60–65 °C, lift residue with a PLASTIC scraper only, wash the plate in
  the sink with dish soap (magic eraser ok), dry fully, re-check level.
  No acetone, no steel wool on the coating.
- **OctoPrint says "Printer is not operational":** printer is off or the
  serial link is closed — `quantum_printer_connect` with
  `action: "connect"`, then re-check status. /dev/ttyUSB0 is the only
  real port (ttyS0 is a decoy).

## 7. Working rules

- **Heavy-Start Gate:** before starting/restarting any Tritium service
  expected to take >2 GiB RAM for print/slice work, run `free -h` +
  `uptime`; stop if swap ≥90% OR MemAvailable <4 GiB OR load1 >20.
  (Slicing itself is brief CPU work; the gate is about services.)
- Bridge discipline for Tritium work: sequential dev_shell calls,
  base64 payloads, commands under ~50 s.
- Tracker: printer work hangs off TRK-0657 (thermistor) and TRK-0659
  (MCP tools); file new printer issues in the Tracker first.
