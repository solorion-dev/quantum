# Cooper local twin (pre-reconciliation)

Seeded from Codex `minecraft-forge-modding`; this is the divergent local copy (`local-minecraft-modding`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# Minecraft Modding — Off To Market edition

Custom fleet skill, authored Oct 30, 2026 by Cooper for Scotty. No installable
skill targets Forge 1.19.2 (ecosystem research, Oct 30, 2026): the best public
bundle (`jahrome907/minecraft-agent-skills`, installed alongside this one)
targets NeoForge 26.x / 1.21.x and Forge 1.20.1 legacy. Use that bundle for
generic workflow scaffolding; **this skill overrides it on all version
specifics.**

## 0. Before touching code — mandatory checks

1. **Antigravity concurrency warning (Oct 30, 2026):** Google Antigravity CLI
   was actively making fixes to this project when this skill was written.
   Always check the repo's current branch and dirty/working state first, and
   coordinate before editing a file another agent may be editing. Never assume
   the tree you last saw is the tree that exists now.
2. **Read the repo, don't assert from memory:** `gradle.properties`,
   `build.gradle`, `src/main/resources/META-INF/mods.toml`, and the mod main
   class establish the real versions, mappings, and modid. Quote them with a
   date when you record them anywhere else.
3. **Repo home:** Cadential Studios GitHub org (Scotty believes edits/changes
   belong there). Verify the exact repo slug from the repo itself before
   committing. Commits by fleet agents go through the Quantum AI App
   (`quantum-ai-app[bot]`, hub `quantum_github_*` tools, acting agent as
   author) once that app is installed on Cadential-Studios and the hub's
   multi-installation routing exists — until then, do not claim that path
   works for Cadential-Studios repos; it is verified for dsect-net only.

## 1. Pinned facts — Off To Market

Verify against the repo before relying on any of these (source: CurseForge
project page, read Oct 30, 2026):

- Display name: "Off To Market: Enhanced Trading" / "Off to Market — Trading Deluxe"
- CurseForge slug: `off-to-market-enhanced-trading`, Project ID 1470472,
  author Scotty2Hotty999, 224 downloads, page updated 2026-02-25
- Minecraft: **1.19.2** · Loader: **Forge 43.x+** · Java 17 · ForgeGradle 5-era MDK
- Modid / config: `offtomarket` / `config/offtomarket-common.toml`
- License: All Rights Reserved © 2024–2026 Scotty Venable
- Optional integrations: JEI/REI for recipes
- Release naming follows Scotty's fleet convention: `AppName-vX.x-status`

Core systems: three-tier coin currency (Copper 1 / Silver 10 / Gold 100 CP,
Coin Bag, Coin Exchange, optional Gold Only mode); Trading Post (hub:
browse towns, shipments In Transit → At Market → Returning, quests,
diplomats, workers, merchant level/reputation); Trading Bin (price-per-slot);
Market Board; 10+ handcrafted towns with supply/demand pricing;
quests (standard/bulk/rush/specialty/charity, max 5 active, refresh at dawn,
expire 2–4 days); workers (Negotiator, Trading Cart; level to 10);
diplomats (premium +50%/+65%/+80% by town tier, 1.5× travel);
Animal Trade Slips (Peenam Animal Market); dynamic mod-compat town
generation by runtime item scanning/categorisation (Farmer's Delight,
Twilight Forest, Ars Nouveau, etc.; tested in a 300+ mod pack).

### Player feedback on record (CurseForge comments, all 7, read Oct 30, 2026)

- **Infinite-money bug (SuperFanatic, ~Jun 2026) — highest-priority known bug:**
  the Shipment Note received after a shipment lands IN the Trading Bin, is
  itself worth 9 CP, and can be re-shipped for another note in an endless
  loop. Fix directions the reporter suggested and Scotty endorsed in reply
  (~Jul 2026): move shipment notes into a Ledger book, and/or make notes
  unsellable and ineligible for the Trading Bin. **Check whether this is
  already fixed / in progress (Antigravity) before starting it.**
- **Mod-item price balance + blacklist request (same comment):** dynamic
  mod-compat prices are badly scaled, and players want a config blacklist of
  items that cannot be bought/sold.
- **Physical caravans + 1.20.1 port request (ILikeEmBig, ~Jul 2026):** visible
  caravan entities are already on the public roadmap; the 1.20.1 ask is a
  port *forward* from 1.19.2, despite the commenter saying "backport."
- **Modpack permission:** granted by Scotty in comments (May 2026).
- No crash or mod-conflict reports in CurseForge comments as of Oct 30, 2026.

### Roadmap already promised publicly (CurseForge page)

Near-term: economy balance pass, shipment tracking edge cases (shipments
stuck/not returning), quest expiry/refresh audit, Trading Bin UX, Guide Book
rewrite, JEI/REI integration, config validation, crash hardening.
Do not re-promise these as new; they are existing commitments.

## 2. Version law

- **Forge 1.19.2 docs win.** Version-pinned docs:
  https://docs.minecraftforge.net/en/1.19.2/
- Traps vs newer guidance (jahrome907 bundle, NeoForge/Fabric docs, most
  tutorials written after 2023):
  - Registries: Forge `DeferredRegister` + `RegisterEvent` era patterns for
    1.19.2; do not import NeoForge registration idioms blindly.
  - Persistence: **Capabilities** (`AttachCapabilitiesEvent`, `ICapabilityProvider`)
    + SavedData in 1.19.2 — NeoForge **data attachments** do NOT exist here.
  - Networking: Forge `SimpleChannel` with explicit packet IDs — the
    1.20.5+ custom payload system does NOT exist here.
  - Metadata: `META-INF/mods.toml` — NOT `neoforge.mods.toml`.
  - Build: **ForgeGradle 5** + `gradlew` — NOT ModDevGradle/NeoGradle.
  - Mappings: Mojang official (Mojmap), commonly with **Parchment** layered
    on top for parameter names/javadocs in 1.19.2-era MDKs.
- Porting primers (only when Scotty decides a port):
  https://docs.minecraftforge.net/en/latest/legacy/porting/

## 3. Build & Gradle

- MDK layout; version pins live in `gradle.properties` (minecraft, forge,
  mappings channel/version, mod version).
- Runs: `gradlew runClient`, `gradlew runServer`, `gradlew runData`
  (datagen), `gradlew runGameTestServer`.
- Build: `gradlew build` → reobfuscated jar in `build/libs/`. That jar — not
  the dev jar — is what ships to CurseForge.
- Dist safety is the classic Forge bug class: never reference client-only
  classes (screens, renderers) from common code paths; use `DistExecutor` /
  `@Mod(value, dist)` patterns and test on a dedicated server.

## 4. Registries & lifecycle

- `DeferredRegister` for: items (Copper/Silver/Gold Coin, Coin Bag, Ledger,
  Guide Book, Shipment Note, Animal Trade Slip), blocks + BlockEntities
  (Trading Post, Trading Bin, Market Board), MenuTypes, entities, sounds.
- Setup: `FMLCommonSetupEvent` (networking, town/economy init),
  `FMLClientSetupEvent` (screens via `MenuScreens`, renderers).
- Every sellable/tradeable thing resolves through the economy/pricing layer —
  never hardcode prices at call sites; the price service is what config,
  reputation, supply/demand, workers, and the blacklist all hook into.

## 5. Data & persistence

- Merchant level/XP, per-town reputation, workers, active shipments, quests,
  and diplomat requests are **server-authoritative saved state**: SavedData
  on the overworld for global economy state, capabilities for player state.
- NBT serialisation must be defensive: missing/legacy tags from older saves
  must not crash a world load (crash hardening is a stated roadmap item, and
  the mod is played in 300+ mod packs).
- Config: `ForgeConfigSpec` in `offtomarket-common.toml` — global price
  multiplier, Gold Only mode, dynamic towns toggle, supply/demand tuning,
  debug mode (instant travel / free purchases). Validate ranges and log
  clear errors on bad values.
- **Blacklist (player-requested):** config list of item IDs excluded from
  buying/selling, checked in the pricing layer so it covers both handcrafted
  and dynamically generated towns.

## 6. GUIs / containers

- `AbstractContainerMenu` + client `Screen` pairs; Trading Post tabs
  (Browse, Shipments, Quests, Workers, Diplomats, Coin Exchange), Trading
  Bin price-per-slot UI (roadmap: replace clunky click-to-set with inline
  editing / a dedicated price screen), Market Board display.
- Sync with container data slots for scalars and packets for complex state.
  Menus must never trust client-sent prices or quantities — the server
  recomputes every trade (the coin economy is dupe-bait by design; see the
  Shipment Note bug).

## 7. Networking

- One `SimpleChannel` for the mod; document packet IDs in one place.
- Packets declare direction; handlers `enqueueWork` onto the main thread and
  validate sender state (open menu, distance, shipment ownership) before
  mutating anything.
- Shipment phase transitions (In Transit → At Market → Returning → Done)
  happen server-side on tick/time checks, never on client request.

## 8. Datapack JSON & datagen

- Recipes, loot tables, tags, advancements via datagen where practical;
  hand-written JSON validated against the 1.19.2 schemas on the Minecraft Wiki.
- Conditional data: `forge:mod_loaded` / item-exists conditions for mod-compat content.
- Towns are handcrafted data today (10+); datapack-defined towns are a
  roadmap item — design new town data as if it will become datapack JSON.
- Dynamic mod-compat towns: runtime scan of other mods' items, categorise
  (ingots/gems/food/weapons/armor/magic…), generate a themed market. Pricing
  from category heuristics is known-bad at the extremes (player report) —
  clamp prices and honour the blacklist.

## 9. JEI / REI integration

- JEI is primary on Forge 1.19.2: `IModPlugin`, categories/recipes for coin
  exchange and custom crafting. Compile against the JEI **API only**; full
  jar is a runtime dependency.
  Wiki: https://github-wiki-see.page/m/mezz/JustEnoughItems/wiki
  ("1.18.2 to 1.20.2 for Forge or Fabric" covers 1.19.2).
- REI is secondary/optional (needs Architectury + Cloth Config on Forge).
  Maven: https://maven.shedaniel.me

## 10. Testing & verification

- A change is not verified by compiling alone (fleet rule: developers must
  SEE what they build).
- Minimum: `gradlew build` clean, `runClient` smoke (Trading Post opens,
  a trade completes), dedicated-server start without dist crashes.
- GameTests (`minecraft-testing` skill from jahrome907) for economy logic:
  coin conversion, shipment lifecycle, quest expiry at dawn.
- Regression test the Shipment Note loop specifically: notes must never be
  sellable or bin-eligible.
- Read `run/logs/latest.log` and crash reports before claiming a fix.

## 11. Publishing

- CurseForge: correct game-version (1.19.2) + Forge loader IDs, release type
  (alpha while WIP), changelog in Scotty's words, dependencies marked.
  Upload API: https://support.curseforge.com/support/solutions/articles/9000197321-curseforge-upload-api
  General API: https://docs.curseforge.com/rest-api/
  (`docs.curseforge.com` "for Studios" is for game studios, not mod authors.)
- Modrinth cross-post is available if Scotty wants it:
  https://docs.modrinth.com/api/
- CI/release workflow scaffolding: `minecraft-ci-release` skill (jahrome907).
- **MCreator is NOT the path** for this mod — visual generator output cannot
  be retrofitted onto this hand-written codebase.

## 12. Knowledge-base index (check the version-pinned page, not "latest")

- Forge 1.19.2 docs (PRIMARY): https://docs.minecraftforge.net/en/1.19.2/
- NeoForge docs (migration reference only): https://docs.neoforged.net/
- Fabric docs (alt-loader reference only): https://docs.fabricmc.net/
- Minecraft Wiki (vanilla mechanics, JSON schemas — never the Fandom mirror): https://minecraft.wiki/
- Parchment mappings: https://www.parchmentmc.org/ · https://parchmentmc.org/faq.html
- JEI wiki: https://github-wiki-see.page/m/mezz/JustEnoughItems/wiki
- REI repo/maven: https://github.com/shedaniel/RoughlyEnoughItems · https://maven.shedaniel.me
- CurseForge upload API + REST API: see §11
- Modrinth API: https://docs.modrinth.com/api/

Installed companion skills (jahrome907/minecraft-agent-skills, Oct 30 2026):
`minecraft-modding`, `minecraft-ci-release`, `minecraft-testing`,
`minecraft-datapack`, `minecraft-resource-pack` — generic scaffolding only,
NeoForge 26.x / Forge 1.20.1 oriented; this skill wins on conflicts.
Not installed, deliberately: Bukkit/Spigot plugin skills (wrong target),
Blockbench MCP skills (install only when doing models, repo <100 stars),
`siredvin/minecraft-modding-skills` (0 stars — mined for ideas only).

## 13. Release discipline (Off To Market)

- **Container-sync / inventory / NBT persistence changes do NOT ship on
  unit tests alone.** They need a `runClient` pass AND a dedicated-server
  smoke pass before release. The 0.6.3 sync-fix class of change (double-chest
  sync, ledger persistence) is exactly where this bites — data-class tests
  cannot see a container desync.
- **The CHANGELOG.md entry lands in the SAME commit as the version bump.**
  0.6.4 and 0.6.5 shipped Oct 31, 2026 with no changelog entries and had to
  be backfilled into Notion after the fact. Never again: no bump without
  its changelog entry in the same commit.
- **Removals get announced in the release post, explicitly.** When a shipped
  change removes an item or feature players may hold — e.g. 0.6.2 removed
  the Shipment Note item outright to close the infinite-money exploit —
  the release post must say so in plain words. A silent removal reads as
  a bug (or lost items) to existing worlds.
