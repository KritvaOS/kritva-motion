"""Tests for scripts/integration_gate.py (AC-406): each outcome is proven on a throw-away tree, run as a subprocess
so no test module is loaded into this process. Software evidence only."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "integration_gate.py"
PASSING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n"
FAILING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1, 2)\n"
SKIPPED = "import unittest\n\nclass T(unittest.TestCase):\n    @unittest.skip('x')\n    def test_a(self):\n        pass\n"


def run(body=None, manifest=None):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if body is not None:
            (root / "tests" / "integration").mkdir(parents=True)
            (root / "tests" / "integration" / "test_mod.py").write_text(body, encoding="utf-8")
        if manifest is not None:
            (root / "tests" / "manifest").mkdir(parents=True)
            (root / "tests" / "manifest" / "conformance_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        p = subprocess.run([sys.executable, str(GATE), "--root", str(root)], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


class TestIntegrationGate(unittest.TestCase):
    def test_passes_when_every_test_passes_and_names_the_evidenced_ids(self):
        manifest = {"entries": [{"id": "CT-X-01", "status": "IN_SCOPE", "test": "test_mod.T.test_a"}]}
        code, out = run(PASSING, manifest)
        self.assertEqual(code, 0, out)
        self.assertIn("conformance_ids_evidenced=['CT-X-01']", out)
        self.assertIn("integration gate: ok", out)

    def test_fails_on_a_failing_test(self):
        self.assertEqual(run(FAILING)[0], 1)

    def test_fails_on_a_skipped_test(self):
        code, out = run(SKIPPED)
        self.assertEqual(code, 1)
        self.assertIn("skipped", out)

    def test_fails_when_no_test_exists(self):
        code, out = run("")
        self.assertEqual(code, 1)
        self.assertIn("no integration test", out)

    def test_fails_when_the_directory_is_missing(self):
        self.assertEqual(run(None)[0], 1)

    def test_the_repository_gate_passes_and_names_the_two_ids(self):
        p = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("CT-BE-03", p.stdout)
        self.assertIn("CT-BE-06", p.stdout)


if __name__ == "__main__":
    unittest.main()
