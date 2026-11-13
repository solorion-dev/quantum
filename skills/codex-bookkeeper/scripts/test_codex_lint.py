#!/usr/bin/env python3
"""Tests for codex_lint.py — fixture-vault tests for every check family.

Added 2026-10-18 (daily evolution build) when the canonical script was
restored into this skill copy. The canonical script shipped with no tests;
these pin its documented behavior (F/N/G/L/A/S families) so a future edit
to the linter — or a future re-sync from the Codex copy — can't silently
change what "conformant" means.

Run:  python3 -m unittest discover -s scripts -v
  or: python3 scripts/test_codex_lint.py
Requires PyYAML (same dependency as codex_lint.py itself).
"""
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("codex_lint", HERE / "codex_lint.py")
codex_lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codex_lint)

GOOD_FM = """\
---
title: "A Fine Note"
author_agent: "cooper"
agent_id: "cooper@dsect.net"
last_edited_by: "cooper"
date_created: "2026-10-18"
time_created: "09:00:00"
last_updated: "2026-10-18"
time_updated: "10:00:00"
status: "Active"
maintained_by: "cooper"
version: "1.0"
tags: ["team-quantum"]
related_files: []
---
"""


def codes(findings):
    return [f.code for f in findings]


class LintTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relpath: str, text: str) -> Path:
        p = self.vault / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def lint(self, relpath: str, text: str, index=None):
        p = self.write(relpath, text)
        return codex_lint.lint_file(p, self.vault, index)


class TestFrontmatter(LintTestCase):
    def test_clean_note_has_no_findings(self):
        self.assertEqual(self.lint("notes/Fine Note.md", GOOD_FM + "\nBody.\n"), [])

    def test_missing_frontmatter_is_f1_error(self):
        findings = self.lint("notes/Bare.md", "Just a body, no frontmatter.\n")
        self.assertIn("F1", codes(findings))
        self.assertEqual(findings[codes(findings).index("F1")].level, "ERROR")

    def test_missing_fields_are_f3(self):
        fm = '---\ntitle: "Only a title"\nstatus: "Active"\n---\n'
        findings = self.lint("notes/Thin.md", fm + "\nBody.\n")
        self.assertIn("F3", codes(findings))
        msg = findings[codes(findings).index("F3")].msg
        self.assertIn("author_agent", msg)
        self.assertIn("related_files", msg)

    def test_unparseable_frontmatter_is_f2(self):
        findings = self.lint("notes/Broken.md", "---\ntitle: [unclosed\n---\n\nBody.\n")
        self.assertIn("F2", codes(findings))

    def test_bad_status_is_f4(self):
        fm = GOOD_FM.replace('status: "Active"', 'status: "Banana"')
        self.assertIn("F4", codes(self.lint("notes/Bad Status.md", fm + "\nBody.\n")))

    def test_bad_date_format_is_f5_warning(self):
        fm = GOOD_FM.replace('date_created: "2026-10-18"', 'date_created: "10/18/2026"')
        findings = self.lint("notes/Bad Date.md", fm + "\nBody.\n")
        self.assertIn("F5", codes(findings))
        self.assertEqual(findings[codes(findings).index("F5")].level, "WARN")

    def test_out_of_order_keys_are_f6(self):
        fm = GOOD_FM.replace('title: "A Fine Note"\nauthor_agent: "cooper"',
                              'author_agent: "cooper"\ntitle: "A Fine Note"')
        self.assertIn("F6", codes(self.lint("notes/Shuffled.md", fm + "\nBody.\n")))

    def test_second_frontmatter_block_is_f7(self):
        text = GOOD_FM + '\n---\ntitle: "Again"\n---\n\nBody.\n'
        self.assertIn("F7", codes(self.lint("notes/Double.md", text)))

    def test_empty_file_is_f0_warning(self):
        findings = self.lint("notes/Empty.md", "")
        self.assertIn("F0", codes(findings))

    def test_soul_md_is_exempt(self):
        self.assertEqual(self.lint("SOUL.md", "No frontmatter at all.\n"), [])


class TestNaming(LintTestCase):
    def test_banned_character_is_n1(self):
        findings = self.lint("notes/Bad: Name.md", GOOD_FM + "\nBody.\n")
        self.assertIn("N1", codes(findings))

    def test_goal_filename_pattern_warns_n2(self):
        fm = GOOD_FM.replace("---\n", '---\ngoal_id: "NEB-001"\ncodename: "FOO"\nproject: "Nebula"\nphase: "1"\n', 1)
        findings = self.lint("projects/X/goals/loose name.md", fm + "\nBody.\n")
        self.assertIn("N2", codes(findings))

    def test_well_formed_goal_filename_no_n2(self):
        fm = GOOD_FM.replace("---\n", '---\ngoal_id: "NEB-001"\ncodename: "FOO"\nproject: "Nebula"\nphase: "1"\n', 1)
        findings = self.lint("projects/X/goals/NEB-001 FOO — The Thing.md", fm + "\nBody.\n")
        self.assertNotIn("N2", codes(findings))
        self.assertNotIn("G1", codes(findings))
        self.assertNotIn("G2", codes(findings))


class TestGoalNotes(LintTestCase):
    def test_goal_note_missing_goal_fields_is_g1(self):
        findings = self.lint("projects/X/goals/NEB-001 FOO — The Thing.md", GOOD_FM + "\nBody.\n")
        # in_goals triggers G checks only via goal_id presence in the G branch:
        # the branch runs when in_goals OR goal_id set — in_goals is True here.
        self.assertIn("G1", codes(findings))

    def test_non_numeric_phase_is_g2(self):
        fm = GOOD_FM.replace("---\n", '---\ngoal_id: "NEB-001"\ncodename: "FOO"\nproject: "Nebula"\nphase: "discovery"\n', 1)
        findings = self.lint("projects/X/goals/NEB-001 FOO — The Thing.md", fm + "\nBody.\n")
        self.assertIn("G2", codes(findings))


class TestArchive(LintTestCase):
    def test_archived_without_successor_is_a1(self):
        fm = GOOD_FM.replace('status: "Active"', 'status: "Archived"')
        self.assertIn("A1", codes(self.lint("notes/Old.md", fm + "\nBody.\n")))

    def test_archived_with_successor_in_body_is_clean_of_a1(self):
        fm = GOOD_FM.replace('status: "Active"', 'status: "Archived"')
        findings = self.lint("notes/Old.md", fm + "\nSuperseded by [[notes/Fine Note]].\n")
        self.assertNotIn("A1", codes(findings))

    def test_archived_with_related_files_is_clean_of_a1(self):
        fm = (GOOD_FM.replace('status: "Active"', 'status: "Archived"')
                      .replace("related_files: []", 'related_files: ["notes/Fine Note.md"]'))
        findings = self.lint("notes/Old.md", fm + "\nBody.\n")
        self.assertNotIn("A1", codes(findings))


class TestLinks(LintTestCase):
    def test_bare_project_doc_is_l1(self):
        findings = self.lint("notes/Links.md", GOOD_FM + "\nSee [[OVERVIEW]] for details.\n")
        self.assertIn("L1", codes(findings))

    def test_path_qualified_project_doc_is_fine(self):
        findings = self.lint("notes/Links.md", GOOD_FM + "\nSee [[projects/X/OVERVIEW]].\n")
        self.assertNotIn("L1", codes(findings))

    def test_broken_wikilink_is_l2_with_index(self):
        target = self.write("notes/Target.md", GOOD_FM + "\nBody.\n")
        source = self.write("notes/Source.md", GOOD_FM + "\n[[Target]] and [[Nowhere Real]]\n")
        index = codex_lint.build_index(self.vault, None, None)
        findings = codex_lint.lint_file(source, self.vault, index)
        self.assertIn("L2", codes(findings))
        msgs = [f.msg for f in findings if f.code == "L2"]
        self.assertTrue(any("Nowhere Real" in m for m in msgs))
        self.assertFalse(any(m.endswith("[[Target]]") for m in msgs))
        self.assertIsNotNone(target)


class TestSkillNotes(LintTestCase):
    def test_skill_with_name_and_description_passes(self):
        text = '---\nname: "my-skill"\ndescription: "Does a thing."\n---\n\n# Skill\n'
        self.assertEqual(self.lint("Skills/my-skill/SKILL.md", text), [])

    def test_skill_name_folder_mismatch_is_s2(self):
        text = '---\nname: "other-name"\ndescription: "Does a thing."\n---\n\n# Skill\n'
        self.assertIn("S2", codes(self.lint("Skills/my-skill/SKILL.md", text)))

    def test_skill_missing_description_is_s1(self):
        text = '---\nname: "my-skill"\n---\n\n# Skill\n'
        self.assertIn("S1", codes(self.lint("Skills/my-skill/SKILL.md", text)))


class TestMainExitCodes(LintTestCase):
    def run_main(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = codex_lint.main(argv)
        return rc, buf.getvalue()

    def test_clean_vault_exits_0_strict(self):
        self.write("notes/Fine Note.md", GOOD_FM + "\nBody.\n")
        rc, out = self.run_main([str(self.vault / "notes"), "--vault", str(self.vault), "--strict"])
        self.assertEqual(rc, 0)
        self.assertIn("0 errors", out)

    def test_errors_exit_1_only_when_strict(self):
        self.write("notes/Bare.md", "No frontmatter.\n")
        rc_strict, _ = self.run_main([str(self.vault / "notes"), "--vault", str(self.vault), "--strict"])
        rc_loose, _ = self.run_main([str(self.vault / "notes"), "--vault", str(self.vault)])
        self.assertEqual(rc_strict, 1)
        self.assertEqual(rc_loose, 0)

    def test_report_file_is_written(self):
        self.write("notes/Bare.md", "No frontmatter.\n")
        report = self.vault / "report.md"
        rc, _ = self.run_main([str(self.vault / "notes"), "--vault", str(self.vault),
                               "--report", str(report)])
        self.assertEqual(rc, 0)
        text = report.read_text(encoding="utf-8")
        self.assertIn("1 errors", text)
        self.assertIn("F1", text)

    def test_skip_prefixes_are_not_linted(self):
        self.write("_templates/Tmpl.md", "No frontmatter, template block only.\n")
        self.write("notes/Fine Note.md", GOOD_FM + "\nBody.\n")
        rc, out = self.run_main([str(self.vault), "--vault", str(self.vault), "--strict"])
        self.assertEqual(rc, 0)
        self.assertIn("1 files", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
