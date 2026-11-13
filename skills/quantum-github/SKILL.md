---
name: quantum-github
version: 1.0.0
description: "Quantum GitHub skill. Use for dsect-net issues, draft PRs, or merge talk, and for checking that scheduled GitHub work uses an unattended auth path."
tags: [quantum, fleet]
status: active
provenance: quantum
aliases: [local-quantum-github]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Quantum GitHub

## Pass

- Search memory for the repo and issue number before opening a second card for the same work.

- Read with the GitHub tools for allowed repos only.

- Treat a draft PR as a proposal. Do not say it merged unless the merge commit is on the default branch.

- Take goal ids from `projects/README.md`, not from a commit message. That is the quantum goals method.

- Treat a green PR as separate from a deploy. Nebula deploys follow the nebula method.

## Check the auth path for scheduled work

- Check how a job will authenticate before you create, enable or re-enable any scheduled or background job that reads or writes GitHub.

- Reject a per call approval connector path for unattended work, including the Muse GitHub connector CLI under `/opt/hatch/bin/github`. A job that needs the user to approve each call will flood the user with approval cards instead of finishing.

- Route scheduled GitHub work through the Quantum AI App via the Tritium MCP bridge, the path the PR Hygiene Weekly definition was rewired to on Oct 19, 2026. Do not route it through the suspended cooper-the-fox gh CLI, and do not run bulk or burst work under the user's personal GitHub account.

- Run one harmless read or one single manual run first and count the approval prompts it produces. Enable the schedule only when that test run produces no per call approval prompts.

- Stop and pause the job if a run starts producing repeated approval prompts or relaunches the same script. Report the count and the path it used, and leave the job paused rather than retrying it in a loop.

## Close

- Leave a workspace note with the repo, number and state.

- Record a Hive decision only when the user decided it.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Do a single manual run before the first scheduled run whenever the auth path, the repo set or the write scope changed.

- Prefer a read only test run over a write run when you only need to prove the auth path works unattended.
