---
name: video-editor
version: 1.0.0
description: "Editing and post-production for self-generated video: stitching clips together, laying music underneath, and finishing renders to delivery spec. Every recipe below was run for real on this VM (see Worked Examples) — if a recipe and reality disagree, reality wins and this file gets corrected."
tags: [quantum]
status: active
provenance: quantum
aliases: [local-video-editor]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Local Video Editor

Editing and post-production for self-generated video: stitching clips together, laying music underneath, and finishing renders to delivery spec. Every recipe below was run for real on this VM (see Worked Examples) — if a recipe and reality disagree, reality wins and this file gets corrected.

## Purpose

- Concat / stitch multiple clips into one sequence, with plain cuts or `xfade` transitions.
- Music underlay: mix a track under the picture with level offset and fade in/out.
- Loudness: loudnorm to a target (house target −16 LUFS integrated, −1.5 dBTP); **finals use two-pass loudnorm** (see Honesty Notes).
- Conform picture to delivery size — scale / crop / letterbox to 1280×720 or 1920×1080.
- Frame extraction and tile contact sheets so every render gets eyeballed.
- Delivery encode: H.264 + AAC in MP4 with faststart.

Working directory for renders and scratch: `~/workspace/video-pipeline/`.

## Toolchain (verified 2026-10-20)

- `ffmpeg version 8.1.2` / `ffprobe version 8.1.2` (Ubuntu 24.04 build; libx264, libx265, libmp3lame, libopus, libvpx present).
- Re-verify before trusting this line on a new VM: `ffmpeg -version | head -1`.

## Generation sources (where footage comes from)

1. **Nebula LTX (local, Tritium)** — via the hub `quantum_nebula_*` tools. State as of 2026-10-20: agent API healthy, four LTX video workflows listed (`ltx-2.3_a2v_lora_wf_v1`, `ltx-2.3_t2v_lora_basic_wf_v1`, `ltx-2.3_t2v_lora_wf_v1`, `ltx-2.3_video_wf_v1`), but **generation is UNVERIFIED** — LTX needs its prep step (`/home/scott/nebula-ltx25/ltx-prep.sh`) plus GPU juggling with llama-qwen/comfyui. Governed by the `local-quantum-nebula` skill: never call LTX working until a generation actually completes.
2. **Hosted in-chat video generation** — Cooper's media video tools. Listed here as a source; not exercised in the reference renders.
3. **Godot captures** — Xvfb harness renders from the game itself (precedent: the prometheia-ui-overhaul capture pipeline, `--rendering-driver opengl3`). **Godot captures carry a ~1 s engine splash head — trim from ≥1.5 s** or the splash ships in your edit.

## Music sources

- **Existing project tracks first.** Prometheia's title theme "First Fire" lives at `~/workspace/video-pipeline/first_fire_title.mp3` (48 kHz stereo, 228.8 s; extracted read-only via `git show cooper/main-menu-redesign:godot/audio/music/first_fire_title.mp3` from `~/workspace/prometheia-merge`; sits at about −14.7 LUFS as shipped).
- **Samples before batches (creative rule, standing):** for anything creative — music, voice, generated footage — make short samples and get Scotty's ears/eyes on them BEFORE a full render. Never burn a batch on an unvalidated aesthetic.

## Recipes

### 0. Normalize first (mandatory before xfade)

`xfade` fails unless both inputs match fps, resolution, SAR, and pix_fmt. Conform every clip up front:

```bash
ffmpeg -i in.mp4 -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1,format=yuv420p" -c:a aac norm.mp4
```

Drop the `pad` and use `crop` instead if the piece should fill the frame rather than letterbox.

### 1. Trim a clip

```bash
ffmpeg -ss 17 -i src.mp4 -t 5 -c:v libx264 -crf 20 -pix_fmt yuv420p -c:a aac clip.mp4
```

(Seek before `-i` for speed; re-encode rather than stream-copy when the cut must be frame-accurate or feed an xfade.)

### 2. Xfade stitch (two clips, 1 s crossfade)

Offsets are in seconds from the start of the first clip; with clip A = 5 s and a 1 s fade, `offset=4`.

```bash
ffmpeg -i a.mp4 -i b.mp4 -filter_complex \
"[0:v][1:v]xfade=transition=fade:duration=1:offset=4[v]; \
 [0:a][1:a]acrossfade=d=1[a]" \
-map "[v]" -map "[a]" -c:v libx264 -crf 20 -pix_fmt yuv420p -c:a aac stitched.mp4
```

Plain concat (same codec/geometry) can use the concat demuxer with `-c copy`; xfade always needs the re-encode path above.

### 3. Music underlay with fades

Mix the track under the program audio (or alone, when the clips are silent) at a set offset, with fades so it never starts/stops abruptly:

```bash
ffmpeg -i stitched.mp4 -i music.mp3 -filter_complex \
"[1:a]volume=-8dB,afade=t=in:st=0:d=2,afade=t=out:st=6:d=3[mus]; \
 [0:a][mus]amix=inputs=2:duration=first:dropout_transition=0[a]" \
-map 0:v -map "[a]" -c:v copy -c:a aac -b:a 160k with_music.mp4
```

Set the `afade=t=out` start to (total duration − fade length). If the program audio is genuinely silent/absent, map the music directly instead of amixing against silence.

**Ducking** (sidechaincompress so music dips under dialogue) is the documented next step but is **unexercised** — both reference renders used silent source clips, so no ducking recipe here is proven yet. Prove it on a sample before using it in a final.

### 4. Loudnorm — two-pass for finals

Pass 1, measure (keep the JSON ffmpeg prints at the end):

```bash
ffmpeg -i with_music.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null -
```

Pass 2, apply with the measured values (`measured_I`, `measured_TP`, `measured_LRA`, `measured_thresh`, `offset` from pass 1):

```bash
ffmpeg -i with_music.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-20.5:measured_TP=-4.2:measured_LRA=8.0:measured_thresh=-31.5:offset=0.3:linear=true \
-c:v copy -c:a aac -b:a 160k final.mp4
```

Single-pass loudnorm is fine for smoke tests only — it drifts (see Honesty Notes).

### 5. Delivery encode

```bash
ffmpeg -i final.mp4 -c:v libx264 -crf 20 -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 160k deliver.mp4
```

### 6. Contact sheet (frame extraction for eyeballing)

```bash
ffmpeg -i deliver.mp4 -vf "fps=1/2,scale=640:360,tile=3x2" -frames:v 1 contact.png
```

Tune `fps=` to the clip length so the sheet covers the whole piece, including any crossfade midpoint — blends are where stitching defects hide.

### 7. Verify with ffprobe

```bash
ffprobe -v error -show_entries format=duration,size,bit_rate \
-show_entries stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels \
-of default=noprint_wrappers=1 deliver.mp4
```

And re-measure loudness on the delivered file (same loudnorm command as pass 1, read `input_i` / `input_tp`).

## Verification rule

**Eyeball every render.** Extract the contact sheet, look at it, and only then report the render. Check: geometry (no stretching, letterbox where expected), the crossfade midpoint frame, text legibility, and that no splash head or black slug survived. A render nobody looked at is not verified — same standard as screenshots for app work.

## Worked examples (reference outputs, `~/workspace/video-pipeline/`)

- **`smoke_test.mp4`** — 9.000 s, 1280×720, H.264 30 fps + AAC, 708,803 B. Build: `menu_fire_preview.mp4` trim (1 s→6 s) + 1 s xfade + `intro_cinematic_preview.mp4` trim (17 s→22 s, the cosmic-eye approach), First Fire underlay at −8 dB with in/out fades, **single-pass** loudnorm. Measured −14.79 LUFS / −2.21 dBTP against a −16 target — the drift documented below.
- **`intro_cinematic_full.mp4`** — 86.300 s, 1280×720, H.264 30 fps + AAC 48 kHz stereo, 5,355,568 B. Build: the full intro cinematic stitched with text/audio per its beats, **two-pass loudnorm to −16 LUFS**. Contact sheet: `intro_cinematic_full_contact.png`.
- **`first_fire_title.mp3`** — the music source above (228.8 s).

Prometheia application this was built for: recreating/extending the intro cinematic — beats: pixel dust → quote card → cosmic eye → Overseer stanzas → convergence → white flash → hard cut to the menu.

## Honesty notes (learned on the renders above)

1. **Single-pass loudnorm drifts hot.** On the 9 s smoke test it landed ~1.2 LU above target (−14.79 vs −16). Finals: always two-pass with `linear=true`.
2. **xfade is strict.** Mismatched fps/res/SAR/pix_fmt = hard failure. Normalize first (Recipe 0), every time.
3. **Godot splash head.** Captures start with ~1 s of engine splash; trim from ≥1.5 s in real edits.
4. **Ducking is unproven here.** Documented, not exercised — the reference clips were silent. Sample-test before relying on it.
5. **Nebula LTX generation is unverified.** API healthy, workflows listed; no completed generation yet. Do not promise LTX footage until one finishes (see `local-quantum-nebula`).

## Available connectors

Use `muse.connector_search` to find the current connector docs before following recovered instructions. Nebula generation goes through the hub tools; see the `local-quantum-nebula` skill.
