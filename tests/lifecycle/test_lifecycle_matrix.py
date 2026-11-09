"""The generated transition matrix against LIFECYCLE.md (KOS-MOTION-003 PR-06).

scripts/lifecycle_matrix.py prints the three transition tables (T: command states, 7.5; C: joint control, 13.3;
H: joint health, 13.3) from src/kritva_motion/lifecycle/model.py. This test compares them with the tables in
tasks/KOS-MOTION-003/LIFECYCLE.md row by row, so it fails on a missing, extra, duplicated or replaced
transition and not only on a different count. It then breaks a copy of the document in each of those four ways
and requires the comparison to notice. Deterministic and offline; reads two files.
"""
import importlib.util
import itertools
import json
import unittest
from pathlib import Path

import lifecycle_support as S   # noqa: F401  (puts src on the path)
from kritva_motion.lifecycle import model

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lifecycle_matrix", ROOT / "scripts" / "lifecycle_matrix.py")
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)

MANIFEST = json.loads((ROOT / "tests" / "manifest" / "conformance_manifest.json").read_text(encoding="utf-8"))
ID_MATRIX = (ROOT / "tasks" / "KOS-MOTION-003" / "ID_MATRIX.md").read_text(encoding="utf-8")
DOC = (ROOT / "tasks" / "KOS-MOTION-003" / "LIFECYCLE.md").read_text(encoding="utf-8")


class TestTransitionMatrix(unittest.TestCase):
    def test_code_and_document_agree_row_for_row(self):
        self.assertEqual(matrix.compare(matrix.generated(), matrix.documented(DOC)), [])

    def test_sizes_and_content_of_the_tables(self):
        g = matrix.generated()
        self.assertEqual([len(g[k]) for k in "TCH"], [7, 11, 6])
        self.assertEqual({(f, t) for _, f, t in g["T"]},
                         {("(admission)", "ACCEPTED"), ("ACCEPTED", "RUNNING"), ("ACCEPTED", "CANCELLED"),
                          ("ACCEPTED", "FAILED"), ("RUNNING", "COMPLETED"), ("RUNNING", "CANCELLED"),
                          ("RUNNING", "FAILED")})
        # the command table is exactly the pairs of the 5 x 5 grid that the model allows (CT-LC-02 uses the same)
        allowed = {(a, b) for a, b in itertools.product(model.STATES, repeat=2) if model.is_allowed(a, b)}
        self.assertEqual(allowed, {(f, t) for _, f, t in g["T"] if f != "(admission)"})
        self.assertEqual({(f, t) for _, f, t in g["C"]}, set(model.CONTROL_TRANSITIONS))
        self.assertEqual({(f, t) for _, f, t in g["H"]}, set(model.HEALTH_TRANSITIONS))

    def test_the_rendered_matrix_is_what_the_document_carries(self):
        rendered = matrix.render().splitlines()
        for line in rendered:
            if line.startswith("| C") or line.startswith("| H"):
                self.assertIn(line, DOC.splitlines(), "the document carries the generated row verbatim")

    def test_a_broken_document_is_noticed(self):
        lines = DOC.splitlines()
        rows = [i for i, ln in enumerate(lines) if matrix._ROW.match(ln)]
        self.assertEqual(len(rows), 7 + 11 + 6)
        gen = matrix.generated()
        for key, label in (("T", "T5"), ("C", "C4"), ("H", "H3")):
            i = next(k for k in rows if lines[k].startswith(f"| {label} |"))
            with self.subTest(missing=label):
                broken = lines[:i] + lines[i + 1:]
                self.assertTrue(any("in the code but not in" in p for p in matrix.compare(gen, matrix.documented("\n".join(broken)))))
            with self.subTest(duplicated=label):
                broken = lines[:i + 1] + [lines[i]] + lines[i + 1:]
                self.assertTrue(any("duplicated" in p for p in matrix.compare(gen, matrix.documented("\n".join(broken)))))
            with self.subTest(replaced=label):      # same number of rows, one transition changed
                broken = list(lines)
                cells = broken[i].split("|")           # | label | from | to | ...: change the "to" cell only
                cells[3] = " `NOWHERE` "
                broken[i] = "|".join(cells)
                problems = matrix.compare(gen, matrix.documented("\n".join(broken)))
                self.assertTrue(any("in the code but not in" in p for p in problems), problems)
                self.assertTrue(any("in LIFECYCLE.md but not in the code" in p for p in problems), problems)
        with self.subTest(extra="Cx"):
            extra = DOC + "\n| C99 | `IDLE` | `IDLE` | not a transition |\n"
            self.assertTrue(any("in LIFECYCLE.md but not in the code" in p
                                for p in matrix.compare(gen, matrix.documented(extra))))

    def test_the_script_checks_the_repository_document(self):
        self.assertEqual(matrix.main(["--check"]), 0)

    def test_id_matrix_decisions_against_the_manifest(self):
        """ID_MATRIX.md (the owner-confirmed classification) and the manifest agree for every ID: a target is
        IN_SCOPE with a test, a 'stays DEFERRED' ID is DEFERRED, a 'stays OUT_OF_SCOPE' ID is OUT_OF_SCOPE."""
        status = {e["id"]: e["status"] for e in MANIFEST["entries"]}
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in ID_MATRIX.splitlines()
                if ln.startswith("| CT-")]
        self.assertEqual(len(rows), 85)
        self.assertEqual(len({r[0] for r in rows}), 85, "no ID twice")
        targets = 0
        for r in rows:
            ident, decision = r[0], r[5]
            expected = ("IN_SCOPE" if decision.startswith("Target of KOS-MOTION-003")
                        else "OUT_OF_SCOPE" if decision.startswith("Stays OUT_OF_SCOPE") else "DEFERRED")
            targets += expected == "IN_SCOPE"
            self.assertEqual(status[ident], expected, f"{ident}: {decision}")
        self.assertEqual(targets, 55)
        self.assertEqual(sum(v == "IN_SCOPE" for v in status.values()), 39 + 55)   # KOS-MOTION-002's 39 plus 55

    def test_scenario_list_in_the_document(self):
        """The fault-injection scenario set of CT-TMO-07 is listed in LIFECYCLE.md in the order of the code."""
        import scenario_support as X
        listed = [ln.split("|")[2].strip().strip("`") for ln in DOC.splitlines() if ln.startswith("| S") and ln[3:4].isdigit()
                  or (ln.startswith("| S") and ln[3:5].isdigit())]
        self.assertEqual(listed, [sc["name"] for sc in X.SCENARIOS])


if __name__ == "__main__":
    unittest.main()
