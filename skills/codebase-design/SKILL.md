---
name: codebase-design
version: 1.0.0
description: "Shared vocabulary for designing deep modules. Use when the user wants to design or improve a module's interface, find deepening opportunities, decide where a seam goes, make code more testable or AI-navigable, or when another skill needs the deep-module vocabulary."
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
# Codebase Design

Design **deep modules**: a lot of behaviour behind a small interface, placed at a clean seam, testable through that interface. Use this language and these principles wherever code is being designed or restructured. The aim is leverage for callers, locality for maintainers, and testability for everyone.

## Glossary

Use these terms exactly: don't substitute "component," "service," "API," or "boundary."

**Module**: anything with an interface and an implementation. Deliberately scale-agnostic: a function, class, package, or tier-spanning slice.

**Interface**: everything a caller must know to use the module correctly: type signature, invariants, ordering constraints, error modes, required configuration, performance characteristics.

**Implementation**: what's inside a module. Distinct from **Adapter**: a thing can be a small adapter with a large implementation (a Postgres repo) or a large adapter with a small implementation (an in-memory fake).

**Depth**: leverage at the interface. A module is **deep** when a large amount of behaviour sits behind a small interface, **shallow** when the interface is nearly as complex as the implementation.

**Seam** (Michael Feathers): a place where you can alter behaviour without editing in that place; the *location* at which a module's interface lives.

**Adapter**: a concrete thing that satisfies an interface at a seam. Describes *role*, not substance.

**Leverage**: what callers get from depth — more capability per unit of interface learned.

**Locality**: what maintainers get from depth — change, bugs, knowledge, and verification concentrate in one place.

## Deep vs shallow

Deep module = small interface + lots of implementation. Shallow module = large interface + little implementation (avoid).

When designing an interface, ask: can I reduce the number of methods? Can I simplify the parameters? Can I hide more complexity inside?

## Principles

- **Depth is a property of the interface, not the implementation.** A deep module can be internally composed of small, mockable, swappable parts; they just aren't part of the interface.
- **The deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam. If you want to test *past* the interface, the module is probably the wrong shape.
- **One adapter means a hypothetical seam. Two adapters means a real one.** Don't introduce a seam unless something actually varies across it.

## Designing for testability

1. **Accept dependencies, don't create them.**
2. **Return results, don't produce side effects.**
3. **Small surface area.** Fewer methods = fewer tests needed. Fewer params = simpler test setup.

## Rejected framings

- Depth as ratio of implementation-lines to interface-lines (Ousterhout): rewards padding the implementation.
- "Interface" as just the TypeScript `interface` keyword or a class's public methods: too narrow.
- "Boundary": overloaded with DDD's bounded context. Say **seam** or **interface**.
