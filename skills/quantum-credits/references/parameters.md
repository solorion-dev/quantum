# Quantum Credits — tuned parameters (from research, Oct 15, 2026)

Source: `~/workspace/credits-build/research/crypto-finance-research.md` (372 lines, 19+ primary-source citations: Bitcoin whitepaper + pow.cpp, Filecoin spec, Primecoin paper, BOINC journal, EIP-1559, SF Fed Taylor letter, AWS Ground Truth docs). Items marked [REC] there are research recommendations; Scotty's locked decisions in the skill outrank them. All values live in the ONE genesis config module in `services/economy/src/genesis.ts`.

## Mining / emission
- Target block interval: **60s**.
- Difficulty: set from MEASURED fleet hash rate (leading-zero-bits table in research §2), not guessed.
- Retarget: every **100 blocks**, median timestamps, adjustment clamped to **[0.5×, 2×]** per window (tighter than Bitcoin's 4× — small chain, fewer miners).
- Partial credit: share-based accounting for miners who submit near-miss proofs, so small CPU miners still earn proportionally.
- Emission: fixed declining schedule with halving (brief §5.2) toward the hard cap; reward only with valid proof + 2-validator quorum.

## Founder compensation (three separate coded instruments — never conflated)
1. **Founder allocation: 8% of supply**, **12-month cliff, then 36-month linear vesting** (norms: insider band 10–20% is tolerated in real protocols; Filecoin team 15% / 6-yr vesting; Bitcoin 0% premine and Ethereum's ~16.7% genesis insider share are the two cautionary poles).
2. **Fee royalty:** bounty posting fee with split **40% burn / 40% Treasury / 20% founder** (A1).
3. **Optional fixed paycheck** from Treasury (A1), kept inside a seigniorage cap so total founder take stays a visible, bounded % — the Fed assessment reports "founder take" as a named metric.
- Bank display (A4): wallet shows the founder's position in four lines — vested balance, unvested balance, royalty earned to date, paycheck history. Radical legibility is the anti-"10,000,000 credits" property.

## Fed v1 parameter sheet (research §6)
- Emission multiplier controller (Taylor-style): adjust within the brief's **[0.5×, 1.5×]** fences based on measured basket inflation + activity gap.
- Health dashboard (10 metrics): velocity, basket inflation, Gini / HHI / Nakamoto coefficient, bounty completion rate, escrow float, founder take %, quest pass rate, savings uptake.
- Seigniorage is accounted explicitly: issuance value accrues to miners/Treasury per the schedule — never to an admin.

## Quest verification pipeline (research §5/§6 thresholds)
1. Gold-standard items seeded at **~10%** of quest flow (known answers check the contributor AND the verifier).
2. **2-verifier quorum** for payout.
3. Rubric scoring with a pass threshold; embedding dedupe: **cosine > 0.92 = reject as duplicate; 0.85–0.92 = derivative, partial pay**.
4. Commit-reveal hashing on submissions (no copying another submitter's work).
5. Random **re-audit of 5%** of accepted submissions within 30 days; failed re-audit claws back and hits reputation.
6. Verifiers stake **5%** (skin-in-the-game) on their verdicts.
7. Admission rule of thumb: verification should cost ~10× less than the payout it protects (the verification-asymmetry check).
