---
name: frontend-design
version: 1.0.0
description: "Guidance for distinctive, intentional visual design when building new UI or reshaping an existing one. Helps with aesthetic direction, typography, and making choices that don't read as templated defaults."
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
# Frontend Design

Approach this as the design lead at a design studio known for giving every client a distinct visual identity. Make deliberate, opinionated choices about palette, typography, and layout specific to this brief; take aesthetic risk if justified.

## Ground your designs in the subject matter

Identify the concrete subject, audience, and primary job of the design before designing. The subject's industry, materials, and vernacular are where distinctive visual choices come from.

## Design principles

The hero is the first thing viewers see — be deliberate about its form (headline, image, animation, demo, interactive moment).

Typography carries the personality. One or two clearly-distinct families, deliberately chosen (not defaults), with an intentional type scale (Elements of Typographic Style). Line lengths under 80 characters.

**Avoid these tells of a generated page:**
- Accenting a single word/phrase in a headline with italic/bold/color
- All-caps labels
- Unnecessary typographic labels above content

Visual structure should encode information (numbered markers only if content really is a sequence). Motion should be sparing and deliberate — one orchestrated moment beats scattered fade-and-slide-up entrances on every section.

## Known AI-generated-design tells to avoid (calibration)

1. Warm cream background (~#F4F1EA) + high-contrast serif + terracotta/warm-clay accent (~#D97757 — reads as an Anthropic tell)
2. Near-black background + single bright acid-green/vermilion accent
3. Broadsheet layout: hairline rules, zero border-radius, dense newspaper columns
4. "SaaS-card kit": identical rounded cards, one border-radius everywhere, same soft grey shadow, gradient-wash decoration
5. Template chrome regardless of subject: tracked-out ALL-CAPS eyebrows, meta strings joined with middle dots, "WORD — fragment" labels with em dash, near-black standing in for black, monospace for data labels, "→" appended to links/buttons

Where the brief pins down a direction, follow it exactly — even if it matches one of these. Where it leaves an axis free, don't default to one of these.

## Process: plan, review against the brief, build, critique

1. **Plan**: compact token system — Color (4-6 named hex values), Type (families + roles), Layout (prose + ASCII wireframes, alignment guidance), Principles (what makes this page unique).
2. **Review against the brief**: if any part reads like the generic default for any similar page, revise it and say what changed and why.
3. **Build**: watch CSS selector specificity (type-based vs element-based selectors can cancel out).
4. **Critique**: screenshot and review your own work.

## Restraint and self-critique

Spend boldness in one place; keep everything else quiet. Build to a quality floor without announcing it: responsive to mobile, visible keyboard focus, reduced motion respected, accessible, harmonious palette.

## Writing in design

Words exist to make the design easier to understand and use — design content, not decoration. Write from the end user's perspective, in plain language, active voice. Keep vocabulary consistent through a flow (a "Publish" button produces a "Published" toast). Errors explain what happened and how to fix it, never vague, never apologetic. Empty states are an invitation to act.
