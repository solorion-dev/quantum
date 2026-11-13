---
name: verify-authoritative-surface
version: 1.0.0
description: "Verify status claims against the authoritative surface, including fresh money and subscription billing channel checks, before reporting them as fact."
tags: [quantum]
status: active
provenance: quantum
aliases: [local-verify-authoritative-surface]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Verify Against the Authoritative Surface

## Name the claim and its surface

- Name the claim before checking it, such as code is green, an email was sent, a deploy is safe, a charge landed, or a subscription is cancelled.

- Map the claim to the surface that actually decides it and check only that surface.

- Fetch the remote ref and parse or test it for pushed code, or use a clean worktree of that ref.

- Read the actual Sent record for an email claim, because a draft or a plan to send proves neither sending nor not sending.

- Read the target checkout branch, HEAD and dirty state before any deploy or pull, and compare it against the repo.

- Check what a specific user sees through that user account view, because an admin or agent view does not establish the user experience.

- Read the artifact itself for completed work, such as git log, files on disk or test output, and never treat a summary or your own earlier diagnosis as the artifact.

## Check money and subscriptions at point of use

- Treat every money figure as point of use and report it with the time it was read and the surface it came from.

- Treat a stale bank or aggregator read that shows no charge as unknown, never as proof that no charge exists.

- Verify the vendor and the exact billing channel from a fresh issuer or vendor notification before acting on a charge or a cancellation request.

- Confirm the channel again when the first source and a later source disagree, and correct the earlier claim plainly the same session.

- Report a cancellation as confirmed only when a verified view of the billing account shows cancelled or inactive, or the user confirms they completed it themselves.

- Leave a cancellation unconfirmed when a browser session ends without that view, and say plainly that the payment may still be active.

## Get a choice before any sign in

- Present the verified billing channel and the two routes before asking for any credential, naming the agent in browser route and the user in app route with the steps and rough time for the user route.

- Ask for a sign in only after the user picks the agent route for that named account.

- Describe a login as pending until the account view is actually open, and never claim to be in an account while a sign in is still in progress.

- Stop, disclose what changed and ask again before touching a second account when the first channel is disproven.

- Warn the user away from prompts inside a billing account that would undo the goal, such as updating a payment method when the goal is to stop an automatic payment, and name that risk before they tap anything.

## Report the scope of the check

- Report each status claim with the surface checked, what that check actually showed and what it did not cover.

- Label the claim unverified when the authoritative surface is not accessible, and state what could not be checked.

- Never upgrade silence, absence of alerts or a failed check into a positive finding.

- State the correction plainly when a check overturns an earlier claim, fix the record and keep the corrected surface as the source going forward.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Offer the user the short self service route in the billing app when it is faster and safer than an agent sign in, and stay available to verify the result.

- Check a second independent fresh source when the first source is an aggregator that is known to lag, rather than repeating the same stale read.
