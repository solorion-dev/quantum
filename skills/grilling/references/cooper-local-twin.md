# Cooper local twin (pre-reconciliation)

Seeded from Codex `grilling`; this is the divergent local copy (`local-grilling`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# Grilling

## Map the design tree

- Treat the plan or decision as a design tree where every decision branches into the decisions that hang off it.

- Work the tree in rounds and track which decisions are settled and which are still open.

- Define the frontier as every decision whose prerequisites are already settled.

## Ask the frontier

- Ask the whole frontier in one round, number each question, and give your recommended answer for each one.

- Wait for the user answers before asking the next round.

- Put a question whose answer depends on another open question in a later round, not this one.

- Recompute the frontier after each round because settled decisions unblock new questions.

- Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

## Find facts yourself

- Finding _facts_ is your job, never the user's.

- When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it.

- Do not ask the user for anything you could look up yourself.

- Do not block on it because a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report.

- Ask the rest of the frontier now.

- The _decisions_ are the user's, so put each to them and wait.

## Finish the interview

- Continue until the frontier is empty and every branch of the design tree has been visited.

- Do not act on the plan until the user confirms you have reached a shared understanding.

- Summarize the settled decisions plainly when the user confirms that understanding.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Ask for a shorter pass when the user wants the top risks only, and name the branches you left unvisited.

- Split a very large tree into named subtrees and finish one subtree before opening the next.
