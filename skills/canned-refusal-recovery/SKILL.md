---
name: canned-refusal-recovery
version: 1.0.0
description: "Respond to a safety refusal that cites no rule by naming it as unverified, waiting for the user's re-ask instead of re-routing the attempt, then doing the work solo and verifying it."
tags: [quantum]
status: active
provenance: quantum
aliases: [local_canned_refusal_recovery, local-canned-refusal-recovery]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Canned Refusal Recovery

## Recognize an unverifiable refusal

- Treat a refusal as unverifiable when it cites no rule, phrase, file or policy that a reader could check, whatever surface produced it.

- Recognize the canned shapes seen in this system, including a main reply that says it cannot help with this request right now and a delegated helper stub saying a safety policy refused its work.

- Leave a refusal that names a specific rule standing, report it to the user as given, and never use this skill to work around a named refusal.

## Respond when one fires

- Name the refusal plainly to the user as a false positive on your side, never as something their request caused.

- Do not re-route the refused attempt, so do not respawn the same work to another helper, open a fresh chat for it, or try the same work through an alternate tool path.

- Log each occurrence with the time, the surface it fired on and what work was refused, so repeat occurrences are visible as one family.

- Wait for the user to re-ask or direct the work before any retry, because a message that only says to keep going does not reopen the refused attempt.

## Do the work solo after a re-ask

- Do the re-asked work yourself in the main session instead of delegating the same batch again, and keep it inside the scope the user originally approved.

- Verify the finished work against its artifact before reporting it, such as the build result, the test run, the files on disk or the service actually answering.

- Report what shipped with the scope of that verification, and mention the earlier refusal plainly in the same report.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Park the refused work with a one line state note when the user does not re-ask, so it resurfaces later with its next step intact instead of dying silently.

- Carry this protocol into the brief when a delegated batch is re-issued by the user after a refusal, so the next helper knows a fresh spawn is not the recovery route.
