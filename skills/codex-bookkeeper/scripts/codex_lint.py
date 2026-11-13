#!/usr/bin/env python3
"""codex_lint.py — conformance checks for Quantum Codex notes.

Part of the `codex-bookkeeper` skill. Checks the rules that are mechanical, so
every bookkeeper agent applies them identically instead of by eye:

  F  frontmatter   present, parses, all 13 Commandment-2 fields, valid status,
                   date/time formats, key order, no second frontmatter block
  N  naming        banned filename characters, goal-note filename pattern
  G  goal notes    goal_id / codename / project / phase present, phase numeric
  L  links         bare [[OVERVIEW]]/[[ROADMAP]]/[[INDEX]]; broken WikiLinks (--links)
  A  archive       status Archived with no successor pointer

Secrets are NOT checked here — run Bookkeeping/tools/vault_secret_scan.py.

The vault is an rclone mount of Google Drive: uncached reads are slow and a
whole-vault walk can stall other readers for minutes. So paths are REQUIRED —
lint the folders you touched, not the world. --links builds a filename index
with `rclone lsf -R --fast-list` against the remote (~20 s for the whole vault),
falling back to walking the mount only if rclone is unavailable.

Usage:
  codex_lint.py PATH [PATH ...] [--vault /home/scott/codex] [--links [--remote codex:]]
                [--report FILE.md] [--strict]
Exit code: 0 clean or warnings only; 1 errors found and --strict given.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

REQUIRED = [
    "title", "author_agent", "agent_id", "last_edited_by", "date_created",
    "time_created", "last_updated", "time_updated", "status", "maintained_by",
    "version", "tags", "related_files",
]
STATUSES = {"Draft", "Active", "Pending Review", "Completed", "Archived"}
BANNED_FILENAME = re.compile(r'["\[\]|#^:\\*?<>]')
GOAL_FILENAME = re.compile(r"^[A-Z]{2,4}-\d{3} [A-Z0-9]+ — .+\.md$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^\d{2}:\d{2}:\d{2}$")
WIKILINK = re.compile(r"(?<!!)\[\[([^\]\n]+?)\]\]")
EMBED = re.compile(r"!\[\[([^\]\n]+?)\]\]")
BARE_PROJECT_DOC = re.compile(r"\[\[(OVERVIEW|ROADMAP|INDEX)(\|[^\]]*)?(#[^\]]*)?\]\]")
FENCE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")

# Folders never linted: frozen, tooling, machine output, or a different format.
SKIP_DIRS = {".obsidian", ".claude", ".git", "archive", "node_modules", "__pycache__", ".trash"}
SKIP_PREFIXES = ("Bookkeeping/logs", "Bookkeeping/reports", "_templates")
# Hermes-canonical files follow their own format (codex_structure §3 exemptions).
EXEMPT_NAMES = {"SOUL.md", "skill-manifest.md"}


class Finding:
    def __init__(self, level: str, code: str, path: str, msg: str):
        self.level, self.code, self.path, self.msg = level, code, path, msg

    def __str__(self) -> str:
        return f"{self.level:5} {self.code:3} {self.path} — {self.msg}"


def split_frontmatter(text: str):
    """Return (frontmatter_text, body, key_order) or (None, text, [])."""
    if not text.startswith("---"):
        return None, text, []
    end = text.find("\n---", 3)
    if end == -1:
        return None, text, []
    fm = text[3:end].strip("\n")
    body = text[end + 4:]
    order = [m.group(1) for m in re.finditer(r"^([A-Za-z_][\w-]*):", fm, re.M)]
    return fm, body, order


def rel(path: Path, vault: Path) -> str:
    try:
        return str(path.relative_to(vault))
    except ValueError:
        return str(path)


def iter_markdown(paths: list[Path], vault: Path):
    for p in paths:
        if p.is_file() and p.suffix == ".md":
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            r = rel(Path(root), vault)
            if r.startswith(SKIP_PREFIXES):
                dirs[:] = []
                continue
            for f in files:
                if f.endswith(".md"):
                    yield Path(root) / f


def _add(stems: set, relpaths: set, r: str) -> None:
    name = r.rsplit("/", 1)[-1]
    if name.endswith(".md"):
        stems.add(name[:-3])
        relpaths.add(r[:-3])
    else:
        stems.add(name)  # attachments are linked with their extension
        relpaths.add(r)


def build_index(vault: Path, remote: str | None, rclone_config: str | None):
    """Filenames (stem and relative path without .md) across the vault.

    Walking the rclone mount lists each directory through the FUSE layer and has
    stalled for minutes (measured 2026-09-23). `rclone lsf -R --fast-list` against
    the remote lists all ~1,600 files in ~20 s, so it is tried first.
    """
    stems, relpaths = set(), set()
    if remote:
        import subprocess
        cmd = ["rclone", "lsf", "-R", "--files-only", "--fast-list",
               "--exclude", "/.obsidian/**", "--exclude", "/.git/**", remote]
        if rclone_config:
            cmd += ["--config", rclone_config]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True).stdout
            for line in out.splitlines():
                if line.strip():
                    _add(stems, relpaths, line.strip())
            return stems, relpaths
        except Exception as e:  # fall back to walking the mount
            print(f"(rclone listing failed: {e}; walking the mount instead — slow)", file=sys.stderr)
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in {".obsidian", ".git", ".trash", "node_modules"}]
        for f in files:
            _add(stems, relpaths, rel(Path(root) / f, vault))
    return stems, relpaths


def link_target(raw: str) -> str:
    # Inside Markdown tables Obsidian aliases are written [[target\|alias]]; drop the escape.
    target = raw.split("|", 1)[0].split("#", 1)[0].strip().rstrip("\\").strip()
    return target[:-3] if target.endswith(".md") else target


def resolves(target: str, stems: set, relpaths: set) -> bool:
    if not target:
        return True  # [[#heading]] — same-note link
    if "/" in target:
        return target in relpaths or any(p.endswith("/" + target) for p in relpaths)
    return target in stems


def lint_file(path: Path, vault: Path, index) -> list[Finding]:
    out: list[Finding] = []
    r = rel(path, vault)
    name = path.name

    if BANNED_FILENAME.search(name):
        out.append(Finding("ERROR", "N1", r, "filename contains a banned character (\" [ ] | # ^ : \\ * ? < >)"))
    in_goals = path.parent.name == "goals"
    if in_goals and not GOAL_FILENAME.match(name):
        out.append(Finding("WARN", "N2", r, "goal filename should be 'ABBR-NNN CODENAME — Short Name.md'"))

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:  # unreadable (e.g. 0-byte gdoc shortcut)
        return out + [Finding("ERROR", "F0", r, f"unreadable: {e}")]
    if not text.strip():
        return out + [Finding("WARN", "F0", r, "empty file")]

    exempt = name in EXEMPT_NAMES or r.startswith("Skills/")
    fm_text, body, order = split_frontmatter(text)

    if r.startswith("Skills/") and name == "SKILL.md":
        # Skills use name/description frontmatter, not Commandment 2.
        try:
            meta = yaml.safe_load(fm_text or "") or {}
            if not meta.get("name") or not meta.get("description"):
                out.append(Finding("ERROR", "S1", r, "skill frontmatter needs name and description"))
            elif meta["name"] != path.parent.name:
                out.append(Finding("ERROR", "S2", r, f"skill name '{meta['name']}' != folder '{path.parent.name}'"))
        except yaml.YAMLError as e:
            out.append(Finding("ERROR", "S0", r, f"skill frontmatter does not parse — it will silently not load ({str(e).splitlines()[0]})"))
        return out

    if not exempt:
        if fm_text is None:
            out.append(Finding("ERROR", "F1", r, "no YAML frontmatter"))
        else:
            try:
                meta = yaml.safe_load(fm_text) or {}
            except yaml.YAMLError as e:
                meta = None
                out.append(Finding("ERROR", "F2", r, f"frontmatter does not parse: {str(e).splitlines()[0]}"))
            if isinstance(meta, dict):
                missing = [k for k in REQUIRED if k not in meta]
                if missing:
                    out.append(Finding("ERROR", "F3", r, f"missing fields: {', '.join(missing)}"))
                status = meta.get("status")
                if status is not None and status not in STATUSES:
                    out.append(Finding("ERROR", "F4", r, f"status '{status}' not one of {sorted(STATUSES)}"))
                for k in ("date_created", "last_updated"):
                    v = meta.get(k)
                    if v is not None and not DATE.match(str(v)):
                        out.append(Finding("WARN", "F5", r, f"{k} '{v}' is not YYYY-MM-DD"))
                for k in ("time_created", "time_updated"):
                    v = meta.get(k)
                    if v is not None and not TIME.match(str(v)):
                        out.append(Finding("WARN", "F5", r, f"{k} '{v}' is not HH:MM:SS (quote it — YAML reads bare 10:30:00 as a number)"))
                present = [k for k in order if k in REQUIRED]
                if present != [k for k in REQUIRED if k in present]:
                    out.append(Finding("WARN", "F6", r, "Commandment-2 keys out of canonical order (type keys go between version and tags)"))
                if in_goals or meta.get("goal_id"):
                    gm = [k for k in ("goal_id", "codename", "project", "phase") if k not in meta]
                    if gm:
                        out.append(Finding("ERROR", "G1", r, f"goal note missing: {', '.join(gm)}"))
                    ph = meta.get("phase")
                    if ph is not None and not re.fullmatch(r"\d+", str(ph)):
                        out.append(Finding("ERROR", "G2", r, f"phase must be the phase NUMBER as a string, got '{ph}'"))
                if status == "Archived":
                    rf = meta.get("related_files") or []
                    if not rf and not re.search(r"supersed|successor|replaced by", body, re.I):
                        out.append(Finding("ERROR", "A1", r, "Archived with no successor pointer"))
            if re.match(r"\s*---\s*\n\s*title:", body):
                out.append(Finding("ERROR", "F7", r, "a second frontmatter block follows the first (template bug)"))

    scan = INLINE_CODE.sub("", FENCE.sub("", body if fm_text is not None else text))
    for m in BARE_PROJECT_DOC.finditer(scan):
        out.append(Finding("ERROR", "L1", r, f"bare [[{m.group(1)}]] — path-qualify it: [[projects/<Project>/{m.group(1)}]]"))

    if index is not None:
        stems, relpaths = index
        seen = set()
        for m in list(WIKILINK.finditer(scan)) + list(EMBED.finditer(scan)):
            t = link_target(m.group(1))
            if t in seen:
                continue
            seen.add(t)
            if "<" in t or "{" in t:
                continue  # placeholder inside prose
            if not resolves(t, stems, relpaths):
                out.append(Finding("WARN", "L2", r, f"link target not found: [[{t}]]"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--vault", type=Path, default=Path("/home/scott/codex"))
    ap.add_argument("--links", action="store_true", help="also check WikiLinks resolve (lists the whole vault)")
    ap.add_argument("--remote", default="codex:", help="rclone remote for the fast listing used by --links ('' to walk the mount)")
    ap.add_argument("--rclone-config", default=str(Path.home() / ".config/rclone/rclone.conf"))
    ap.add_argument("--report", type=Path, help="write a Markdown report here as well")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any ERROR")
    a = ap.parse_args(argv)

    vault = a.vault.resolve()
    paths = [(p if p.is_absolute() else vault / p).resolve() for p in a.paths]
    cfg = a.rclone_config if Path(a.rclone_config).exists() else None
    index = build_index(vault, a.remote or None, cfg) if a.links else None

    findings, files = [], 0
    for f in iter_markdown(paths, vault):
        files += 1
        findings.extend(lint_file(f, vault, index))

    errors = sum(1 for f in findings if f.level == "ERROR")
    warns = len(findings) - errors
    for f in findings:
        print(f)
    print(f"\n{files} files · {errors} errors · {warns} warnings")

    if a.report:
        lines = ["| level | code | file | finding |", "|---|---|---|---|"]
        lines += [f"| {f.level} | {f.code} | `{f.path}` | {f.msg.replace('|', '/')} |" for f in findings]
        a.report.write_text(
            f"{files} files checked · **{errors} errors** · {warns} warnings\n\n" + "\n".join(lines) + "\n",
            encoding="utf-8",
        )
    return 1 if (a.strict and errors) else 0


if __name__ == "__main__":
    sys.exit(main())
