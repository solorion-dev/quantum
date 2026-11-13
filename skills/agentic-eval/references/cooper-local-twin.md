# Cooper local twin (pre-reconciliation)

Seeded from Codex `agentic-eval`; this is the divergent local copy (`local-agentic-eval`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# Agentic Evaluation Patterns

```
Generate → Evaluate → Critique → Refine → Output
    ↑                              │
    └──────────────────────────────┘
```

Use for quality-critical generation, tasks with clear evaluation criteria, or content requiring specific standards.

## Pattern 1: Basic Reflection

Generate, then loop: self-critique against criteria (structured JSON: PASS/FAIL + feedback per criterion), refine addressing only the failed criteria, up to max_iterations (default 3).

## Pattern 2: Evaluator-Optimizer

Separate generate() / evaluate() / optimize() into distinct steps. evaluate() returns a JSON score (0-1) plus per-dimension breakdown (accuracy, clarity, etc). Loop until score >= threshold (e.g. 0.8) or max_iterations reached.

## Pattern 3: Code-Specific Reflection

Generate code + tests together, run tests, and if they fail feed the error back to fix the code. Repeat up to max_iterations.

## Evaluation strategies

- **Outcome-based**: does the output achieve the expected result vs a reference answer.
- **LLM-as-judge**: compare two outputs pairwise against stated criteria.
- **Rubric-based**: score against weighted dimensions (e.g. accuracy 0.4, clarity 0.3, completeness 0.3), sum weighted 1-5 scores.

## Best practices

| Practice | Rationale |
|---|---|
| Clear criteria | Define specific, measurable evaluation criteria upfront |
| Iteration limits | Cap at 3-5 to prevent infinite loops |
| Convergence check | Stop if score isn't improving between iterations |
| Log history | Keep full trajectory for debugging |
| Structured output | JSON for reliable parsing |

## Checklist

- [ ] Define evaluation criteria/rubric
- [ ] Set score threshold for "good enough"
- [ ] Configure max iterations (default 3)
- [ ] Implement generate() / evaluate() (structured output) / optimize()
- [ ] Add convergence detection
- [ ] Log all iterations
- [ ] Handle evaluation parse failures gracefully
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
