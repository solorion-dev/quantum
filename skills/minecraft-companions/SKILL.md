---
name: minecraft-companions
version: 1.0.0
description: "Operating the AI Companion mod (Fabric 1.20.1) in Scotty's live Minecraft instance: companion brains on Tritium Ollama, aicompanion.json config, skins, personas, and log-based diagnostics. Use whenever the work mentions the AI Companion mod, Minecraft companions, Vetta, Rook, companion brains/skins/personas/voices, or."
tags: [minecraft, imported]
status: active
provenance: quantum
aliases: [local-minecraft-companions]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Minecraft Companions — AI Companion operations

Custom fleet skill, authored Nov 1, 2026 by Cooper for Scotty, from the
verified Vetta/Rook bring-up the same night.

## 0. Scope split — read this first

- **This skill = OPERATING companions** in a live, running instance: config,
  brains, skins, personas, voices, diagnostics.
- **`local-minecraft-modding` = DEVELOPING mods** (Off To Market, Forge
  1.19.2 code). Different job, different skill. The companion mod here is
  Fabric 1.20.1 and is operated, not developed, by the fleet.

## 1. Instance facts (verified Nov 1, 2026)

- Host: Scotty's Victus laptop, FTB App instance **`ai companion test 1201(2)`**
  (Fabric 1.20.1 + AI Companion mod + deps).
- **FTB App instance root is `C:\Users\scott\AppData\Local\.ftba\instances\`** —
  NOT `~/.ftba`. Paths below are relative to the instance folder.
- Config: `config\aicompanion.json`
- Skins: `config\aicompanion\skins\`
- Logs: `logs\latest.log` (the diagnostic ground truth — see §7)
- Brains: Ollama on Tritium, shared by all companions (see §3).

## 2. Config anatomy

One file, `aicompanion.json`, three kinds of content:

- **One global `llm` block** — `endpoint`, `model`, `temperature`,
  `maxTokens` — **shared by ALL companions**. There is no per-companion
  brain. A second (or third) companion costs **no extra VRAM**, just more
  turns through the same loaded model.
- **`companions` array** — one object per companion: `name`, `description`,
  `systemPrompt`, `skin.file`, `skin.slim`, `voice`.
- **Behaviour toggles + a `tts` block** — engine-side behaviours
  (follow/navigate/gather/fight) work with no brain at all; chat replies are
  what the LLM drives. TTS is specced but not built (see §8).

## 3. Brain wiring (Tritium Ollama)

- Ollama listens on Tritium `:11434` and serves both the native API and the
  OpenAI-compatible routes; the mod talks to it from the game machine.
- **LAN gotcha:** `http://192.168.4.196:11434` is **blocked from the LAN by
  Tritium's UFW** (no allow rule for 11434; the packets drop even though
  Ollama itself is bound correctly). The config therefore uses Tritium's
  **tailnet address `http://100.66.182.7:11434`** — the firewall already
  allows full access over `tailscale0`. If someone later adds a UFW allow
  for 11434/tcp from the LAN, the LAN address works too; until then, don't
  "fix" the endpoint back to the LAN IP.
- **Verify reachability FROM THE VICTUS** (PowerShell `Invoke-RestMethod`
  to `/api/tags`, plus one real chat round-trip). Tritium-local success
  proves nothing — the game machine is the caller.
- **Memory proxy (Nov 2, 2026, TRK-0586):** the config endpoint is now
  `http://100.66.182.7:11435` — the **rook-memory proxy**, NOT Ollama
  directly. It relays the mod's `/v1/chat/completions` calls to Ollama
  (:11434), injecting retrieved long-term memories ("THINGS YOU
  REMEMBER:") from a SQLite store (`/home/scott/.cooper/rook-memory/
  memories.db` on Tritium; embedder = nomic-embed-text; systemd user
  service `rook-memory-proxy`, tailnet-bind only). Code + README
  mirrored at `~/workspace/rook-memory/`. Rollback = point the endpoint
  back to `:11434` and relaunch. Diagnose memory issues from the
  proxy's audit log (`proxy.log` in the same dir) before touching the
  mod config.
- **VRAM reality:** the RTX 2060 Super has 8 GB, shared with the Jan/Breeze
  llama.cpp service (~3 GB resident — never evict or restart it for a
  companion). The current 7B Q4 pick (~5.1 GB at 4096 context) doesn't fully
  fit beside Jan, so Ollama splits it GPU/CPU — and still answers ~33 tok/s,
  plenty for chat.
- **Cold-load caveat:** Ollama's keep-alive is ~5 minutes, so the first
  companion call after an idle stretch pays a ~16 s model reload. Tell
  Scotty that before anyone calls a quiet companion "broken."

## 4. Config editing discipline

- The game may be running while you edit. Edits apply on the mod's **next
  config load** — a world rejoin or instance relaunch — not mid-step. Say
  so when you hand back.
- **Always back up first**, dated suffix (`aicompanion.json.bakN-YYYYMMDD`)
  in the same folder.
- **Edit via the JSON object model** (PowerShell `ConvertFrom-Json` → set
  properties on the object → `ConvertTo-Json -Depth 20` → BOM-less UTF-8
  write). Never string-splice JSON, and never embed long text in
  single-quoted PowerShell literals — see the AGENTS.md convention (Nov 1,
  2026) for the apostrophe parse trap that silently killed two edits.
- **Re-read the file after writing and verify the final on-disk state.**
  An edit is not done until the re-read shows it — and check the fields you
  did NOT touch (model, endpoint, other companions) survived too.
- **Never leave `skin.file` pointing at a nonexistent file.** If a skin
  isn't installed yet, leave it `""`.

## 5. Skins pipeline

Getting a skin file onto the Victus, in order:

1. **Source:** reputable skin libraries (SkinsMC, Skindex/minecraftskins.com,
   NameMC). **Scripted downloads are walled:** Skindex returns 403
   (Cloudflare bot wall) even with browser headers, and SkinsMC exposes no
   working direct-file URL. **Fetch through the real browser's Download
   button** on the skin's page instead.
2. **Validate BEFORE wiring — a file is not a skin until it passes:**
   - it is a PNG with a **64×64** modern skin layout (64×32 legacy is not
     what this mod expects);
   - **eyeball the texture**: the pixel regions must be a real skin template
     (head/hat blocks top-left, body, arms, legs in their layout slots) —
     not a render, avatar, or random 64×64 image;
   - **arm model:** set `skin.slim = true` only for slim (3px) skins;
     classic skins are 4px and take `slim = false`. The listing page
     usually states which it is.
3. **Transfer:** base64 the PNG inside a PowerShell script
   (`[Convert]::FromBase64String` → `[IO.File]::WriteAllBytes`) into
   `config\aicompanion\skins\<name>.png`, then **verify byte count and
   dimensions on the Victus side** against the source.
4. **Wire:** set that companion's `skin.file` to the exact filename
   (per §4 discipline), `skin.slim` per step 2.

Current roster skins, for style reference: Vetta — SkinsMC #210994
(forest ranger girl, green hood, classic arms); Rook — SkinsMC #177860
(blonde explorer with goggles and hip pouch, classic arms).

## 6. Persona writing for small brains

The brain is a 7B-class instruct model: **it plays character LIGHTLY.**
Prompt accordingly.

- Keep each `systemPrompt` **short — 4–6 sentences.** Long, lyrical prompts
  get ignored; concrete beats lyrical every time.
- Recipe per prompt: (1) role nouns ("You are a ranger of the wilds: scout,
  tracker, and pathfinder"); (2) speech discipline ("keep your replies
  short and spoken, like trail talk"); (3) **2–3 concrete habits/traits**
  (notices terrain/weather/tracks; warns of danger early and plainly);
  (4) **one relationship note** — how they treat the owner and the other
  companions (Vetta watches the owner's back; Rook teases Vetta and
  actually listens when she warns him).
- The `description` is a one-or-two-sentence identity blurb in the same
  spirit.
- Personas **are** loaded verbatim into every request — you can confirm a
  persona took effect by finding its exact text in the `latest.log`
  prompt dumps (§7), not by vibes.

## 7. Diagnostics — the log is the ground truth

`logs\latest.log` contains the mod's full prompt dumps: the incoming
message ("User Message" / "Other AI Message"), the companion's persona,
and a `worldStatus` (difficulty, weather, time of day, nearby hostiles,
nearby blocks with counts) plus `agentStatus` (health, food, inventory,
position, active `taskStatus`). **Read the log before theorising** about
what a companion perceived, decided, or is doing — it is better evidence
than the in-game chat, and it is how the bring-up was verified.

Observed quirks (Nov 1, 2026 — know them before "fixing" them):

- **Banter is deliberately damped.** The mod tells each companion "Last
  message was from an AI… don't keep the conversation going forever," so
  companions mostly work in parallel rather than riffing. To see
  interaction, prompt the pair together (an `all:` address or a question
  aimed at both).
- **The 7B expands orders literally.** A "get some wood" order became a
  Mine-and-Collect task listing essentially every log/wood/stem/hyphae
  variant in the game. Harmless, occasionally hilarious; narrow the order
  if it matters.
- **Duplicate reply lines in the log may be the mod's own prompt-dump
  logging**, not the companion double-sending. Check the actual in-game
  chat before treating it as a bug.
- Cross-companion awareness is real: one companion's chat line is fed to
  the others as an "Other AI Message" with their persona attached.
- **KNOWN CRASH — ConversationHistory JsonNull (hit live Nov 1, 2026,
  01:37 EDT; twice more Nov 2, 12:39 + 12:51 EST).** The integrated
  server can die with `java.lang.UnsupportedOperationException:
  JsonNull` at `adris.altoclef.player2api.ConversationHistory.toString`
  (ConversationHistory.java:296) via `ConversationManager.injectOnTick`.
  TWO trigger paths, both verified: (1) the trim path — log shows
  `ConversationHistory: prompt was [N] chars over the [budget] budget -
  dropped [X] oldest turn(s)` shortly before; (2) **no trim at all** —
  a single empty LLM reply (`json={}`, "message=null command=null")
  leaves a null-content turn in history, and the NEXT message's
  serialization dies on it, in a session of any length (Nov 2, 12:51:
  empty reply 12:47:14, crash 12:51:04, zero trim WARNs). The history
  budget is NOT hardcoded: it is the config key **`llm.maxPromptChars`**
  (16,000 on Nov 1; raised to **64,000** Nov 2, 2026, alongside the
  16k-context brain alias below). Conversation history is **in-memory
  only** — no history files exist in the instance — so a relaunch
  starts clean and the world save is unharmed. Fix = relaunch +
  rejoin. This is an upstream mod bug, NOT a config problem: personas,
  skins, and endpoint edits cannot cause it, and raising token budgets
  does NOT fix it. If it recurs repeatedly, capture the crash report
  plus any trim WARN line and file it upstream.

## 8. Voices — specced, NOT built

- TTS ships **on** by default in the mod, pointed at a factory placeholder
  (`localhost:8880`) where nothing listens. Failed voice calls silently
  leave the line as chat text — **harmless**; don't chase it as a fault.
- The mod expects a **Kokoro-FastAPI-shaped endpoint**: `POST
  /v1/audio/speech` (+ voice-list and health routes). Audio back **must be
  WAV, 16-bit mono, 24 kHz** — Java cannot decode MP3, so transcode.
- **The Minecraft client machine makes the voice calls** (the Victus), so
  any endpoint must be reachable from the Victus.
- Each companion's free-form `voice` string is the routing key: the plan is
  a small adapter on Tritium speaking the Kokoro shape and rendering each
  companion through a different **Breeze** voice profile. Breeze is not a
  Kokoro server; the adapter is a build task, not a config change.
- Full spec: **Hive entry 2526**. Build it only when Scotty green-lights it.

## 9. Roster & model pick (as of Nov 1, 2026)

- **Vetta** — woodland ranger/scout: reads trail, weather, and beast-sign;
  trail talk, early plain warnings, dry calm confidence; watches the
  owner's back. Skin: SkinsMC #210994, classic arms.
- **Rook** — scavenger-tinker foil to Vetta: magpie eye for loot, curious,
  upbeat, a little reckless; teases Vetta and listens when she warns him.
  Skin: SkinsMC #177860, classic arms.
- **Brain:** `qwen2.5:7b-instruct-q4_K_M` on Tritium Ollama (endpoint per
  §3) — picked for instruction-following in the size class that fits
  beside Jan on the 2060. **Since Nov 2, 2026 the config points at the
  alias `qwen2.5:7b-companion-16k`** (same weights, `PARAMETER num_ctx
  16384` baked in — fixes Ollama's silent head-first truncation of long
  companion prompts, TRK-0577), with `llm.maxTokens` 1024 and
  `llm.maxPromptChars` 64000 in `aicompanion.json`. Fleet
  model-residency policy (idle models unload; residency only for
  constant work or slow reloads) lives in **TRK-0501** — size future
  companion-brain changes under it.
