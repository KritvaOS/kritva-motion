#!/usr/bin/env python3
"""Regression tests for this repository's README checker (Kritva README standard, D-055/D-057).

The checker is structural only. These tests cover its code-block, link, placeholder and metadata handling so
that a change to the checker cannot silently weaken it. They do not test that any README is accurate.
"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = [ROOT / "scripts" / "check_readme.py", ROOT / "scripts" / "docs" / "check_readme.py",
              ROOT / "scripts" / "validation" / "check_readme.py"]
CHECKER = next(p for p in CANDIDATES if p.exists())
_spec = importlib.util.spec_from_file_location("check_readme", CHECKER)
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

FIELDS = "".join(f"| {f} | value |\n" for f in C.FIELDS)
HEADS = "\n".join(f"## {h}\n\ntext\n" for h in (
    "Purpose and Scope", "Position in the Ecosystem", "Architecture", "Documents to Read", "Repository Structure",
    "Tool and Development Workflow", "Dependencies", "Milestones", "Tasks and Acceptance", "Status Reporting",
    "Validation and Regression", "Git Workflow", "Safety and Security", "Release and Versioning", "Ownership",
    "Related Repositories", "License"))
GOOD = f"# r\n\n> d\n\n| Property | Value |\n|---|---|\n{FIELDS}\n{HEADS}"


class CheckReadme(unittest.TestCase):
    def run_check(self, text, files=()):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for f in files:
                (d / f).parent.mkdir(parents=True, exist_ok=True)
                (d / f).write_text("x")
            (d / "README.md").write_text(text)
            return C.check(d / "README.md", d)

    def test_complete_readme_passes(self):
        self.assertEqual(self.run_check(GOOD), [])

    def test_missing_and_empty_metadata_field_fail(self):
        self.assertTrue(self.run_check(GOOD.replace(f"| {C.FIELDS[0]} | value |\n", "")))
        self.assertTrue(self.run_check(GOOD.replace(f"| {C.FIELDS[1]} | value |", f"| {C.FIELDS[1]} |  |")))

    def test_missing_topic_fails(self):
        self.assertTrue(self.run_check(GOOD.replace("## Release and Versioning", "## Other")))

    def test_broken_link_fails_and_good_link_passes(self):
        self.assertTrue(any("does not resolve" in p for p in self.run_check(GOOD + "\n[a](nope.md)\n")))
        self.assertEqual(self.run_check(GOOD + "\n[a](docs/a.md#top) [w](https://example.com/x) [h](#top)\n", ["docs/a.md"]), [])

    def test_placeholder_fails_but_code_is_ignored(self):
        self.assertTrue(any("placeholder" in p for p in self.run_check(GOOD + "\nSee <repository-name>\n")))
        self.assertTrue(any("placeholder" in p for p in self.run_check(GOOD + "\nTODO\n")))
        self.assertEqual(self.run_check(GOOD + "\n```\n<repo> [x](nope.md) TODO\n```\nand `<y>` `[z](nope)`\n"), [])
        self.assertEqual(self.run_check(GOOD + "\nExample:\n\n    feat(x): <imperative summary> [<TASK-ID>]\n"), [])

    def test_tilde_fence_is_code_and_a_mismatched_fence_does_not_close(self):
        self.assertEqual(self.run_check(GOOD + "\n~~~\n<repo> [x](nope.md) TODO\n~~~\n"), [])
        self.assertTrue(self.run_check(GOOD + "\n```\ncode\n~~~\nTODO\n"))

    def test_link_after_a_closed_fence_is_still_checked(self):
        problems = self.run_check(GOOD + "\n```\ncode\n```\n[a](nope.md)\n")
        self.assertTrue(any("does not resolve" in p for p in problems))

    def test_link_on_an_indented_line_is_still_checked(self):
        self.assertTrue(any("does not resolve" in p for p in self.run_check(GOOD + "\n    see [a](nope.md)\n")))


class Repository(unittest.TestCase):
    def test_this_repository_readme_passes(self):
        self.assertEqual(C.check(ROOT / "README.md", ROOT), [])

    def test_cli_exit_codes(self):
        ok = subprocess.run([sys.executable, str(CHECKER), "README.md", "--root", str(ROOT)], cwd=str(ROOT), capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stdout.decode())
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "README.md").write_text("# empty\n")
            bad = subprocess.run([sys.executable, str(CHECKER), "README.md", "--root", d], cwd=d, capture_output=True)
            self.assertEqual(bad.returncode, 1)


if __name__ == "__main__":
    unittest.main()
