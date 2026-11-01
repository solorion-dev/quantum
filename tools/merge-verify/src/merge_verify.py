#!/usr/bin/env python3
"""merge-verify — verify that a merged tree actually runs.

Implements the fleet rule (Oct 26, 2026): "A merge is not verified
until the merged tree runs — a green PR diff does not prove the
merged tip works: after any merge, exercise the merged tree itself
(typecheck/build/tests + smoke run) before calling the branch done."

Born from the Oct 25, 2026 Eidolon bad merge (PR #7 lineage dropped
declarations while keeping their uses -> 25 typecheck errors, two
crashing pages, all invisible in the diff).

Stdlib only, Python 3.10+. Read-only with respect to the repo:
no checkout, no fetch, no writes. Only read-only git commands are
used (rev-parse, status, merge-base). Check commands are argv
arrays from the config file — never shell strings.

v2 (Nov 1, 2026): package.json auto-discovery — when no config
file is present (and no explicit --config was given), derive a
default check set from package.json scripts (typecheck, test,
build, in that order) and say so in the report (config_source=
"package.json"). A real config file still wins when present.
--no-auto-discover restores the strict v1 behaviour. If no
checks can be discovered, the verdict is INCOMPLETE, never
VERIFIED.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

VERDICT_VERIFIED = "VERIFIED"
VERDICT_FAILED = "FAILED"
VERDICT_INCOMPLETE = "INCOMPLETE"

EXIT_VERIFIED = 0
EXIT_FAILED = 1
EXIT_INCOMPLETE = 2

VERDICT_EXIT = {
    VERDICT_VERIFIED: EXIT_VERIFIED,
    VERDICT_FAILED: EXIT_FAILED,
    VERDICT_INCOMPLETE: EXIT_INCOMPLETE,
}

DEFAULT_TIMEOUT_S = 600
TAIL_LINES = 40
TAIL_CHARS = 4000

# v2 auto-discovery: candidate package.json scripts, in fixed order.
CANDIDATE_SCRIPTS = ["typecheck", "test", "build"]

# Lockfile -> package manager, in priority order (first match wins).
LOCKFILE_PACKAGE_MANAGERS = [
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
    ("npm-shrinkwrap.json", "npm"),
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
]


def _tail(output: str) -> str:
    """Last 40 lines / ~4000 chars of combined output."""
    if not output:
        return ""
    lines = output.splitlines()
    tail = "\n".join(lines[-TAIL_LINES:])
    if len(tail) > TAIL_CHARS:
        tail = tail[-TAIL_CHARS:]
    return tail


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        errors="replace",
    )


def _sha_matches(head: str, expect: str) -> bool:
    """Full SHA or unique prefix >= 7 chars."""
    expect = expect.strip()
    if len(expect) < 7:
        return False
    return head.startswith(expect)


def _detect_package_manager(repo: Path, package_data: dict) -> str:
    """Package manager for discovered checks.

    A lockfile in the repo root wins (see LOCKFILE_PACKAGE_MANAGERS
    priority order). Else the package.json "packageManager" field
    (name before "@"). Else npm.
    """
    for lockfile, pm in LOCKFILE_PACKAGE_MANAGERS:
        if (repo / lockfile).exists():
            return pm
    pm_field = package_data.get("packageManager")
    if isinstance(pm_field, str) and pm_field.strip():
        name = pm_field.strip().split("@", 1)[0].strip()
        if name:
            return name
    return "npm"


def _discover_checks(repo: Path):
    """Derive a check set from <repo>/package.json.

    Returns (checks_cfg, discovered, error). On success error is
    None, checks_cfg is a list of {"name", "command"} dicts (argv
    arrays, default timeout) and discovered is the list of script
    names in CANDIDATE_SCRIPTS order. On failure checks_cfg is
    None and error names that no config was found and no checks
    could be discovered.
    """
    prefix = (
        "no config was found (no merge-verify.json) and no checks "
        "could be discovered from package.json"
    )
    pkg_path = repo / "package.json"
    if not pkg_path.exists():
        return None, [], f"{prefix}: package.json not found at {pkg_path}"
    try:
        raw = pkg_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as exc:
        return None, [], f"{prefix}: package.json does not parse: {pkg_path}: {exc}"
    if not isinstance(data, dict):
        return None, [], f"{prefix}: package.json is not a JSON object: {pkg_path}"
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        scripts = {}
    discovered: list[str] = []
    for name in CANDIDATE_SCRIPTS:
        value = scripts.get(name)
        if isinstance(value, str) and value.strip() != "":
            discovered.append(name)
    if not discovered:
        return None, [], (
            f"{prefix}: package.json has no candidate scripts "
            f"({'/'.join(CANDIDATE_SCRIPTS)}) at {pkg_path}"
        )
    pm = _detect_package_manager(repo, data)
    checks_cfg = [
        {"name": name, "command": [pm, "run", name]} for name in discovered
    ]
    return checks_cfg, discovered, None


def run_verification(
    repo_arg: str,
    config_arg: str | None,
    expect_head: str | None,
    expect_ancestor: str | None,
    auto_discover: bool = True,
) -> dict:
    errors: list[str] = []
    checks_results: list[dict] = []
    head: str | None = None
    expect_head_ok: bool | None = None
    expect_ancestor_ok: bool | None = None
    tree_clean_before: bool | None = None
    tree_clean_after: bool | None = None

    repo = Path(repo_arg).expanduser()

    # --- 1. Validation -------------------------------------------------
    validation_failed = False

    if not repo.exists() or not repo.is_dir():
        errors.append(f"repo does not exist or is not a directory: {repo}")
        validation_failed = True
        repo_resolved = str(repo)
        return _finish(
            verdict=VERDICT_INCOMPLETE,
            repo=repo_resolved,
            head=None,
            expect_head_ok=None,
            expect_ancestor_ok=None,
            tree_clean_before=None,
            tree_clean_after=None,
            checks=[],
            errors=errors,
        )

    repo_resolved = str(repo.resolve()) if repo.exists() else str(repo)

    # Is it a git work tree?
    is_git = False
    if not validation_failed:
        try:
            r = _git(repo, "rev-parse", "--is-inside-work-tree")
            is_git = r.returncode == 0 and r.stdout.strip() == "true"
        except FileNotFoundError:
            errors.append("git executable not found")
            validation_failed = True
        if not is_git and not validation_failed:
            errors.append(f"repo is not a git work tree: {repo}")
            validation_failed = True

    # Config
    config_path: Path | None = None
    config: dict | None = None
    require_clean = True
    checks_cfg: list = []
    config_source: str | None = None
    discovered: list[str] = []

    if not validation_failed:
        explicit_config = bool(config_arg)
        if explicit_config:
            cp = Path(config_arg).expanduser()
            if not cp.is_absolute():
                cp = (Path.cwd() / cp)
            config_path = cp
        else:
            config_path = repo / "merge-verify.json"

        if not config_path.exists():
            if explicit_config or not auto_discover:
                # v1 behaviour: explicit --config, or discovery
                # disabled via --no-auto-discover — a missing
                # config is INCOMPLETE, never a discovery attempt
                # for an explicit path.
                errors.append(f"config not found: {config_path}")
                validation_failed = True
            else:
                # v2: no config file — try package.json discovery.
                disc_checks, disc_names, disc_error = _discover_checks(repo)
                if disc_error is not None:
                    errors.append(disc_error)
                    validation_failed = True
                else:
                    checks_cfg = disc_checks
                    discovered = disc_names
                    config_source = "package.json"
                    # Discovered checks always require a clean tree.
                    require_clean = True
        else:
            config_source = "file"
            try:
                raw = config_path.read_text(encoding="utf-8")
                config = json.loads(raw)
            except Exception as exc:  # JSON parse or read error
                errors.append(f"config does not parse: {config_path}: {exc}")
                validation_failed = True
                config = None

            if config is not None:
                if not isinstance(config, dict):
                    errors.append("config must be a JSON object")
                    validation_failed = True
                else:
                    require_clean = bool(config.get("require_clean", True))
                    checks_cfg = config.get("checks")
                    if not isinstance(checks_cfg, list) or len(checks_cfg) == 0:
                        errors.append("config checks list is missing or empty")
                        validation_failed = True
                        checks_cfg = []
                    else:
                        # Validate each check entry shape
                        for idx, chk in enumerate(checks_cfg):
                            if not isinstance(chk, dict):
                                errors.append(f"check #{idx} is not an object")
                                validation_failed = True
                                continue
                            if not chk.get("name") or not isinstance(chk.get("name"), str):
                                errors.append(f"check #{idx} missing string 'name'")
                                validation_failed = True
                            cmd = chk.get("command")
                            if not isinstance(cmd, list) or len(cmd) == 0 or not all(isinstance(x, str) for x in cmd):
                                errors.append(f"check #{idx} ({chk.get('name')!r}) missing non-empty argv 'command' list")
                                validation_failed = True

    if validation_failed:
        # Still try to record HEAD if possible for the report
        if is_git:
            try:
                r = _git(repo, "rev-parse", "HEAD")
                if r.returncode == 0:
                    head = r.stdout.strip()
            except Exception:
                pass
        return _finish(
            verdict=VERDICT_INCOMPLETE,
            repo=repo_resolved,
            head=head,
            expect_head_ok=None,
            expect_ancestor_ok=None,
            tree_clean_before=None,
            tree_clean_after=None,
            checks=[],
            errors=errors,
            config_source=config_source,
            discovered=discovered,
        )

    # --- 2. HEAD / identity checks ------------------------------------
    try:
        r = _git(repo, "rev-parse", "HEAD")
        if r.returncode != 0:
            errors.append(f"git rev-parse HEAD failed: {_tail(r.stderr + r.stdout)}")
            return _finish(
                verdict=VERDICT_INCOMPLETE,
                repo=repo_resolved,
                head=None,
                expect_head_ok=None,
                expect_ancestor_ok=None,
                tree_clean_before=None,
                tree_clean_after=None,
                checks=[],
                errors=errors,
                config_source=config_source,
                discovered=discovered,
            )
        head = r.stdout.strip()
    except FileNotFoundError:
        errors.append("git executable not found")
        return _finish(
            verdict=VERDICT_INCOMPLETE,
            repo=repo_resolved,
            head=None,
            expect_head_ok=None,
            expect_ancestor_ok=None,
            tree_clean_before=None,
            tree_clean_after=None,
            checks=[],
            errors=errors,
            config_source=config_source,
            discovered=discovered,
        )

    has_identity_failure = False

    if expect_head is not None:
        if _sha_matches(head, expect_head):
            expect_head_ok = True
        else:
            # Also handle prefix <7 as failure per spec (allow full or >=7)
            expect_head_ok = False
            has_identity_failure = True
            errors.append(f"expect-head mismatch: HEAD is {head}, expected {expect_head}")

    if expect_ancestor is not None:
        # git merge-base --is-ancestor <sha> HEAD ; exit 0 = ancestor, 1 = not, other = error
        try:
            r = _git(repo, "merge-base", "--is-ancestor", expect_ancestor, "HEAD")
            if r.returncode == 0:
                expect_ancestor_ok = True
            elif r.returncode == 1:
                expect_ancestor_ok = False
                has_identity_failure = True
                errors.append(f"expect-ancestor not ancestor: {expect_ancestor} is not an ancestor of HEAD {head}")
            else:
                # e.g. unknown object -> treat as FAILED per spec wording
                # ("merge-base --is-ancestor fails = FAILED")
                expect_ancestor_ok = False
                has_identity_failure = True
                msg = _tail((r.stderr or "") + (r.stdout or ""))
                errors.append(f"expect-ancestor check failed: {expect_ancestor} is not an ancestor of HEAD {head}" + (f": {msg}" if msg else ""))
        except FileNotFoundError:
            expect_ancestor_ok = False
            has_identity_failure = True
            errors.append("git executable not found for merge-base check")

    # --- 3. Clean tree before -----------------------------------------
    dirty_before = False
    if require_clean:
        try:
            r = _git(repo, "status", "--porcelain")
            if r.returncode != 0:
                errors.append(f"git status failed: {_tail(r.stderr)}")
                dirty_before = True  # cannot prove clean -> INCOMPLETE path
                tree_clean_before = None
            else:
                porcelain = r.stdout
                tree_clean_before = (porcelain.strip() == "")
                if not tree_clean_before:
                    dirty_before = True
                    errors.append("tree_dirty_before: working tree is not clean before checks (git status --porcelain non-empty)")
        except FileNotFoundError:
            errors.append("git executable not found for status check")
            dirty_before = True
    else:
        # Still record for report if possible, but don't gate
        try:
            r = _git(repo, "status", "--porcelain")
            if r.returncode == 0:
                tree_clean_before = (r.stdout.strip() == "")
        except Exception:
            tree_clean_before = None

    if dirty_before and require_clean:
        # No verdict on checks — tree is not pristine. Checks are not run.
        # Precedence: if identity already FAILED, FAILED wins only per
        # documented rule? Spec precedence focuses on checks. For
        # simplicity and documentation: identity failure is a FAILED
        # condition that was actually verified, so it yields FAILED;
        # otherwise dirty-before alone is INCOMPLETE.
        verdict = VERDICT_FAILED if has_identity_failure else VERDICT_INCOMPLETE
        return _finish(
            verdict=verdict,
            repo=repo_resolved,
            head=head,
            expect_head_ok=expect_head_ok,
            expect_ancestor_ok=expect_ancestor_ok,
            tree_clean_before=tree_clean_before,
            tree_clean_after=None,
            checks=[],
            errors=errors,
            config_source=config_source,
            discovered=discovered,
        )

    # --- 4. Run ALL checks sequentially --------------------------------
    has_failed_check = False
    has_incomplete_check = False

    for chk in checks_cfg:
        name = chk.get("name")
        command = chk.get("command")
        timeout_s = chk.get("timeout_s", DEFAULT_TIMEOUT_S)
        try:
            timeout_s = int(timeout_s)
            if timeout_s <= 0:
                timeout_s = DEFAULT_TIMEOUT_S
        except Exception:
            timeout_s = DEFAULT_TIMEOUT_S

        cwd_rel = chk.get("cwd")
        if cwd_rel:
            cwd_path = (repo / cwd_rel).resolve() if not Path(cwd_rel).is_absolute() else Path(cwd_rel)
            # Keep inside repo conceptually; if subdir missing, subprocess will fail -> incomplete
            cwd_str = str(cwd_path)
        else:
            cwd_path = repo
            cwd_str = str(repo)

        start = time.monotonic()
        timed_out = False
        exit_code = None
        tail = ""

        try:
            proc = subprocess.run(
                command,
                cwd=cwd_str,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout_s,
            )
            duration = time.monotonic() - start
            exit_code = proc.returncode
            combined = (proc.stdout or "") + (proc.stderr or "")
            tail = _tail(combined)
            if exit_code != 0:
                has_failed_check = True
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            timed_out = True
            exit_code = None
            has_incomplete_check = True
            # Partial output may be bytes or str
            out = ""
            if exc.stdout:
                out += exc.stdout.decode(errors="replace") if isinstance(exc.stdout, (bytes, bytearray)) else str(exc.stdout)
            if exc.stderr:
                out += exc.stderr.decode(errors="replace") if isinstance(exc.stderr, (bytes, bytearray)) else str(exc.stderr)
            if exc.output:
                # output alias for stdout in some versions; avoid duplication if same
                pass
            tail = _tail(out) if out else ""
            errors.append(f"check '{name}' timed out after {timeout_s}s")
        except FileNotFoundError as exc:
            duration = time.monotonic() - start
            exit_code = None
            timed_out = False
            has_incomplete_check = True
            tail = _tail(str(exc))
            errors.append(f"check '{name}' executable missing: {command[0] if command else ''}: {exc}")
        except OSError as exc:
            # e.g. cwd does not exist, permission, etc. — check never ran to a result
            duration = time.monotonic() - start
            exit_code = None
            timed_out = False
            has_incomplete_check = True
            tail = _tail(str(exc))
            errors.append(f"check '{name}' could not run: {exc}")

        checks_results.append({
            "name": name,
            "exit_code": exit_code,
            "duration_s": round(duration, 3),
            "timed_out": timed_out,
            "tail": tail,
        })

    # --- 6. Clean tree after ------------------------------------------
    tree_dirty_after = False
    if require_clean:
        try:
            r = _git(repo, "status", "--porcelain")
            if r.returncode == 0:
                tree_clean_after = (r.stdout.strip() == "")
                if tree_clean_before and not tree_clean_after:
                    tree_dirty_after = True
                    errors.append("tree_dirty_after: working tree became dirty during checks (verification polluted the tree)")
            else:
                tree_clean_after = None
                errors.append(f"git status after checks failed: {_tail(r.stderr)}")
                has_incomplete_check = True
        except FileNotFoundError:
            tree_clean_after = None
            has_incomplete_check = True
            errors.append("git executable not found for post-check status")
    else:
        try:
            r = _git(repo, "status", "--porcelain")
            if r.returncode == 0:
                tree_clean_after = (r.stdout.strip() == "")
        except Exception:
            tree_clean_after = None

    # --- 7. Verdict / precedence ---------------------------------------
    # FAILED conditions: a check exited non-zero, an identity check
    # failed, or the tree became dirty during checks.
    # INCOMPLETE conditions: a check timed out or its executable was
    # missing (it never ran to a result).
    #
    # Precedence (documented in README): if both kinds occur, FAILED
    # wins only if at least one check actually ran and failed.
    # Timeouts / missing executables with no failing check = INCOMPLETE.
    # Identity failures and tree_dirty_after are verified FAILED
    # conditions in their own right, so they also yield FAILED even
    # without a failing check (they were actually observed, not missing).
    has_failed_condition = has_failed_check or has_identity_failure or tree_dirty_after
    has_incomplete_condition = has_incomplete_check

    if has_failed_condition and has_incomplete_condition:
        if has_failed_check or has_identity_failure or tree_dirty_after:
            verdict = VERDICT_FAILED
        else:
            verdict = VERDICT_INCOMPLETE
    elif has_failed_condition:
        verdict = VERDICT_FAILED
    elif has_incomplete_condition:
        verdict = VERDICT_INCOMPLETE
    else:
        verdict = VERDICT_VERIFIED

    return _finish(
        verdict=verdict,
        repo=repo_resolved,
        head=head,
        expect_head_ok=expect_head_ok,
        expect_ancestor_ok=expect_ancestor_ok,
        tree_clean_before=tree_clean_before,
        tree_clean_after=tree_clean_after,
        checks=checks_results,
        errors=errors,
        config_source=config_source,
        discovered=discovered,
    )


def _finish(*, verdict, repo, head, expect_head_ok, expect_ancestor_ok, tree_clean_before, tree_clean_after, checks, errors, config_source=None, discovered=None) -> dict:
    return {
        "verdict": verdict,
        "exit_code": VERDICT_EXIT[verdict],
        "repo": repo,
        "head": head,
        "expect_head_ok": expect_head_ok,
        "expect_ancestor_ok": expect_ancestor_ok,
        "tree_clean_before": tree_clean_before,
        "tree_clean_after": tree_clean_after,
        "checks": checks,
        "errors": errors,
        "config_source": config_source,
        "discovered": list(discovered) if discovered else [],
    }


def _print_human(result: dict) -> None:
    print(f"merge-verify: {result['verdict']}")
    if result.get("config_source") == "package.json":
        scripts = ", ".join(result.get("discovered") or [])
        print(f"config: derived from package.json (scripts: {scripts})")
    elif result.get("config_source") == "file":
        print("config: file")
    print(f"  repo: {result['repo']}")
    print(f"  head: {result['head']}")
    if result.get("expect_head_ok") is not None:
        print(f"  expect_head_ok: {result['expect_head_ok']}")
    if result.get("expect_ancestor_ok") is not None:
        print(f"  expect_ancestor_ok: {result['expect_ancestor_ok']}")
    print(f"  tree_clean_before: {result['tree_clean_before']}")
    print(f"  tree_clean_after: {result['tree_clean_after']}")
    if result["checks"]:
        print("  checks:")
        for chk in result["checks"]:
            if chk["timed_out"]:
                status = "TIMEOUT"
            elif chk["exit_code"] is None:
                status = "MISSING/ERROR"
            elif chk["exit_code"] == 0:
                status = "ok"
            else:
                status = f"exit {chk['exit_code']}"
            print(f"    - {chk['name']}: {status} ({chk['duration_s']}s)")
            # Tails for failures / timeouts / missing
            if chk["exit_code"] not in (0,) or chk["timed_out"]:
                # Show tail for non-zero, timeout, missing
                if chk.get("tail"):
                    print("      tail:")
                    for line in chk["tail"].splitlines():
                        print(f"        {line}")
    if result["errors"]:
        print("  errors:")
        for e in result["errors"]:
            print(f"    - {e}")
    print(f"  exit: {result['exit_code']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="merge-verify", description="Verify that a merged tree actually runs.")
    parser.add_argument("--repo", required=True, help="Path to git work tree to verify")
    parser.add_argument("--config", default=None, help="Path to config JSON (default: <repo>/merge-verify.json)")
    parser.add_argument("--expect-head", default=None, help="Expected HEAD SHA (full or unique prefix >=7 chars)")
    parser.add_argument("--expect-ancestor", default=None, help="SHA that must be an ancestor of HEAD")
    parser.add_argument("--no-auto-discover", action="store_true", help="Disable package.json auto-discovery (strict v1 behaviour: no config = INCOMPLETE)")
    parser.add_argument("--json", action="store_true", help="Emit one JSON object")
    args = parser.parse_args(argv)

    result = run_verification(
        repo_arg=args.repo,
        config_arg=args.config,
        expect_head=args.expect_head,
        expect_ancestor=args.expect_ancestor,
        auto_discover=not args.no_auto_discover,
    )

    if args.json:
        print(json.dumps(result))
    else:
        _print_human(result)

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
