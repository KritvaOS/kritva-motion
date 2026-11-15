"""KOS-MOTION-004 (AC-407): tasks/KOS-MOTION-004/ID_MATRIX.md agrees with the conformance manifest.

The matrix lists every ID that was not IN_SCOPE when the task was drafted (11). The test fails when a
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
MATRIX = ROOT / "tasks" / "KOS-MOTION-004" / "ID_MATRIX.md"
MANIFEST = ROOT / "tests" / "manifest" / "conformance_manifest.json"
ROW = re.compile(r"^\| (CT-[A-Z]+-\d+) \| ([A-Z_]+) \| [^|]* \| .* \| ([^|]+) \| ([^|]+) \| (PR-0[2-6]|-) \|$")
DELIVERY_PRS = {"PR-02", "PR-03", "PR-04", "PR-05", "PR-06"}


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


class TestIdMatrix004(unittest.TestCase):
    def test_the_matrix_has_eleven_unique_rows(self):
        rows, dups = matrix_rows()
        self.assertEqual(dups, [])
        self.assertEqual(len(rows), 11)

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
                       if i in rows and s == "IN_SCOPE" and rows[i]["delivery"] not in DELIVERY_PRS)
        self.assertEqual(wrong, [])

    def test_the_targets_are_the_six_backend_ids(self):
        rows, _ = matrix_rows()
        targets = sorted(i for i, r in rows.items() if r["delivery"] in DELIVERY_PRS)
        self.assertEqual(targets, ["CT-BE-01", "CT-BE-02", "CT-BE-03", "CT-BE-04", "CT-BE-06", "CT-BE-07"])

    def test_the_other_ids_stay_deferred(self):
        rows, _ = matrix_rows()
        status = manifest_status()
        wrong = sorted(i for i, r in rows.items() if r["delivery"] == "-" and status[i] != "DEFERRED")
        self.assertEqual(wrong, [])


if __name__ == "__main__":
    unittest.main()
