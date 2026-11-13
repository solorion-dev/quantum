---
name: quantum-live-tv
version: 1.0.0
description: "Jellyfin Live TV skill. Use after a tuner or M3U change. Run Refresh Guide, not Refresh Channels. Playback is unproven until Scotty confirms a Guide Refresh and a real stream."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-live-tv]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum Live TV

One rule, from the 2026-10-06 evolution note. Do not restate it as five status pings.

## Pass

1. After any Jellyfin tuner or M3U change, Refresh Guide. Not Refresh Channels. A stale channel cache can still show 1000+ dead channels after the library has the curated count.
2. Playback stays unproven until Scotty confirms a Guide Refresh and a real stream.
3. On Tritium, `sqlite3` is not on PATH. Query `library.db` with `python3` via the operator shell, not a guessed host command from this skill.

## Close

Workspace note with what was refreshed and whether he confirmed a stream. Do not write a hive fact that playback works without that confirmation.
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
