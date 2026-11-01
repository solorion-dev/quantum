"""Tests for merge-verify.

Creates real temp git repos with `git init`, per-repo user config,
commits and a real merge. Runs the tool as a subprocess so exit
codes and --json output are exercised exactly as in the field.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = TOOL_DIR / "src" / "merge_verify.py"


# ---------------------------------------------------------------- helpers

def git(repo: Path, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stdout} {result.stderr}")
    return result


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    # -b main requires git >= 2.28; environment has 2.43
    result = subprocess.run(
        ["git", "init", "-b", "main", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # fallback for older git
        subprocess.run(["git", "init", str(path)], capture_output=True, text=True, check=True)
        git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Merge Verify Test")
    git(path, "config", "commit.gpgsign", "false")
    return path


def write(repo: Path, rel: str, content: str):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def write_config(repo: Path, checks, require_clean=True, name="merge-verify.json"):
    cfg = {"require_clean": require_clean, "checks": checks}
    (repo / name).write_text(json.dumps(cfg), encoding="utf-8")
    return repo / name


def ok_check(name="ok"):
    return {"name": name, "command": [sys.executable, "-c", "print('ok')"]}


def run_tool(repo: Path, *extra, use_json=True):
    cmd = [sys.executable, str(SCRIPT), "--repo", str(repo)]
    if use_json:
        cmd.append("--json")
    cmd.extend(extra)
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = None
    if use_json and result.stdout.strip():
        try:
            data = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception:
            data = None
    return result, data


def make_simple_repo(tmp_path: Path) -> Path:
    """Repo with one commit and a passing config committed? No —
    config must be present but committing it would be clean; leaving
    it untracked would make the tree dirty. So tests commit the
    config file as part of the repo where a clean tree is needed.
    This helper creates repo + initial file, caller adds config
    then commits everything together via commit_all.
    """
    repo = init_repo(tmp_path / "repo")
    write(repo, "hello.txt", "hello\n")
    return repo


# ---------------------------------------------------------------- tests

def test_good_merge_verified(tmp_path):
    repo = make_simple_repo(tmp_path)
    commit_all(repo, "initial")
    # branch adds a file, main adds another, then merge
    git(repo, "checkout", "-b", "feature")
    write(repo, "feature.txt", "feature\n")
    commit_all(repo, "feature")
    git(repo, "checkout", "main")
    write(repo, "main2.txt", "main2\n")
    # config committed on main before merge so merged tree is clean
    write_config(repo, [ok_check("smoke")])
    commit_all(repo, "main work + config")
    # real merge
    result = subprocess.run(["git", "-C", str(repo), "merge", "--no-ff", "feature", "-m", "merge feature"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (repo / "feature.txt").exists()

    proc, data = run_tool(repo)
    assert data is not None, proc.stdout + proc.stderr
    assert data["verdict"] == "VERIFIED"
    assert proc.returncode == 0
    assert data["exit_code"] == 0


def test_bad_merge_shape_failed(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write(repo, "mod.py", "def foo():\n    return 42\n")
    write(repo, "main.py", "from mod import foo\nprint(foo())\n")
    write_config(repo, [{"name": "run-main", "command": [sys.executable, "main.py"]}])
    commit_all(repo, "initial: foo defined and used")

    # branch removes foo while keeping its use in main.py
    git(repo, "checkout", "-b", "bad-remove")
    write(repo, "mod.py", "def bar():\n    return 1\n")
    commit_all(repo, "remove foo")
    git(repo, "checkout", "main")
    write(repo, "other.txt", "diverge\n")
    commit_all(repo, "diverge main")
    result = subprocess.run(["git", "-C", str(repo), "merge", "--no-ff", "bad-remove", "-m", "merge bad"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    # merged tree: mod.py has no foo, main.py still uses it
    assert "foo" not in (repo / "mod.py").read_text() or "def foo" not in (repo / "mod.py").read_text()

    proc, data = run_tool(repo)
    assert data is not None, proc.stdout + proc.stderr
    assert data["verdict"] == "FAILED"
    assert proc.returncode == 1
    failing = [c for c in data["checks"] if c["exit_code"] not in (0, None)]
    assert failing, data
    assert failing[0]["name"] == "run-main"
    assert "foo" in failing[0]["tail"] or "ImportError" in failing[0]["tail"]


def test_expect_head_match_ok(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [ok_check()])
    head = commit_all(repo, "initial")
    proc, data = run_tool(repo, "--expect-head", head)
    assert data["verdict"] == "VERIFIED"
    assert data["expect_head_ok"] is True
    assert proc.returncode == 0
    # prefix form also works
    proc2, data2 = run_tool(repo, "--expect-head", head[:7])
    assert data2["expect_head_ok"] is True
    assert data2["verdict"] == "VERIFIED"


def test_expect_head_mismatch_failed(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [ok_check()])
    commit_all(repo, "initial")
    fake = "0" * 40
    proc, data = run_tool(repo, "--expect-head", fake)
    assert data["verdict"] == "FAILED"
    assert data["expect_head_ok"] is False
    assert proc.returncode == 1


def test_expect_ancestor_is_ancestor_ok(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [ok_check()])
    first = commit_all(repo, "first")
    write(repo, "second.txt", "2\n")
    commit_all(repo, "second")
    proc, data = run_tool(repo, "--expect-ancestor", first)
    assert data["verdict"] == "VERIFIED"
    assert data["expect_ancestor_ok"] is True
    assert proc.returncode == 0


def test_expect_ancestor_not_ancestor_failed(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [ok_check()])
    commit_all(repo, "first")
    # create an orphan / unrelated commit sha via a separate repo
    other = init_repo(tmp_path / "other")
    write(other, "x.txt", "x\n")
    unrelated = commit_all(other, "unrelated")
    proc, data = run_tool(repo, "--expect-ancestor", unrelated)
    assert data["verdict"] == "FAILED"
    assert data["expect_ancestor_ok"] is False
    assert proc.returncode == 1


def test_dirty_tree_before_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [ok_check()])
    commit_all(repo, "initial")
    # dirty the tree
    write(repo, "dirty.txt", "uncommitted\n")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2
    assert data["tree_clean_before"] is False


def test_check_timeout_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [{
        "name": "slow",
        "command": [sys.executable, "-c", "import time; time.sleep(5)"],
        "timeout_s": 1,
    }])
    commit_all(repo, "initial")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2
    assert len(data["checks"]) == 1
    assert data["checks"][0]["timed_out"] is True
    assert data["checks"][0]["exit_code"] is None


def test_missing_executable_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [{
        "name": "missing-bin",
        "command": ["definitely-not-a-real-executable-xyz123", "--help"],
    }])
    commit_all(repo, "initial")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2
    assert data["checks"][0]["exit_code"] is None
    assert data["checks"][0]["timed_out"] is False


def test_missing_config_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    commit_all(repo, "initial")  # no merge-verify.json
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2


def test_invalid_json_config_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    (repo / "merge-verify.json").write_text("{not valid json", encoding="utf-8")
    commit_all(repo, "initial bad config")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2


def test_check_dirties_tree_failed(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [{
        "name": "polluter",
        "command": [sys.executable, "-c", "open('polluted.txt','w').write('x')"],
    }])
    commit_all(repo, "initial")
    proc, data = run_tool(repo)
    assert data["verdict"] == "FAILED"
    assert proc.returncode == 1
    assert data["tree_clean_before"] is True
    assert data["tree_clean_after"] is False
    assert any("tree_dirty_after" in e for e in data["errors"])


def test_json_output_parses(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [ok_check()])
    head = commit_all(repo, "initial")
    proc, data = run_tool(repo)
    assert proc.returncode == 0
    assert data is not None
    assert data["verdict"] == "VERIFIED"
    assert data["head"] == head
    assert isinstance(data["checks"], list)
    assert "exit_code" in data
    assert "repo" in data


def test_non_git_dir_incomplete(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "file.txt").write_text("hi\n")
    proc, data = run_tool(plain)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2


def test_empty_checks_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [])
    commit_all(repo, "initial empty checks")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2


def test_check_with_cwd_subdir(tmp_path):
    repo = make_simple_repo(tmp_path)
    sub = repo / "sub"
    sub.mkdir()
    (sub / "marker.txt").write_text("in-subdir\n", encoding="utf-8")
    write_config(repo, [{
        "name": "in-sub",
        "command": [sys.executable, "-c", "data=open('marker.txt').read(); assert 'in-subdir' in data; print('sub ok')"],
        "cwd": "sub",
    }])
    commit_all(repo, "initial with subdir")
    proc, data = run_tool(repo)
    assert data is not None, proc.stdout + proc.stderr
    assert data["verdict"] == "VERIFIED", data
    assert proc.returncode == 0
    assert data["checks"][0]["exit_code"] == 0


# ---------------------------------------------------------------- v2: package.json auto-discovery

def write_package_json(repo: Path, data, name="package.json"):
    """Write package.json from a dict, or verbatim if a string."""
    text = data if isinstance(data, str) else json.dumps(data)
    (repo / name).write_text(text, encoding="utf-8")
    return repo / name


def write_fake_pm(bin_dir: Path, name: str) -> Path:
    """Create an executable fake package manager in bin_dir.

    It prints a distinctive marker (``fake-<name> <args>``) and
    exits 0, so a test can prove which pm the tool selected by
    looking at the check's output tail — pnpm/yarn are not
    installed in every environment, and a real npm would also
    exit 0, so exit code alone cannot prove selection.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / name
    exe.write_text(f"#!/bin/sh\necho \"fake-{name} $*\"\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)
    return bin_dir


def run_tool_env(repo: Path, *extra, env_extra_path: Path | None = None, use_json=True):
    cmd = [sys.executable, str(SCRIPT), "--repo", str(repo)]
    if use_json:
        cmd.append("--json")
    cmd.extend(extra)
    env = None
    if env_extra_path is not None:
        env = os.environ.copy()
        env["PATH"] = str(env_extra_path) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    data = None
    if use_json and result.stdout.strip():
        try:
            data = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception:
            data = None
    return result, data


def test_discovery_passing_script_verified(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 0"}})
    commit_all(repo, "initial with package.json")
    proc, data = run_tool(repo)
    assert data is not None, proc.stdout + proc.stderr
    assert data["verdict"] == "VERIFIED", data
    assert proc.returncode == 0
    assert data["config_source"] == "package.json"
    assert data["discovered"] == ["test"]
    assert [c["name"] for c in data["checks"]] == ["test"]
    assert data["checks"][0]["exit_code"] == 0
    # require_clean defaults to True for discovered checks
    assert data["tree_clean_before"] is True
    assert data["tree_clean_after"] is True


def test_discovery_order_and_missing_scripts_skipped(tmp_path):
    repo = make_simple_repo(tmp_path)
    # Deliberately scrambled insertion order, no "typecheck",
    # plus a non-candidate script that must be ignored.
    write_package_json(repo, {"scripts": {
        "build": "exit 0",
        "lint": "exit 0",
        "test": "exit 0",
    }})
    commit_all(repo, "initial with package.json")
    proc, data = run_tool(repo)
    assert data["verdict"] == "VERIFIED", data
    assert data["discovered"] == ["test", "build"]
    assert [c["name"] for c in data["checks"]] == ["test", "build"]


def test_discovery_all_candidates_in_fixed_order(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {
        "build": "exit 0",
        "test": "exit 0",
        "typecheck": "exit 0",
    }})
    commit_all(repo, "initial with package.json")
    proc, data = run_tool(repo)
    assert data["verdict"] == "VERIFIED", data
    assert data["discovered"] == ["typecheck", "test", "build"]
    assert [c["name"] for c in data["checks"]] == ["typecheck", "test", "build"]


def test_discovery_empty_script_value_skipped(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "", "build": "exit 0"}})
    commit_all(repo, "initial with package.json")
    proc, data = run_tool(repo)
    assert data["verdict"] == "VERIFIED", data
    assert data["discovered"] == ["build"]


def test_discovery_pnpm_lockfile_selects_pnpm(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 0"}})
    write(repo, "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
    commit_all(repo, "initial pnpm repo")
    bin_dir = write_fake_pm(tmp_path / "fake-bin", "pnpm")
    proc, data = run_tool_env(repo, env_extra_path=bin_dir)
    assert data["verdict"] == "VERIFIED", data
    assert data["config_source"] == "package.json"
    assert "fake-pnpm" in data["checks"][0]["tail"]
    assert "run test" in data["checks"][0]["tail"]


def test_discovery_yarn_lockfile_selects_yarn(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 0"}})
    write(repo, "yarn.lock", "# yarn lockfile v1\n")
    commit_all(repo, "initial yarn repo")
    bin_dir = write_fake_pm(tmp_path / "fake-bin", "yarn")
    proc, data = run_tool_env(repo, env_extra_path=bin_dir)
    assert data["verdict"] == "VERIFIED", data
    assert "fake-yarn" in data["checks"][0]["tail"]
    assert "run test" in data["checks"][0]["tail"]


def test_discovery_default_npm_without_lockfile(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 0"}})
    commit_all(repo, "initial npm repo")
    bin_dir = write_fake_pm(tmp_path / "fake-bin", "npm")
    proc, data = run_tool_env(repo, env_extra_path=bin_dir)
    assert data["verdict"] == "VERIFIED", data
    assert "fake-npm" in data["checks"][0]["tail"]
    assert "run test" in data["checks"][0]["tail"]


def test_discovery_bun_lockfile_selects_bun(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 0"}})
    write(repo, "bun.lockb", "")
    commit_all(repo, "initial bun repo")
    bin_dir = write_fake_pm(tmp_path / "fake-bin", "bun")
    proc, data = run_tool_env(repo, env_extra_path=bin_dir)
    assert data["verdict"] == "VERIFIED", data
    assert "fake-bun" in data["checks"][0]["tail"]


def test_discovery_package_manager_field_fallback(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {
        "packageManager": "pnpm@9.0.0",
        "scripts": {"test": "exit 0"},
    })
    commit_all(repo, "initial packageManager repo")
    bin_dir = write_fake_pm(tmp_path / "fake-bin", "pnpm")
    proc, data = run_tool_env(repo, env_extra_path=bin_dir)
    assert data["verdict"] == "VERIFIED", data
    assert "fake-pnpm" in data["checks"][0]["tail"]


def test_discovery_lockfile_wins_over_package_manager_field(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {
        "packageManager": "pnpm@9.0.0",
        "scripts": {"test": "exit 0"},
    })
    write(repo, "yarn.lock", "# yarn lockfile v1\n")
    commit_all(repo, "initial lockfile-wins repo")
    bin_dir = tmp_path / "fake-bin"
    write_fake_pm(bin_dir, "pnpm")
    write_fake_pm(bin_dir, "yarn")
    proc, data = run_tool_env(repo, env_extra_path=bin_dir)
    assert data["verdict"] == "VERIFIED", data
    assert "fake-yarn" in data["checks"][0]["tail"]
    assert "fake-pnpm" not in data["checks"][0]["tail"]


def test_config_file_wins_over_package_json(tmp_path):
    repo = make_simple_repo(tmp_path)
    # package.json script would fail if it were (wrongly) used
    write_package_json(repo, {"scripts": {"test": "exit 1"}})
    write_config(repo, [ok_check("from-config")])
    commit_all(repo, "initial config + package.json")
    proc, data = run_tool(repo)
    assert data["verdict"] == "VERIFIED", data
    assert data["config_source"] == "file"
    assert data["discovered"] == []
    assert [c["name"] for c in data["checks"]] == ["from-config"]


def test_explicit_config_wins_over_package_json(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 1"}})
    commit_all(repo, "initial package.json only")
    external = tmp_path / "external-config.json"
    external.write_text(
        json.dumps({"require_clean": True, "checks": [ok_check("external")]}),
        encoding="utf-8",
    )
    proc, data = run_tool(repo, "--config", str(external))
    assert data["verdict"] == "VERIFIED", data
    assert data["config_source"] == "file"
    assert data["discovered"] == []
    assert [c["name"] for c in data["checks"]] == ["external"]


def test_no_auto_discover_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 0"}})
    commit_all(repo, "initial with package.json")
    proc, data = run_tool(repo, "--no-auto-discover")
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2
    assert data["config_source"] is None
    assert data["discovered"] == []


def test_no_config_and_no_package_json_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    commit_all(repo, "initial")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2
    assert data["config_source"] is None
    assert data["discovered"] == []
    assert any(
        "no config was found" in e and "no checks could be discovered" in e
        for e in data["errors"]
    ), data["errors"]


def test_invalid_package_json_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, "{not valid json")
    commit_all(repo, "initial bad package.json")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2
    assert data["config_source"] is None
    assert any("no checks could be discovered" in e for e in data["errors"])


def test_package_json_not_an_object_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, "[1, 2, 3]")
    commit_all(repo, "initial array package.json")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2
    assert data["config_source"] is None


def test_package_json_no_candidate_scripts_incomplete(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"lint": "exit 0", "format": "exit 0"}})
    commit_all(repo, "initial no candidates")
    proc, data = run_tool(repo)
    assert data["verdict"] == "INCOMPLETE"
    assert proc.returncode == 2
    assert data["config_source"] is None
    assert data["discovered"] == []
    assert any("no checks could be discovered" in e for e in data["errors"])


def test_discovered_failing_script_failed(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 1"}})
    commit_all(repo, "initial failing package.json")
    proc, data = run_tool(repo)
    assert data["verdict"] == "FAILED", data
    assert proc.returncode == 1
    assert data["config_source"] == "package.json"
    assert data["discovered"] == ["test"]
    assert data["checks"][0]["exit_code"] not in (0, None)


def test_discovery_human_output_line(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_package_json(repo, {"scripts": {"test": "exit 0"}})
    commit_all(repo, "initial with package.json")
    proc, _ = run_tool(repo, use_json=False)
    assert proc.returncode == 0
    assert "config: derived from package.json (scripts: test)" in proc.stdout


def test_config_file_reports_file_source(tmp_path):
    repo = make_simple_repo(tmp_path)
    write_config(repo, [ok_check()])
    commit_all(repo, "initial")
    proc, data = run_tool(repo)
    assert data["verdict"] == "VERIFIED"
    assert data["config_source"] == "file"
    assert data["discovered"] == []
