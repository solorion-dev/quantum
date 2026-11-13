---
name: vercel-react-best-practices
version: 1.0.0
description: "React and Next.js performance optimization guidelines from Vercel Engineering. Use when writing, reviewing, or refactoring React/Next.js code to ensure optimal performance patterns."
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
# Vercel React Best Practices

70 rules across 8 categories, prioritized by impact.

| Priority | Category | Impact | Prefix |
|---|---|---|---|
| 1 | Eliminating Waterfalls | CRITICAL | `async-` |
| 2 | Bundle Size Optimization | CRITICAL | `bundle-` |
| 3 | Server-Side Performance | HIGH | `server-` |
| 4 | Client-Side Data Fetching | MEDIUM-HIGH | `client-` |
| 5 | Re-render Optimization | MEDIUM | `rerender-` |
| 6 | Rendering Performance | MEDIUM | `rendering-` |
| 7 | JavaScript Performance | LOW-MEDIUM | `js-` |
| 8 | Advanced Patterns | LOW | `advanced-` |

## Key rules by category

**Waterfalls**: check cheap sync conditions before awaiting; defer await into the branch that uses it; Promise.all() for independent ops; start promises early in API routes; Suspense to stream.

**Bundle**: avoid barrel-file imports; prefer statically analyzable paths; next/dynamic for heavy components; defer third-party scripts past hydration; load modules only when the feature activates; preload on hover/focus.

**Server**: authenticate server actions like API routes; React.cache() for per-request dedup; LRU cache cross-request; avoid duplicate RSC prop serialization; hoist static I/O to module level; avoid module-level mutable request state; minimize client-component data; parallelize fetches (including nested, via Promise.all); after() for non-blocking work.

**Client fetching**: SWR for dedup; dedupe global event listeners; passive listeners for scroll; version/minimize localStorage schema.

**Re-renders**: don't subscribe to state only used in callbacks; memoize expensive extracted components; hoist default non-primitive props; primitive effect dependencies; subscribe to derived booleans not raw values; derive state during render not effects; functional setState; lazy useState init; skip memo for simple primitives; split hooks with independent deps; move interaction logic into event handlers not effects; startTransition for non-urgent updates; useDeferredValue to keep input responsive; refs for transient high-frequency values; never define components inside components.

**Rendering**: animate a div wrapper, not the SVG itself; content-visibility for long lists; hoist static JSX; reduce SVG coordinate precision; inline script for client-only data to avoid hydration flicker; suppress expected hydration mismatches explicitly; Activity component for show/hide; ternary not && for conditionals; useTransition for loading state; resource hints for preloading; defer/async on script tags.

**JS perf**: batch DOM/CSS changes; Map for repeated lookups; cache property access and function results in loops; cache storage reads; combine filter/map passes; check array length before expensive comparisons; early return; hoist RegExp out of loops; loop instead of sort for min/max; Set/Map for O(1) lookups; toSorted() for immutability; flatMap to map+filter in one pass; requestIdleCallback for non-critical work.

**Advanced**: don't put useEffectEvent results in effect deps; store event handlers in refs; initialize the app once per load; useLatest for stable callback refs.

## How to use

Read individual rule files for full explanations and code examples (correct vs incorrect), e.g. `rules/async-parallel.md`, `rules/bundle-barrel-imports.md`. Full compiled doc: `AGENTS.md` in the source repo.
