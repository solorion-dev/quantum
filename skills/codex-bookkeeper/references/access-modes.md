# Access modes: how to reach the Codex, and the traps in each

## 1. Filesystem: Tritium's rclone mount (preferred)

`/home/scott/codex`, a live read/write rclone mount of the vault (systemd unit `rclone-codex`). Use
ordinary file tools: read, write, `mv`, `rm`. Changes reach Drive within seconds to minutes.

- **Deletes go to Google Drive's trash** (recoverable for 30 days). That is still not an undo:
  archive instead.
- **Uncached reads are slow.** Never `find`/`grep -r` the whole vault; a single whole-vault walk
  has stalled every other reader for over two minutes. List specific folders, and pass the linter
  specific paths. Wrap exploratory commands in `timeout`.
- If `mountpoint /home/scott/codex` fails, restart the unit. Do not fall back to the Drive connector.
- `.obsidian/plugins/*/data.json` are live plugin configs that sync to Scott's devices. Edit them only
  deliberately, validate the JSON, and never leave a token in one (a Notion token was found in
  cleartext on 2026-09-22).

## 2. Google Drive connector (MCP / API): agents off Tritium (Gemini, Grok, Harbor)

- The real vault is folder `1U5p03fRWPjbx2VtaBCaoL186ZdXthanf`. A nearly empty folder with the same
  name is nested inside it (`1uOutqcHeGhWhG8qrRFrDmIwgYAU-Ilmc`). Confirm the folder contains
  `Quantum Codex Master Index.md` before writing.
- `read_file_content` can return **nothing** for `text/markdown`. Use `download_file_content` and
  base64-decode.
- The connector **cannot update file content**. To edit: create the new version with the same name
  in the same folder, then trash the old file id. Never leave both.
- Create files as `text/markdown` with conversion to Google Docs **disabled**, or Drive silently
  turns them into Docs (breaks Commandment 1).
- You cannot run `codex_lint.py`. Apply its rules by reading (they are listed in its docstring and
  in SKILL.md §2B).

## 3. Obsidian only: a human-driven or in-app agent

- Create notes with Templater (`Ctrl/Cmd-P` → *Templater: Create new note from template*). The
  templates fill identity and timestamps.
- The **Linter** plugin stamps `last_updated`/`time_updated` on save, and ignores `archive/`,
  `_templates/`, `Quantum Agents/` and machine-output folders.
- Obsidian's rename (right-click → Rename) **updates inbound links automatically**. It is the
  safest way to fix a banned filename. Renaming on the filesystem or in Drive does not.
- Dataview and Tasks blocks render only in Obsidian. In raw Markdown they look like code blocks; leave them intact.
