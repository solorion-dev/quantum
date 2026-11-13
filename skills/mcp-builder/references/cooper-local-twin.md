# Cooper local twin (pre-reconciliation)

Seeded from Codex `mcp-builder`; this is the divergent local copy (`local-mcp-builder`) preserved verbatim for reference. The canonical SKILL.md wins where they conflict.

# MCP Server Development Guide

Create MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. The quality of an MCP server is measured by how well it enables LLMs to accomplish real-world tasks.

## Phase 1: Deep Research and Planning

**API Coverage vs. Workflow Tools:** Balance comprehensive API endpoint coverage with specialized workflow tools. When uncertain, prioritize comprehensive API coverage.

**Tool Naming:** Clear, descriptive names with consistent prefixes (e.g., `github_create_issue`), action-oriented.

**Context Management:** Concise tool descriptions, filterable/paginated results, focused data.

**Actionable Error Messages:** Guide agents toward solutions with specific suggestions.

Study the MCP spec (`https://modelcontextprotocol.io/sitemap.xml`, fetch pages with `.md` suffix). Recommended stack: TypeScript, streamable HTTP for remote servers (stateless JSON), stdio for local servers.

## Phase 2: Implementation

Set up project structure, then shared utilities: API client with auth, error handling, response formatting, pagination.

For each tool:
- **Input schema**: Zod (TS) or Pydantic (Python), with constraints, clear descriptions, examples.
- **Output schema**: define `outputSchema` where possible; use `structuredContent`.
- **Description**: concise summary, parameter descriptions, return type.
- **Implementation**: async I/O, proper error handling, pagination support.
- **Annotations**: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`.

## Phase 3: Review and Test

Check for: no duplicated code, consistent error handling, full type coverage, clear descriptions. Build and test with MCP Inspector (`npx @modelcontextprotocol/inspector`).

## Phase 4: Create Evaluations

Create 10 evaluation questions that are independent, read-only, complex (multi-tool-call), realistic, verifiable (single clear answer), and stable over time.

Output as XML:

```xml
<evaluation>
  <qa_pair>
    <question>...</question>
    <answer>...</answer>
  </qa_pair>
</evaluation>
```
## Available connectors

Use `muse.connector_search` to find the current connector docs before following
recovered instructions.
