---
name: local-embedder-resilience
description: Use when Quantum Memory adds or searches fail, memory_health_check reports degraded, an agent says "EMBEDDER DOWN", llama-embed is down, memory writes are blocked, or tracker records come out unembedded. Covers diagnosing the dead embedder on Tritium, pinning the embedding model's exact provenance, the critical-backups lifeboat, parity probes, and the staging-database fallback. Never improvise a substitute model.
---

# Quantum Memory Embedder Resilience

## Purpose
Memory reads can look fine while writes are dead: the DB answers list calls, but add/search need the embedder (`llama-embed.service`, :8082 on Tritium). A dead embedder silently blocks every memory write and leaves tracker records unembedded. Diagnose it, restore the *identical* model, and never poison the index with a substitute.

## Diagnose
1. `memory_health_check` first. Read both halves: DB ok ≠ embedder ok. List working proves only that reads work.
2. On Tritium: `systemctl status llama-embed.service` + its journal. It usually doesn't crash — it never starts: `RequiresMountsFor=/srv/ai/models` fails when that mount is absent.
3. Check the mount, not the service: `findmnt /srv/ai/models`, `blkid` for the filesystem UUID. /srv/ai/* are btrfs subvolumes — on Oct 21 the model lived on the WD Green, which was out of the machine, and no copy existed on any present storage.
4. Count before touching anything: `memory_stats` total is the parity baseline (1,854 on Oct 21). A pilot add that returns EMBEDDER DOWN with the count unmoved proves no partial write happened.

## The identity rule
**Never substitute a different model or quantization into the main index.** Every model draws its own vector map; mixing spaces silently corrupts retrieval — no errors, healthy counts, garbage neighbors. Byte-identical file = provably the same map. This rule outranks urgency.

## Provenance before download
1. Pin the exact source from on-box evidence: the unit's `-m` path and filename, install scripts, hub code, HuggingFace cache metadata.
2. Record repo, revision, filename, expected size + sha256 in the manifest BEFORE downloading.
3. If the evidence stays ambiguous between candidates, stop and give Scotty the candidates. Do not guess.

## Lifeboat (restore with the identical model)
1. Download the pinned GGUF to the critical-backups store: `/mnt/spare/critical-backups/models/` on Tritium. Verify size + sha256 against the manifest.
2. Bind-mount the backup models dir at `/srv/ai/models` — the bind satisfies `RequiresMountsFor` without touching the Green's fstab entries. Keep a .bak of anything you change; write down the un-wind step for when the real volume returns.
3. `systemctl start llama-embed.service`, then verify on named surfaces, all four: service active; a direct embedding request to 127.0.0.1:8082 returns a vector; `memory_health_check` flips to ok; a real `memory_search_memory` query returns sane, relevant results.
4. **Probe vectors:** embed 3 fixed probe sentences with the restored copy and store the vectors in the manifest. When the original model returns, the same probes settle parity (cosine ≈ 1.0 = identical space).

## Staging fallback (identity unproven, writes can't wait)
Text is the source of truth; vectors are derived. Stand up a *separate* staging memory store (second instance, own DB file, candidate embedder) and write there — staging vectors live in their own consistent space and never touch the main index. On the real embedder's return, re-embed the staged **texts** with the original model and merge into main. Tracker records do NOT go through staging — their embed backlog waits for the real embedder.

## After recovery
- File the held payload backlog (filer + checklist in the night's workspace folder), reporting counts before/after.
- Clear the tracker embed backlog: records filed while the embedder was down sit unembedded. Use the tracker CLI's re-embed/reindex path if it offers one; report how many embedded. Never hand-edit the DB to force it.

## Critical-backups layout (standing)
`/mnt/spare/critical-backups/` on the 2TB SATA spare (bay1-2tb): `models/`, `tracker/`, `hub-state/`, `configs/` + a README stating the role. Off-box mirror = Scotty's Google Drive (his call, Oct 21): the same-box copy covers a drive being out of the machine; the Drive mirror covers losing the box.
