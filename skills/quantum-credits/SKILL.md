---
name: quantum-credits
version: 1.0.0
description: "Reference for designing, building, reviewing, or extending the Quantum Credits economy — Scotty's simulated-blockchain internal currency for Quantum (bounty board, real proof-of-work + proof-of-useful-work mining, bounded Fed agent, founder paycheck, AI-verified knowledge quests, Quantum Finance). Use whenever work."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-credits]
dependencies:
  tools: []
  repos: [dsect-net/quantum]
  urls: []
maintainers: [cooper]
---
# Quantum Credits — economy reference

The authoritative design lives in three places, in this order when they disagree:
1. The signed decisions in this skill (Scotty's calls, most recent wins).
2. The dev brief: `~/workspace/your_files/Quantum-Credits-Bounty-Economy-Dev-Brief.md` (+ its Amendments A1–A4, appended) — mirror on Tritium at `/mnt/fast/quantum-os/antigravity/work/credits-build/BRIEF.md` and `AMENDMENTS.md`.
3. GitHub `dsect-net/quantum#15` and the research file `~/workspace/credits-build/research/crypto-finance-research.md` (parameter norms + sources).

## The system in one paragraph

Credits are Quantum's fungible internal currency (1 credit = 100 integer units; never floats). They run on a simulated, hash-chained, append-only ledger on Tritium — balances are derived by replay, never stored as an editable number. Credits price work on a bounty board, reward agents and humans, and circulate through an official bank (Quantum Finance). They are NOT real money in v1; a real-crypto bridge is future scope, credible only because the ledger is honest from block zero.

## Scotty's locked decisions (do not re-litigate)

- **No mint button, for anyone.** Issuance only via (a) genesis allocations and (b) mining rewards on the coded schedule, gated by real proof-of-work + validator quorum. The code path to arbitrary issuance must not exist. Scotty's test: "I can't be like 'I make myself have 10,000,000 credits.'"
- **Fungible, simulated.** Credits are fungible (the Oct 15 "non-fungible" phrasing was Scotty's own corrected slip). Not backed by real money in v1.
- **Hybrid monetary model:** hard supply cap (genesis config) + fixed declining (halving) emission + a Fed agent that tunes ONLY bounded levers via signed, timelocked policy transactions.
- **Mining is real work (A2).** Timer/schedule-only issuance is rejected. Blocks earn only with a valid hash-puzzle proof (nonce → hash < difficulty target; Bitcoin-style retarget, starting difficulty LOW for fleet hardware; GPU helps, CPU works, verification is one hash) PLUS a proof-of-useful-work track: a configured share of each block reward pays for verified fleet compute (result hash + spot re-computation + validator countersign), inside the same schedule/cap.
- **Founder income is protocol income, not printing (A1):** vesting genesis allocation + a per-epoch paycheck paid FROM TREASURY as a signed `paycheck` tx (short Treasury = short paycheck) + protocol fee split (default bounty fee 2%, split 40% burn / 40% Treasury / 20% founder royalty). All parameters in ONE genesis config module.
- **Quests (A3):** humans earn credits by teaching the fleet — explain/write/build datasets in their own words. AI verifier: rubric scoring + semantic dedupe (re-teaching known material pays ~nothing) + originality screen. Payout from escrow on pass; accepted knowledge lands in Quantum Memory/Codex with provenance.
- **Quantum Finance (A4)** (formerly Quantum Bank — "Bank" was too fintech; a brief Nov 11 pick of "Tally" was withdrawn the same night, and Scotty settled on **Quantum Finance** on Nov 12, 2026): the official bank + separate bank app (`apps/bank/`): checking/savings, statements, transfers, scheduled payments, income view. Savings interest is paid from a Treasury allocation at a Fed-bounded rate — never minted. Bounty app (`apps/bounty/`) keeps a wallet peek; service is `services/economy/` in `dsect-net/quantum`, branch `worker/antigravity/credits-economy-v1`, draft PR only — no merge, no deploy without Scotty.

## Invariants (verify these above all else when reviewing code)

1. Total issued ≤ supply cap, always; mint assertion enforced in code.
2. Σ debits = Σ credits for every non-mint/burn transaction; escrow is always fully backed.
3. No account goes negative, ever.
4. Balances-by-replay == cached balances view.
5. Mutating any historical transaction breaks chain verification at exactly that height.
6. A block without valid PoW proof or without a 2+ distinct-validator quorum seals nothing and earns nothing.
7. Fed actions outside their bounds (reward multiplier, fee %, grant limits) are rejected by validation; every policy change is signed + timelocked.
8. Fee splits sum to 100%; interest/paychecks/grants draw on Treasury balances that actually exist.
9. Quest payout releases only on a recorded verifier pass; dedupe is checked before payout.

Review method: property/invariant testing over example tests (see the acquired `property-based-testing` skill — Trail of Bits; fast-check fits the TypeScript service) + verification against the pushed artifact, never a builder's summary.

## Design patterns worth reaching for

- **Difficulty retarget (Bitcoin):** `new_target = old_target × (actual_timespan / expected_timespan)`, clamped to 4× per interval (Bitcoin retargets every 2016 blocks; credits use a much smaller interval, e.g. 100 blocks — see research file for tuned numbers).
- **Emission:** reward halves every `HALVING_INTERVAL_BLOCKS`; when the cap nears, rewards taper to zero and fees alone circulate.
- **Fed assessment metrics:** issuance vs cap, inflation/epoch, velocity (tx volume / average balances, MV=PQ framing), balance concentration, escrow locked, burn total, bounty completion rate, quest pass rate.
- **Escrow lifecycle:** lock on post (price + fee) → release on verified acceptance → refund-minus-fee on pre-claim cancel → frozen on dispute; resolution is a normal signed tx, never a balance edit.
- **Useful-work verification:** never trust the result — hash it, spot-recompute a random sample deterministically, require a validator countersignature.
- **Knowledge verification:** rubric + embeddings dedupe + a revision loop (fail → feedback → one revise) beats a single pass/fail gate.

## Where things live

- Build supervision: cron `credits-economy-build-watch` (this chat) verifies chunks, pushes, advances Antigravity chunk-by-chunk.
- Docs mirrors: Codex `projects/Quantum Credits and Bounty Board.md`; Notion "Quantum Credits & Bounty Board — Expanded Plan" (Quantum / Ideas & Tasks).
- References folder in this skill: add research-derived parameter tables here as they firm up (`references/parameters.md`).
