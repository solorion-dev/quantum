"""Tests for skill-audit. Run: python3 -m unittest discover -s tests -v"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import skill_audit as sa


def write_skill(root: Path, body: str, extra: dict | None = None) -> Path:
    skill = root / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(body, encoding="utf-8")
    for rel, content in (extra or {}).items():
        p = skill / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return skill


class ExtractionTests(unittest.TestCase):
    def test_extracts_path_repo_and_link(self):
        text = (
            "Run ~/workspace/tools/run.sh and see [guide](references/guide.md).\n"
            "Repo: `dsect-net/quantum` and https://github.com/ScottyVenable/fermata\n"
        )
        refs = sa.extract_references(text, "SKILL.md")
        kinds = {(r.kind, r.value) for r in refs}
        self.assertIn(("path", "~/workspace/tools/run.sh"), kinds)
        self.assertIn(("link", "references/guide.md"), kinds)
        self.assertIn(("repo", "dsect-net/quantum"), kinds)
        self.assertIn(("repo", "ScottyVenable/fermata"), kinds)

    def test_mimetype_is_not_a_repo(self):
        refs = sa.extract_references("Send as `text/plain` please.\n", "SKILL.md")
        self.assertEqual([r for r in refs if r.kind == "repo"], [])

    def test_file_paths_are_not_repos(self):
        text = ("See `references/access-modes.md`, `projects/README.md`, "
                "`assets/hs33.png`, press `Ctrl/Cmd-P`, format `text/markdown`.\n")
        refs = sa.extract_references(text, "SKILL.md")
        self.assertEqual([r for r in refs if r.kind == "repo"], [])

    def test_real_repos_still_detected(self):
        refs = sa.extract_references("Repos: `dsect-net/quantum` and `Cadential-Studios/prometheia`.\n", "SKILL.md")
        repos = {r.value for r in refs if r.kind == "repo"}
        self.assertEqual(repos, {"dsect-net/quantum", "Cadential-Studios/prometheia"})


class AuditTests(unittest.TestCase):
    def test_live_and_dead_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(
                root,
                "Good: [g](references/guide.md) and `scripts/run.sh`\n"
                "Bad: [b](references/missing.md)\n",
                extra={"references/guide.md": "# guide", "scripts/run.sh": "#!/bin/sh\n"},
            )
            # scripts/run.sh was referenced via backticked relative pattern? It is
            # not in references/-style folders list except scripts/ — covered.
            report = sa.audit_skill(skill, home=root)
            dead_values = {r.value for r in report.dead}
            self.assertIn("references/missing.md", dead_values)
            self.assertNotIn("references/guide.md", dead_values)

    def test_placeholder_is_skipped_not_dead(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(root, "Template: ~/workspace/{{NAME}}/x.md\n")
            report = sa.audit_skill(skill, home=root)
            self.assertTrue(any(r.status == "skipped" for r in report.references))
            self.assertEqual(report.dead, [])

    def test_repo_checker_injection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(root, "Repo: `acme/widgets` and `acme/gone`\n")

            def fake_checker(repo):
                return ("ok", "fake") if repo == "acme/widgets" else ("dead", "fake 404")

            report = sa.audit_skill(skill, repo_checker=fake_checker, home=root)
            dead = {r.value for r in report.dead}
            self.assertEqual(dead, {"acme/gone"})

    def test_repo_unverified_without_checker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(root, "Repo: `acme/widgets`\n")
            report = sa.audit_skill(skill, repo_checker=None, home=root)
            repo_refs = [r for r in report.references if r.kind == "repo"]
            self.assertEqual(repo_refs[0].status, "unverified")
            self.assertEqual(report.dead, [])

    def test_remote_home_is_unverified_not_dead(self):
        ref = sa.Reference(kind="path", value="/home/scott/codex", source_file="SKILL.md", line=1)
        sa.verify_path(ref, Path("/tmp"), Path("/home/hatch"), current_user="hatch")
        self.assertEqual(ref.status, "unverified")

    def test_date_placeholder_is_skipped(self):
        ref = sa.Reference(kind="path", value="~/workspace/wroc/weeks/week-YYYY-MM-DD.yaml",
                           source_file="SKILL.md", line=1)
        sa.verify_path(ref, Path("/tmp"), Path("/home/hatch"), current_user="hatch")
        self.assertEqual(ref.status, "skipped")

    def test_find_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_skill(root, "x")
            (root / "not-a-skill").mkdir()
            found = sa.find_skills([root])
            self.assertEqual([p.name for p in found], ["demo-skill"])


class HostScopedTests(unittest.TestCase):
    """Host-scoped declarations (evolution 2026-11-04, TRK-0608).

    A path that lives only on another host can be declared host-scoped —
    inline via <!-- skill-audit: host-scoped --> on the reference's own
    line, or per-skill via .skill-audit-ignore — and then a missing local
    copy classifies unverified instead of dead.
    """

    def test_inline_directive_marks_only_its_own_line(self):
        text = ("Tritium only: ~/.cloudflared/config.yml <!-- skill-audit: host-scoped -->\n"
                "Everywhere: ~/.cloudflared/other.yml\n")
        refs = sa.extract_references(text, "SKILL.md")
        by_value = {r.value: r for r in refs if r.kind == "path"}
        self.assertTrue(by_value["~/.cloudflared/config.yml"].host_scoped)
        self.assertFalse(by_value["~/.cloudflared/other.yml"].host_scoped)

    def test_declared_missing_path_is_unverified_not_dead(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(
                root,
                "Tritium only: ~/.cloudflared/config.yml <!-- skill-audit: host-scoped -->\n")
            report = sa.audit_skill(skill, home=root)
            self.assertEqual(report.dead, [])
            ref = report.references[0]
            self.assertEqual(ref.status, "unverified")
            self.assertIn("host-scoped", ref.detail)
            self.assertIn("skill-audit: host-scoped", ref.detail)

    def test_declared_missing_path_exits_zero_via_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_skill(
                root,
                "Tritium only: ~/.cloudflared/config.yml <!-- skill-audit: host-scoped -->\n")
            self.assertEqual(sa.main([str(root)]), 0)

    def test_undeclared_missing_path_is_dead_and_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(root, "Missing: ~/.cloudflared/config.yml\n")
            report = sa.audit_skill(skill, home=root)
            self.assertEqual([r.value for r in report.dead], ["~/.cloudflared/config.yml"])
            self.assertEqual(sa.main([str(root)]), 1)

    def test_directive_on_another_line_does_not_rescue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(
                root,
                "<!-- skill-audit: host-scoped -->\n"
                "Missing: ~/.cloudflared/config.yml\n")
            report = sa.audit_skill(skill, home=root)
            self.assertEqual([r.value for r in report.dead], ["~/.cloudflared/config.yml"])

    def test_declared_path_that_exists_is_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(
                root,
                "Here: ~/present.txt <!-- skill-audit: host-scoped -->\n",
                extra={})
            (root / "present.txt").write_text("x", encoding="utf-8")
            report = sa.audit_skill(skill, home=root)
            ref = [r for r in report.references if r.value == "~/present.txt"][0]
            self.assertEqual(ref.status, "ok")
            self.assertEqual(report.dead, [])

    def test_ignore_file_missing_match_is_unverified_not_dead(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(
                root,
                "Tritium only: ~/.cloudflared/config.yml\n",
                extra={".skill-audit-ignore": "~/.cloudflared/ # Tritium host only\n"})
            report = sa.audit_skill(skill, home=root)
            self.assertEqual(report.dead, [])
            ref = report.references[0]
            self.assertEqual(ref.status, "unverified")
            self.assertIn(".skill-audit-ignore", ref.detail)
            self.assertIn("Tritium host only", ref.detail)

    def test_ignore_file_non_match_still_dead_and_match_that_exists_is_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_skill(
                root,
                "Gone: ~/gone.txt\nHere: ~/present.txt\n",
                extra={".skill-audit-ignore": "~/present.txt # declared but present\n"})
            (root / "present.txt").write_text("x", encoding="utf-8")
            report = sa.audit_skill(skill, home=root)
            by_value = {r.value: r for r in report.references}
            self.assertEqual(by_value["~/gone.txt"].status, "dead")
            self.assertEqual(by_value["~/present.txt"].status, "ok")

    def test_parse_ignore_text(self):
        entries = sa.parse_ignore_text(
            "# comment only\n\n~/.cloudflared/ # Tritium only\n/opt/other/\n")
        self.assertEqual(entries, [("~/.cloudflared/", "Tritium only"),
                                   ("/opt/other/", "")])


if __name__ == "__main__":
    unittest.main()
