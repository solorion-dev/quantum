---
name: chat-interface-design
version: 1.0.0
description: "Use when designing a chat/conversational or AI-assistant interface — synthesizing reference app screenshots (ChatGPT, Grok, Muse, Claude, etc.) into a concrete design spec (palette, type scale, spacing, message-bubble/input-bar/streaming-state conventions) before or during implementation with a component library and."
tags: [imported]
status: active
provenance: imported
aliases: []
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Chat interface design

Two things generic UI skills (`better-ui`, `frontend-design`) don't cover: turning *several
named reference apps* into one coherent spec instead of an average of all of them, and the
interaction vocabulary specific to chat (streaming, typing, role-differentiated bubbles, a
composer that behaves differently while sending). This skill is for both, and is deliberately
thin — it hands off to `frontend-design`/`better-ui` for anything that isn't chat-specific.

## Synthesizing multiple references into one spec

When the brief is "make it feel like these apps" (plural), the failure mode is producing a
compromise that resembles none of them. Instead:

1. **Name what's actually shared, not what's easiest to copy.** Look for the trait present in
   *every* reference, even if it's not the most visually obvious one. A recurring finding: several
   "very different-looking" chat apps turn out to share the same underlying move — one restrained
   accent color used only for "yours/active/primary," everything else neutral. That's a real,
   nameable pattern; "colorful vs. monochrome" as a top-line description would miss it entirely.
2. **State the shared trait as a decision, with the counter-evidence.** If every reference is a
   light theme and the current build is dark, say that plainly and name it as the one thing worth
   arguing with — don't fold a theme change in quietly under a list of small tweaks.
3. **Separate "structure" from "theme."** A drawer→list→thread architecture and a color palette
   are different axes. References often agree on one and disagree on the other; conflating them
   produces a spec that fights itself (e.g. copying both a reference's *layout* and its unrelated
   *content*, like importing an entire settings-menu row list that doesn't apply to this product).
4. **Build a token table before describing any screen** — named color/type/spacing values pulled
   from the actual references (`accent: #3654F4 — sent bubbles, links, primary buttons`), not
   defaults from the last unrelated project. Cross-check every token against `frontend-design`'s
   generic-AI-tell list (warm-cream+serif, near-black+neon, identical-rounded-card kits,
   ALL-CAPS/monospace chrome, em-dash labels) — flag and justify any overlap rather than silently
   keeping it.
5. **Resist importing shape *and* content together.** A reference's settings screen having ten
   rows doesn't mean this product needs ten rows in the same categories — copy the *pattern*
   (grouped cards, icon+label+chevron), write the *content* from this product's own needs.

## Chat-domain vocabulary a generic UI skill won't supply

- **Message roles, not just "cards."** Sent vs. received need distinct fill/alignment, and in a
  multi-party room, a third state (other people's messages) that's visually distinct from both.
  Bubble color is not the only way to carry sender identity — a name label above the bubble often
  reads better in a group context than color-coding, since color-coding caps out around a dozen
  distinguishable hues.
- **Two tiers of message actions.** A persistent, low-friction row (copy, react) for the handful
  of actions worth zero extra taps, vs. a long-press/context-menu tier for the rest (reply,
  forward, delete). Collapsing both into one tier either clutters every message or hides
  everything behind a tap — check whether the target app's actual references use one tier or two
  before picking.
- **Streaming/in-flight states.** A typing/thinking indicator, a stop-generating affordance
  replacing send, and — for agentic responses — a live "is working" indicator distinct from a
  static typing dot. These have no generic-UI equivalent; a settings-screen skill has nothing to
  say about them.
- **The composer's own state machine.** Idle → has-draft → sending → error-with-draft-preserved.
  Losing what someone typed because a send failed is the one universally unforgivable chat bug —
  design the error state before the happy path.
- **Attachments render twice**, differently: a compact pre-send chip in the composer (with a
  remove affordance) and a different, richer rendering once sent and in the log (thumbnail,
  loading state, tap-to-expand). Don't design one and assume the other follows.
- **Mobile keyboard-avoidance.** The composer must stay pinned above the OS keyboard, sheets and
  long-press menus must not fight it for space (prefer full-screen push over a partial sheet when
  a keyboard is definitely coming, e.g. search) — this is chat-specific because chat is the UI
  pattern most likely to have the keyboard open the entire time it's used.

## Handoff

Once the spec exists, run `better-interface` (or the individual `better-*` skills) against the
actual implementation for accessibility, contrast, and general polish — this skill stops at "what
should this be," not "is this built well."
