import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "status"))
import gen_status as g  # noqa: E402

TASKS = """# Tasks
| Task | Title | Status | Milestone | Acceptance |
|---|---|---|---|---|
| KOS-MOTION-001 | Contract | IN_PROGRESS (owner approved) | V2-M1-MOTION-001 | x |
| KOS-MOTION-002 | Validator | NOT_STARTED (approved) | V2-M2-MOTION-001 | y |
| KOS-MOTION-M0-001 | Governance | IN_REVIEW (baselined in v11) | V2-M0-MOTION-001 | z |
| KOS-MOTION-003 | Lifecycle | IN_PROGRESS (approved) | V2-M2-MOTION-002 | w |
"""


def run(cwd, *a):
    subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True)


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        run(self.root, "init", "-q", "-b", "main")
        run(self.root, "config", "user.email", "t@example.com")
        run(self.root, "config", "user.name", "t")
        (self.root / "planning").mkdir()
        (self.root / "planning" / "TASKS.md").write_text(TASKS)
        (self.root / "status").mkdir()
        schema = (ROOT / "status" / "status.schema.json").read_bytes()
        (self.root / "status" / "status.schema.json").write_bytes(schema)
        (self.root / "status" / "status.schema.json.sha256").write_text(hashlib.sha256(schema).hexdigest() + "  status.schema.json\n")
        run(self.root, "add", "-A")
        run(self.root, "commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()


class TestParse(unittest.TestCase):
    def test_rows(self):
        self.assertEqual(g.parse_tasks(TASKS), {"KOS-MOTION-001": "IN_PROGRESS", "KOS-MOTION-002": "NOT_STARTED", "KOS-MOTION-M0-001": "IN_REVIEW", "KOS-MOTION-003": "IN_PROGRESS"})

    def test_duplicate_fails_closed(self):
        with self.assertRaises(g.StatusError):
            g.parse_tasks(TASKS + "| KOS-MOTION-001 | Again | NOT_STARTED | m | a |\n")

    def test_unknown_status_fails_closed(self):
        with self.assertRaises(g.StatusError):
            g.task_record("KOS-MOTION-009", "DONE")

    def test_never_complete_without_accepted(self):
        for word in ("NOT_STARTED", "READY", "IN_PROGRESS", "IN_REVIEW", "CHANGES_REQUESTED", "BLOCKED"):
            self.assertNotEqual(g.task_record("KOS-MOTION-001", word)["execution"], "COMPLETE")


class TestBuild(Repo):
    def test_empty_report_when_no_task_is_reported(self):
        doc = g.build(self.root, [])
        self.assertEqual(doc["tasks"], [])
        self.assertEqual(doc["workstream_id"], "MOTION")
        self.assertEqual(g.validate(doc), [])
        self.assertRegex(doc["source"]["commit"], r"^[0-9a-f]{40}$")

    def test_reported_tasks_and_sync(self):
        doc = g.build(self.root, ["KOS-MOTION-001", "KOS-MOTION-002"])
        self.assertEqual([t["task_id"] for t in doc["tasks"]], ["KOS-MOTION-001", "KOS-MOTION-002"])
        self.assertEqual(doc["tasks"][0]["execution"], "IN_PROGRESS")
        self.assertEqual(doc["tasks"][0]["git_sync"], "NOT_SYNCED")  # no origin/main in the scratch repo
        self.assertEqual(g.validate(doc), [])

    def test_dirty_tree_is_not_committed(self):
        (self.root / "extra.txt").write_text("x")
        doc = g.build(self.root, ["KOS-MOTION-001"])
        self.assertEqual(doc["tasks"][0]["git_sync"], "NOT_COMMITTED")

    def test_missing_task_fails_closed(self):
        with self.assertRaises(g.StatusError):
            g.build(self.root, ["KOS-MOTION-009"])

    def test_evidence_is_criteria_reference_only(self):
        ev = g.build(self.root, ["KOS-MOTION-001"])["tasks"][0]["evidence"][0]
        self.assertIn("not completion proof", ev["description"])
        self.assertIsNone(ev["ci_run"])
        self.assertIsNone(ev["commit"])


class TestAcceptedEvidence(Repo):
    def accept(self, **over):
        head = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        url = "https://github.com/KritvaOS/kritva-motion/actions/runs/123"
        ev = {"type": "software", "uri": url, "description": "secret-scan: PASS", "commit": head,
              "ci_run": url, "report_sha256": None, "result": "PASS"}
        ev.update(over)
        d = self.root / "tasks" / "KOS-MOTION-001"
        d.mkdir(parents=True, exist_ok=True)
        (d / "EVIDENCE.json").write_text(json.dumps({"task_id": "KOS-MOTION-001", "evidence": [ev]}))
        (self.root / "planning" / "TASKS.md").write_text(TASKS.replace("IN_PROGRESS (owner approved)", "ACCEPTED (owner)"))
        run(self.root, "add", "-A")
        run(self.root, "commit", "-q", "-m", "accept")
        return head

    def test_accepted_reports_complete_with_evidence(self):
        self.accept()
        t = g.build(self.root, ["KOS-MOTION-001"])["tasks"][0]
        self.assertEqual(t["execution"], "COMPLETE")
        self.assertEqual(t["evidence"][0]["result"], "PASS")
        self.assertTrue(t["evidence"][0]["ci_run"].endswith("/123"))
        self.assertEqual(g.validate(g.build(self.root, ["KOS-MOTION-001"])), [])

    def test_accepted_without_evidence_file_fails_closed(self):
        (self.root / "planning" / "TASKS.md").write_text(TASKS.replace("IN_PROGRESS (owner approved)", "ACCEPTED (owner)"))
        with self.assertRaises(g.StatusError):
            g.build(self.root, ["KOS-MOTION-001"])

    def test_short_sha_fails_closed(self):
        self.accept(commit="abc")
        with self.assertRaises(g.StatusError):
            g.build(self.root, ["KOS-MOTION-001"])

    def test_non_pass_fails_closed(self):
        self.accept(result="FAIL")
        with self.assertRaises(g.StatusError):
            g.build(self.root, ["KOS-MOTION-001"])

    def test_pass_without_run_url_fails_closed(self):
        self.accept(ci_run=None)
        with self.assertRaises(g.StatusError):
            g.build(self.root, ["KOS-MOTION-001"])

    def test_commit_not_in_history_fails_closed(self):
        self.accept(commit="b" * 40)
        with self.assertRaises(g.StatusError):
            g.build(self.root, ["KOS-MOTION-001"])

    def test_check_detects_evidence_drift(self):
        self.accept()
        doc = g.build(self.root, ["KOS-MOTION-001", "KOS-MOTION-002", "KOS-MOTION-M0-001", "KOS-MOTION-003"])
        (self.root / "status" / "status.json").write_text(json.dumps(doc))
        self.assertEqual(g.check(self.root), [])
        doc["tasks"][0]["evidence"][0]["description"] = "edited"
        (self.root / "status" / "status.json").write_text(json.dumps(doc))
        self.assertTrue(any("differs from tasks/KOS-MOTION-001/EVIDENCE.json" in p for p in g.check(self.root)))


class TestValidate(unittest.TestCase):
    def good(self):
        return {"schema_version": "2.0", "workstream_id": "MOTION", "repo": "KritvaOS/kritva-motion",
                "source": {"branch": "main", "commit": "a" * 40, "tag": None}, "tasks": [],
                "updated_at": "2026-11-04T00:00:00Z"}

    def test_good(self):
        self.assertEqual(g.validate(self.good()), [])

    def test_short_sha(self):
        d = self.good(); d["source"]["commit"] = "abc"
        self.assertTrue(g.validate(d))

    def test_extra_field(self):
        d = self.good(); d["note"] = 1
        self.assertTrue(g.validate(d))

    def test_bad_enum(self):
        d = self.good()
        d["tasks"] = [{"task_id": "T", "execution": "DONE", "git_sync": "SYNCED", "readiness": "IMPLEMENTABLE", "evidence": []}]
        self.assertTrue(g.validate(d))


class TestCheck(Repo):
    def write(self, doc):
        (self.root / "status" / "status.json").write_text(json.dumps(doc))

    def test_default_reports_the_baselined_tasks(self):
        self.assertEqual(g.REPORTED_TASKS, ["KOS-MOTION-001", "KOS-MOTION-002", "KOS-MOTION-M0-001", "KOS-MOTION-003"])
        self.assertEqual([x["task_id"] for x in g.build(self.root)["tasks"]], g.REPORTED_TASKS)

    def test_check_passes_for_generated_report(self):
        self.write(g.build(self.root))
        self.assertEqual(g.check(self.root), [])

    def test_schema_hash_mismatch(self):
        self.write(g.build(self.root))
        (self.root / "status" / "status.schema.json").write_text("{}")
        self.assertTrue(any("SHA-256" in p for p in g.check(self.root)))

    def test_m0_task_in_review_reports_in_progress_without_acceptance(self):
        t = g.build(self.root)["tasks"][2]
        self.assertEqual((t["task_id"], t["execution"]), ("KOS-MOTION-M0-001", "IN_PROGRESS"))

    def test_reported_set_must_match_constant(self):
        self.write(g.build(self.root, ["KOS-MOTION-001"]))
        self.assertTrue(any("REPORTED_TASKS" in p for p in g.check(self.root)))


class TestVendoredSchema(unittest.TestCase):
    def test_recorded_hash_matches(self):
        self.assertIsNone(g.schema_hash_problem(ROOT))


if __name__ == "__main__":
    unittest.main()
