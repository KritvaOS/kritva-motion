"""Tests of the command history (contract 15 and 7.3), KOS-MOTION-005 PR-04.

CT_LC_05 and CT_HIS_01 are the single executable tests named by the IN_SCOPE manifest entries for those
IDs (method name = ID with hyphens replaced by underscores). The other classes are negative cases.
Deterministic and offline; time is the injected monotonic reading. Software evidence only, never
physical or safety validation.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "lifecycle"))
import lifecycle_support as S  # noqa: E402
from kritva_motion.lifecycle import LifecycleEngine  # noqa: E402
from kritva_motion.stores import (CommandHistory, ConfigurationRegistry, Coordinator,  # noqa: E402
                                  IdempotencyStore)

A = "client-A"
FIELDS_15_1 = ("client_id", "client_request_id", "command_id", "operation", "target", "submitted_at",
               "accepted_at", "execution_started_at", "completed_at", "lifecycle_history", "validation_result",
               "result", "fault_references", "backend_reference", "config_version", "config_digest",
               "authorization_outcome", "deadline_ms", "execution_timeout_ms")


def setup(history_retention=100000):
    e = LifecycleEngine(None, copy.deepcopy(S.base.BACKEND), None)
    store, hist = IdempotencyStore(20000), CommandHistory(history_retention)
    assert ConfigurationRegistry(e, S.base.CAPS, store).activate(copy.deepcopy(S.base.CONFIG), 0)["outcome"] == "ACTIVATED"
    S.ready(e, "joint-1", t=0)
    S.ready(e, "joint-p", t=0)
    return e, Coordinator(e, store, hist), hist


def run_to_completion(e, co):
    r = co.submit(A, S.pos_cmd(0.5), 10, "2026-11-15T00:00:10Z")
    cid = r.command_id
    co.observe(e.execution_started(cid, e.command(cid)["backend_reference"], 20, "2026-11-15T00:00:20Z"))
    co.observe(e.feedback("joint-1", S.sample(0.5), 30, "2026-11-15T00:00:30Z"))
    co.observe(e.feedback("joint-1", S.sample(0.5), 130, "2026-11-15T00:00:40Z"))
    assert e.command(cid)["state"] == "COMPLETED"
    return cid


class TestHistoryConformance(unittest.TestCase):
    def test_CT_LC_05(self):
        """A rejected submission has no command_id and no lifecycle, and appears in history (7.3, 15)."""
        e, co, hist = setup()
        r = co.submit(A, S.pos_cmd(5.0), 10, "2026-11-15T00:00:10Z")
        self.assertFalse(r.admission.accepted)
        self.assertIsNone(r.command_id)
        self.assertEqual(e.commands(), [])
        recs = hist.read()
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec["submission_result"], "REJECTED")
        self.assertIsNone(rec["command_id"])
        self.assertIsNone(rec["lifecycle_history"])
        self.assertEqual(rec["validation_result"]["code"], "LIMIT_POSITION")
        self.assertEqual(rec["result"], {"state": "REJECTED", "code": "LIMIT_POSITION"})
        self.assertEqual((rec["client_id"], rec["client_request_id"], rec["submitted_at"]),
                         (A, "req-1", "2026-11-15T00:00:10Z"))
        self.assertEqual(hist.accepted(), [])
        again = co.submit(A, S.pos_cmd(5.0), 20, "2026-11-15T00:00:20Z")    # the same rejection on replay (7.3)
        self.assertTrue(again.admission.replay)
        self.assertEqual(again.admission.code, "LIMIT_POSITION")
        self.assertEqual(len(hist.read()), 1)                                # not a new record
        self.assertEqual(hist.read()[0]["replays"][0]["at"], "2026-11-15T00:00:20Z")
        with self.assertRaises(ValueError):
            hist.append_submission({"submission_result": "REJECTED", "command_id": "cmd-9"}, 30)

    def test_CT_HIS_01(self):
        """History retains every field of 15.1, distinguishes rejected from accepted and never overwrites (15)."""
        e, co, hist = setup()
        bad = co.submit(A, S.pos_cmd(5.0, client_request_id="req-bad"), 5, "2026-11-15T00:00:05Z")
        cid = run_to_completion(e, co)
        rec = hist.get(cid)
        for f in FIELDS_15_1:
            self.assertIn(f, rec, f)
        self.assertEqual((rec["submission_result"], rec["command_id"], rec["operation"], rec["client_id"]),
                         ("ACCEPTED", cid, "SET_POSITION", A))
        self.assertEqual(rec["target"], {"type": "joint", "id": "joint-1"})
        self.assertEqual((rec["submitted_at"], rec["accepted_at"]), ("2026-11-15T00:00:10Z",) * 2)
        self.assertEqual((rec["execution_started_at"], rec["completed_at"]),
                         ("2026-11-15T00:00:20Z", "2026-11-15T00:00:40Z"))
        self.assertEqual(rec["result"], {"state": "COMPLETED", "reason_code": "GOAL_REACHED"})
        # one entry per state change and per phase change the engine reported, in order
        self.assertEqual([(x["state"], x["phase"], x["reason_code"]) for x in rec["lifecycle_history"]],
                         [("ACCEPTED", "NONE", None), ("ACCEPTED", "DISPATCH_PENDING", None), ("RUNNING", "NONE", None),
                          ("RUNNING", "NONE", None), ("COMPLETED", "NONE", "GOAL_REACHED")])
        self.assertTrue(all({"state", "phase", "reason_code", "at"} <= set(x) for x in rec["lifecycle_history"]))
        self.assertEqual(rec["backend_reference"], e.command(cid)["backend_reference"])
        self.assertEqual((rec["config_version"], rec["config_digest"]),
                         (e.command(cid)["config_version"], e.command(cid)["config_digest"]))
        self.assertEqual(rec["authorization_outcome"], {"identity": "VALID", "permission_granted": True})
        self.assertEqual((rec["deadline_ms"], rec["execution_timeout_ms"]), (10000, 5000))
        self.assertEqual(rec["fault_references"], [])
        # accepted and rejected are kept apart
        self.assertEqual([r["submission_result"] for r in hist.read()], ["REJECTED", "ACCEPTED"])
        self.assertEqual(len(hist.accepted()), 1)
        self.assertEqual(len(hist.rejected()), 1)
        # no earlier entry is ever overwritten
        before = copy.deepcopy(hist.read())
        co.submit(A, S.pos_cmd(0.4, client_request_id="req-2"), 200, "2026-11-15T00:01:00Z")
        co.submit(A, S.pos_cmd(5.0, client_request_id="req-bad"), 201, "2026-11-15T00:01:01Z")   # a replay
        after = hist.read()
        self.assertEqual(after[0]["validation_result"], before[0]["validation_result"])
        self.assertEqual(after[1]["lifecycle_history"], before[1]["lifecycle_history"])
        self.assertEqual({k: v for k, v in after[1].items() if k != "replays"},
                         {k: v for k, v in before[1].items() if k != "replays"})
        self.assertFalse(any(n in dir(hist) for n in ("update", "overwrite", "delete", "remove", "set", "clear")))
        self.assertIsNotNone(bad.admission.code)


class TestHistoryNegativeCases(unittest.TestCase):
    def test_authorization_outcome_is_recorded_as_supplied(self):
        e, co, hist = setup()
        co.submit(A, S.pos_cmd(0.5), 10, "t1", permission_granted=False)
        co.submit(A, S.pos_cmd(0.5, client_request_id="req-2"), 11, "t2", identity="EXPIRED")
        outs = [r["authorization_outcome"] for r in hist.read()]
        self.assertEqual(outs, [{"identity": "VALID", "permission_granted": False},
                                {"identity": "EXPIRED", "permission_granted": True}])
        self.assertEqual([r["validation_result"]["code"] for r in hist.read()], ["PERMISSION_DENIED", "UNAUTHENTICATED"])

    def test_a_conflict_is_its_own_rejected_record(self):
        e, co, hist = setup()
        co.submit(A, S.pos_cmd(0.5), 10, "t1")
        co.submit(A, S.pos_cmd(0.4), 11, "t2")
        recs = hist.read()
        self.assertEqual([r["submission_result"] for r in recs], ["ACCEPTED", "REJECTED"])
        self.assertEqual(recs[1]["validation_result"]["code"], "REQUEST_ID_CONFLICT")

    def test_an_identical_replay_adds_no_record_and_one_marker(self):
        e, co, hist = setup()
        r1 = co.submit(A, S.pos_cmd(0.5), 10, "t1")
        co.submit(A, S.pos_cmd(0.5), 11, "t2")
        co.submit(A, S.pos_cmd(0.5), 12, "t3")
        self.assertEqual(len(hist.read()), 1)
        self.assertEqual([x["at"] for x in hist.get(r1.command_id)["replays"]], ["t2", "t3"])

    def test_fault_reference_is_appended_once(self):
        e, co, hist = setup()
        r = co.submit(A, S.vel_cmd(0.1, jid="joint-1", unit="rad/s"), 10, "t1")
        cid = r.command_id
        co.observe(e.execution_started(cid, e.command(cid)["backend_reference"], 11, "t2"))
        res = e.joint_fault("joint-1", "TRACKING_ERROR", 12, "t3")
        co.observe(res)
        co.observe(res)
        refs = hist.get(cid)["fault_references"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs, [e.faults("joint-1")[0]["fault_id"]])

    def test_retention_drops_whole_old_records_but_keeps_open_commands(self):
        e, co, hist = setup(history_retention=1000)
        co.submit(A, S.pos_cmd(5.0, client_request_id="rej"), 10, "t1")           # rejected
        r = co.submit(A, S.pos_cmd(0.5, client_request_id="open"), 11, "t2")      # accepted, not terminal
        self.assertEqual(hist.purge(500), [])
        self.assertEqual(hist.purge(2000), [1])                                    # the old rejection goes
        self.assertEqual([x["command_id"] for x in hist.read()], [r.command_id])   # the open command stays
        self.assertEqual(hist.purge(10 ** 6), [])

    def test_bad_retention_and_double_accept_are_refused(self):
        for bad in (0, -5, None, True):
            with self.assertRaises(ValueError):
                CommandHistory(bad)
        h = CommandHistory(10)
        rec = {"submission_result": "ACCEPTED", "command_id": "cmd-1", "validation_result": {"accepted": True}}
        h.append_submission(rec, 0)
        with self.assertRaises(ValueError):
            h.append_submission(rec, 1)

    def test_reads_return_copies(self):
        e, co, hist = setup()
        r = co.submit(A, S.pos_cmd(0.5), 10, "t1")
        got = hist.get(r.command_id)
        got["lifecycle_history"].append({"state": "TAMPERED"})
        got["target"]["id"] = "x"
        self.assertEqual(len(hist.get(r.command_id)["lifecycle_history"]), 2)
        self.assertEqual(hist.get(r.command_id)["target"]["id"], "joint-1")


if __name__ == "__main__":
    unittest.main()
