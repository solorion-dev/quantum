---
name: credential-vault-verification
version: 1.0.0
description: "Save credentials to the intended vault, organization and collection and verify visibility, username and live login before reporting them saved, including accounts Muse creates itself."
tags: [quantum]
status: active
provenance: quantum
aliases: [local_credential_vault_verification, local-credential-vault-verification]
dependencies:
  tools: []
  repos: []
  urls: []
maintainers: [cooper]
---
# Credential Vault Save and Verify

## Choose the destination before saving

- Name the exact destination before saving any credential, covering the vault, the organization or personal vault, and the collection the intended user or agent will actually look in.

- Treat a save into a personal vault as a different outcome from a save into a shared organization, and say which one you chose and why before you save.

- Check the existing entry for the same service first with a list or search of the destination collection, so a correction lands on the entry people already use instead of a second copy elsewhere.

## Save at creation time

- Vault the credential in the same work session whenever you create an account, reset a password, or receive a new login, before moving on to using the account.

- Record the username exactly as the service uses it for login, copied from the account or the successful sign in, never from memory or from a display name.

- Keep the secret value out of chat, memory, files and logs, and refer to it only by the vault entry name and its location.

## Verify from the recipient view

- Re-read the saved entry from the destination organization and collection after saving, and confirm it is visible there, not only in the vault view you saved from.

- Confirm the entry name, username field and collection match what the intended recipient will search for, and fix a mismatch before reporting the save.

- Report a credential as saved only after that re-read, and name the organization and collection in the report so the user can find it on the first try.

## Verify the login where it is safe

- Test the credential with a real sign in to the service when a harmless login check exists, and treat a failed login as the save not being done yet.

- Compare the username that worked in the live login against the username stored in the entry, character for character, and correct the entry when they differ.

- Stop and report the gap when no safe login check exists, naming what was verified by re-read and what remains untested.

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Alternatives for better results

- Ask the user which organization or collection they expect before saving when two plausible destinations exist, because moving an entry later costs more than one question now.

- Verify an older entry the same way when a login suddenly fails, since a stale username or a move between collections produces the same symptoms as a wrong password.
