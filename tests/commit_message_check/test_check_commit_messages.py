#!/usr/bin/env python3
"""Unit tests for the commit message checker.

Security control from kritva-program decision D-032 (follow-up).
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "security"))
import check_commit_messages as ccm  # noqa: E402


class MessageTests(unittest.TestCase):
    def test_clean_message_passes(self):
        self.assertEqual(ccm.problems("feat: add thing\n\nbody\n\nCo-Authored-By: Someone <a@b.c>"), [])

    def test_session_trailer_is_rejected_in_any_case(self):
        self.assertTrue(ccm.problems("x\n\nClaude-Session: https://example.test/s"))
        self.assertTrue(ccm.problems("x\n\nclaude-session: abc"))

    def test_session_link_is_rejected(self):
        self.assertTrue(ccm.problems("x\n\nsee https://claude.ai/code/session_01abc"))

    def test_the_word_alone_is_allowed(self):
        self.assertEqual(ccm.problems("docs: describe the claude session policy"), [])


class RangeTests(unittest.TestCase):
    def git(self, d, *args):
        subprocess.run(["git", "-C", d, *args], check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.t"})

    def test_range_flags_only_new_commits(self):
        with tempfile.TemporaryDirectory() as d:
            self.git(d, "init", "-q")
            self.git(d, "commit", "-q", "--allow-empty", "-m", "old\n\nClaude-Session: https://claude.ai/code/session_old")
            self.git(d, "commit", "-q", "--allow-empty", "-m", "clean")
            self.git(d, "commit", "-q", "--allow-empty", "-m", "bad\n\nClaude-Session: https://claude.ai/code/session_new")
            cwd = os.getcwd()
            os.chdir(d)
            try:
                self.assertEqual(ccm.main(["--range", "HEAD~2..HEAD"]), 1)
                self.assertEqual(ccm.main(["--range", "HEAD~2..HEAD~1"]), 0)
                self.assertEqual(ccm.main(["--range", "no-such-ref..HEAD"]), 2)
            finally:
                os.chdir(cwd)

    def test_file_mode(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("x\n\nClaude-Session: y\n")
        try:
            self.assertEqual(ccm.main(["--file", fh.name]), 1)
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
