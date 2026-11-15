"""Tests for scripts/regression_gate.py and scripts/regression_update.py (AC-406), proven on throw-away trees and
as subprocesses so no test module is loaded into this process. Software evidence only."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "regression_gate.py"
UPDATE = ROOT / "scripts" / "regression_update.py"
PASSING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n"
FAILING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1, 2)\n"


def gate(root):
    p = subprocess.run([sys.executable, str(GATE), "--root", str(root)], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


class TestRegressionGate(unittest.TestCase):
    def tree(self, tmp, body):
        d = Path(tmp) / "tests" / "regression"
        d.mkdir(parents=True)
        if body is not None:
            (d / "test_mod.py").write_text(body, encoding="utf-8")
        return Path(tmp)

    def test_passes_on_a_passing_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = gate(self.tree(tmp, PASSING))
        self.assertEqual(code, 0, out)
        self.assertIn("regression gate: ok", out)

    def test_fails_on_a_failing_test_an_empty_tree_and_a_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gate(self.tree(tmp, FAILING))[0], 1)
        with tempfile.TemporaryDirectory() as tmp:
            code, out = gate(self.tree(tmp, None))
            self.assertEqual(code, 1)
            self.assertIn("no regression test", out)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gate(Path(tmp))[0], 1)

    def test_the_repository_gate_passes(self):
        p = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_the_update_command_changes_nothing_when_the_traces_are_current(self):
        p = subprocess.run([sys.executable, str(UPDATE)], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("written or changed: none", p.stdout)
        self.assertIn("removed: none", p.stdout)


if __name__ == "__main__":
    unittest.main()
