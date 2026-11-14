"""Tests for scripts/test_gate.py (AC-206): each failure case is proven on a temporary tree.

The gate runs as a subprocess on a throw-away tree (--root, --test-dir), so no test module is
loaded into this process. Software evidence only.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "test_gate.py"

PLAN = """# Plan

| ID | Test | Sections |
|---|---|---|
| CT-AAA-01 | First | 1.1 |
| CT-AAA-02 | Second | 2 |
| CT-BBB-01 | Third | 3, 4 |
| CT-BBB-02 | Fourth | 5 |
"""
TESTS = """import unittest


class T(unittest.TestCase):
    def test_a(self):
        pass

    def test_b(self):
        pass
"""


def entries():
    return [
        {"id": "CT-AAA-01", "status": "IN_SCOPE", "contract_sections": "1.1", "test": "test_mod.T.test_a"},
        {"id": "CT-AAA-02", "status": "IN_SCOPE", "contract_sections": "2", "test": "test_mod.T.test_b"},
        {"id": "CT-BBB-01", "status": "DEFERRED", "contract_sections": "3, 4", "reason": "needs the runtime"},
        {"id": "CT-BBB-02", "status": "OUT_OF_SCOPE", "contract_sections": "5", "reason": "backend"},
    ]


class Tree:
    def __init__(self, test_src=TESTS, plan=PLAN, entries_=None, manifest=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "contract").mkdir()
        (self.root / "contract" / "CONFORMANCE_TEST_PLAN.md").write_text(plan, encoding="utf-8")
        (self.root / "tests" / "unit").mkdir(parents=True)
        (self.root / "tests" / "manifest").mkdir()
        if test_src is not None:
            (self.root / "tests" / "unit" / "test_mod.py").write_text(test_src, encoding="utf-8")
        if manifest:
            m = {"plan": "contract/CONFORMANCE_TEST_PLAN.md", "entries": entries() if entries_ is None else entries_}
            (self.root / "tests" / "manifest" / "conformance_manifest.json").write_text(json.dumps(m), encoding="utf-8")

    def run(self):
        p = subprocess.run([sys.executable, str(GATE), "--root", str(self.root), "--test-dir", "tests/unit"],
                           capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def close(self):
        self.tmp.cleanup()


class GateCase(unittest.TestCase):
    def gate(self, **kw):
        t = Tree(**kw)
        self.addCleanup(t.close)
        return t.run()

    def refused(self, needle, **kw):
        rc, out = self.gate(**kw)
        self.assertEqual(rc, 1, out)
        self.assertIn("GATE FAIL", out)
        self.assertIn(needle, out)
        self.assertNotIn("gate: ok", out)

    def mod(self, i, **over):
        e = entries()
        e[i].update(over)
        return e


class TestGatePasses(GateCase):
    def test_a_consistent_tree_passes_and_reports_separate_counts(self):
        rc, out = self.gate()
        self.assertEqual(rc, 0, out)
        self.assertIn("gate: ok", out)
        self.assertIn("ids=4 in_scope_passed=2 deferred=1 out_of_scope=1 unit_tests_run=2", out)

    def test_deferred_and_out_of_scope_are_not_counted_as_passed(self):
        rc, out = self.gate(entries_=[
            {"id": "CT-AAA-01", "status": "DEFERRED", "contract_sections": "1.1", "reason": "later"},
            {"id": "CT-AAA-02", "status": "DEFERRED", "contract_sections": "2", "reason": "later"},
            {"id": "CT-BBB-01", "status": "DEFERRED", "contract_sections": "3, 4", "reason": "later"},
            {"id": "CT-BBB-02", "status": "OUT_OF_SCOPE", "contract_sections": "5", "reason": "n/a"}])
        self.assertEqual(rc, 0, out)
        self.assertIn("in_scope_passed=0 deferred=3 out_of_scope=1", out)


class TestManifestVersusPlan(GateCase):
    def test_a_missing_id_is_refused(self):
        self.refused("manifest is missing CT-BBB-02", entries_=entries()[:3])

    def test_an_extra_id_is_refused(self):
        e = entries() + [{"id": "CT-ZZZ-01", "status": "DEFERRED", "contract_sections": "9", "reason": "x"}]
        self.refused("CT-ZZZ-01 which is not in the plan", entries_=e)

    def test_a_duplicate_id_is_refused(self):
        self.refused("lists CT-BBB-01 more than once", entries_=entries() + [entries()[2]])

    def test_an_unknown_status_is_refused(self):
        self.refused("unknown status", entries_=self.mod(2, status="DONE"))

    def test_changed_contract_sections_are_refused(self):
        self.refused("contract_sections", entries_=self.mod(0, contract_sections="9"))

    def test_a_manifest_that_is_not_json_is_refused(self):
        t = Tree()
        self.addCleanup(t.close)
        (t.root / "tests" / "manifest" / "conformance_manifest.json").write_text("{", encoding="utf-8")
        rc, out = t.run()
        self.assertEqual(rc, 1)
        self.assertIn("not valid JSON", out)

    def test_a_missing_manifest_is_refused(self):
        self.refused("does not exist", manifest=False)


class TestInScopeMapping(GateCase):
    def test_an_in_scope_entry_without_a_test_is_refused(self):
        e = self.mod(0)
        del e[0]["test"]
        self.refused("needs exactly one test id", entries_=e)

    def test_a_test_that_was_not_discovered_is_refused(self):
        self.refused("was not discovered", entries_=self.mod(0, test="test_mod.T.test_nope"))

    def test_two_ids_must_not_share_a_test(self):
        self.refused("is also mapped to", entries_=self.mod(1, test="test_mod.T.test_a"))

    def test_a_failing_mapped_test_is_refused(self):
        src = TESTS.replace("def test_a(self):\n        pass", "def test_a(self):\n        self.fail('x')")
        self.refused("tests failed", test_src=src)

    def test_a_skipped_mapped_test_is_refused(self):
        src = TESTS.replace("    def test_a(self):", "    @unittest.skip('later')\n    def test_a(self):")
        rc, out = self.gate(test_src=src)
        self.assertEqual(rc, 1, out)
        self.assertIn("skipped", out)
        self.assertIn("did not pass", out)

    def test_a_failing_subtest_fails_the_test(self):
        src = TESTS.replace("    def test_a(self):\n        pass",
                            "    def test_a(self):\n        with self.subTest(i=1):\n            self.assertEqual(1, 2)")
        rc, out = self.gate(test_src=src)
        self.assertEqual(rc, 1, out)
        self.assertIn("test_mod.T.test_a did not pass", out)

    def test_an_expected_failure_is_not_a_pass(self):
        src = TESTS.replace("    def test_a(self):\n        pass", "    @unittest.expectedFailure\n    def test_a(self):\n        self.fail('x')")
        rc, out = self.gate(test_src=src)
        self.assertEqual(rc, 1, out)
        self.assertIn("did not pass", out)


class TestDeferredAndOutOfScope(GateCase):
    def test_a_deferred_entry_needs_a_reason(self):
        e = self.mod(2)
        del e[2]["reason"]
        self.refused("needs a reason", entries_=e)

    def test_a_blank_reason_is_refused(self):
        self.refused("needs a reason", entries_=self.mod(3, reason="  "))

    def test_a_deferred_entry_must_not_name_a_test(self):
        self.refused("must not name a test", entries_=self.mod(2, test="test_mod.T.test_a"))


class TestUnitTests(GateCase):
    def test_no_tests_is_a_failure_not_a_pass(self):
        self.refused("no tests were discovered", test_src="x = 1\n")

    def test_a_failing_unrelated_test_fails_the_gate(self):
        src = TESTS + "\n    def test_c(self):\n        self.fail('x')\n"
        self.refused("tests failed", test_src=src)

    def test_an_import_error_in_a_test_module_fails_the_gate(self):
        t = Tree()
        self.addCleanup(t.close)
        (t.root / "tests" / "unit" / "test_broken.py").write_text("import no_such_module_xyz\n", encoding="utf-8")
        rc, out = t.run()
        self.assertEqual(rc, 1, out)
        self.assertIn("tests failed", out)

    def test_a_missing_test_directory_fails_the_gate(self):
        t = Tree()
        self.addCleanup(t.close)
        p = subprocess.run([sys.executable, str(GATE), "--root", str(t.root), "--test-dir", "tests/nowhere"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 1)
        self.assertIn("does not exist", p.stdout)


class TestMissingTestDependency(unittest.TestCase):
    """The preflight names the interpreter and the fix instead of leaving only import errors."""

    @staticmethod
    def _gate_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("gate_script_under_test", GATE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_a_missing_jsonschema_gives_an_actionable_hint(self):
        def no_import(name):
            raise ImportError(name)
        hint = self._gate_module().missing_test_dependency(no_import)
        self.assertIsNotNone(hint)
        self.assertIn(sys.executable, hint)
        self.assertIn("-m pip install -r requirements-test.txt", hint)
        self.assertIn("3.11", hint)
        self.assertIn("make test-unit PYTHON=", hint)

    def test_no_hint_when_the_dependency_imports(self):
        self.assertIsNone(self._gate_module().missing_test_dependency(lambda name: object()))


class TestRealManifest(unittest.TestCase):
    def test_the_repository_manifest_covers_the_plan_exactly(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import test_gate as g  # noqa: E402
        rows, dups = g.plan_rows(ROOT / "contract" / "CONFORMANCE_TEST_PLAN.md")
        self.assertEqual(dups, [])
        m = json.loads((ROOT / "tests" / "manifest" / "conformance_manifest.json").read_text(encoding="utf-8"))
        ids = [e["id"] for e in m["entries"]]
        self.assertEqual(sorted(ids), sorted(rows))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(rows), 124)


if __name__ == "__main__":
    unittest.main()
