---
name: improve-codebase-architecture
version: 1.0.0
description: "Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill through whichever one you pick."
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
# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities**: refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

Informed by the project's domain model and a shared design vocabulary (see codebase-design.md: **module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**). Use these terms exactly in every suggestion.

## Process

### 1. Explore

Scope before you scan (YAGNI). Decide *where* to look before you look:
- If the user named a direction, take it.
- Otherwise, walk back commit history (`git log --oneline`) to find hot spots.

Read the project's domain glossary (`CONTEXT.md`) and any ADRs in the area first, then spawn a sub-agent to walk the codebase and note friction: shallow modules, extracted-for-testability functions with no real locality, leaky seams, untested/hard-to-test parts.

Apply the **deletion test**: would deleting it concentrate complexity, or just move it?

### 2. Present candidates as an HTML report

Write a self-contained HTML file to the OS temp directory (not the repo). Use Tailwind via CDN for layout/styling and Mermaid via CDN for graph-shaped relationships; hand-built divs/SVG for more editorial visuals.

For each candidate: Files, Problem, Solution, Benefits (in terms of locality/leverage), Before/After diagram, Recommendation strength (Strong / Worth exploring / Speculative).

End with a Top recommendation section. Use CONTEXT.md vocabulary for domain terms and codebase-design.md vocabulary for architecture terms.

**ADR conflicts**: only surface a candidate that contradicts an existing ADR when the friction is real enough to warrant reopening it; mark it clearly.

Do NOT propose interfaces yet. Ask the user: "Which of these would you like to explore?"

### 3. Grilling loop

Once the user picks a candidate, use grilling.md to walk the decision tree: constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.

Use domain-modeling.md to keep CONTEXT.md current as decisions crystallize. Offer an ADR only when the user rejects a candidate for a load-bearing reason that a future explorer would need.
