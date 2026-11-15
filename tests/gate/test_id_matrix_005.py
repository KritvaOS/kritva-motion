"""KOS-MOTION-005 (AC-506): tasks/KOS-MOTION-005/ID_MATRIX.md agrees with the conformance manifest.

The matrix lists every ID that was not IN_SCOPE when the task was drafted (30). The test fails when a
manifest ID that is not IN_SCOPE is missing from the matrix, when a matrix ID is not in the manifest, when an
ID is listed twice, when the row count changes, or when an ID that is IN_SCOPE in the manifest is not a
target of a delivery PR (so a status change in the manifest never needs an edit of the matrix, but an
unplanned one is caught). Software evidence only.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tasks" / "KOS-MOTION-005" / "ID_MATRIX.md"
MANIFEST = ROOT / "tests" / "manifest" / "conformance_manifest.json"
ROW = re.compile(r"^\| (CT-[A-Z]+-\d+) \| ([A-Z_]+) \| [^|]* \| .* \| ([^|]+) \| ([^|]+) \| (PR-0[2-6]|-) \|$")
DELIVERY_PRS = {"PR-02", "PR-03", "PR-04", "PR-05", "PR-06"}
# IDs this matrix left OUT_OF_SCOPE "(candidate KOS-MOTION-004)" that KOS-MOTION-004 has delivered; its own
# ID_MATRIX.md and tests/gate/test_id_matrix_004.py carry them. Each KOS-MOTION-004 pull request adds its IDs.
DELIVERED_BY_004 = {"CT-BE-01", "CT-BE-02", "CT-BE-03", "CT-BE-04", "CT-BE-06", "CT-BE-07"}


def matrix_rows():
    rows, dups = {}, []
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            if m.group(1) in rows:
                dups.append(m.group(1))
            rows[m.group(1)] = {"status_then": m.group(2), "delivery": m.group(5)}
    return rows, dups


def manifest_status():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {e["id"]: e["status"] for e in data["entries"]}


class TestIdMatrix005(unittest.TestCase):
    def test_the_matrix_has_thirty_unique_rows(self):
        rows, dups = matrix_rows()
        self.assertEqual(dups, [])
        self.assertEqual(len(rows), 30)

    def test_every_matrix_id_is_in_the_manifest(self):
        rows, _ = matrix_rows()
        self.assertEqual(sorted(set(rows) - set(manifest_status())), [])

    def test_every_manifest_id_that_is_not_in_scope_is_in_the_matrix(self):
        rows, _ = matrix_rows()
        missing = sorted(i for i, s in manifest_status().items() if s != "IN_SCOPE" and i not in rows)
        self.assertEqual(missing, [])

    def test_an_id_that_is_in_scope_now_is_a_target_of_a_delivery_pr(self):
        rows, _ = matrix_rows()
        wrong = sorted(i for i, s in manifest_status().items()
                       if i in rows and s == "IN_SCOPE" and rows[i]["delivery"] not in DELIVERY_PRS
                       and i not in DELIVERED_BY_004)
        self.assertEqual(wrong, [])

    def test_the_targets_are_at_most_nineteen_and_at_least_eighteen(self):
        rows, _ = matrix_rows()
        targets = [i for i, r in rows.items() if r["delivery"] in DELIVERY_PRS]
        self.assertIn(len(targets), (18, 19))   # CT-DET-02 may return to DEFERRED (question Q-4)


if __name__ == "__main__":
    unittest.main()
