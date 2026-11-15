"""The engine hooks of KOS-MOTION-004 (BACKEND.md section 8): execution_rejected, BACKEND_HEALTH_CHANGED and
FEEDBACK_STATUS_CHANGED (finding F-8), update_backend_description and the joint_type view. The 113 earlier
IN_SCOPE tests are the regression run for the rest of the engine. Software evidence only."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "lifecycle"))
import lifecycle_support as S  # noqa: E402


def eng():
    return S.engine_optional_feedback()


def dispatched(e, t=1):
    S.ready(e, t=t)
    r = e.submit(S.vel_cmd(0.1), t)
    return r.command_id, e.command(r.command_id)["backend_reference"]


class TestExecutionRejected(unittest.TestCase):
    def test_a_rejection_ends_a_waiting_command_and_keeps_the_reason(self):
        e = eng()
        cid, ref = dispatched(e)
        r = e.execution_rejected(cid, ref, "SERVO_OFF", 2)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"], c["detail"]),
                         ("FAILED", "BACKEND_REJECTED_DISPATCH", "NONE", "SERVO_OFF"))
        self.assertEqual([ev["event_type"] for ev in r.events if ev["stream"]["kind"] == "command"][0], "COMMAND_STATE_CHANGED")

    def test_the_record_has_no_detail_key_when_none_was_given(self):
        e = eng()
        cid, _ = dispatched(e)
        self.assertNotIn("detail", e.command(cid))

    def test_guards(self):
        e = eng()
        cid, ref = dispatched(e)
        for args, why in (((cid, "other-ref", "x", 2), "reference_mismatch"), (("cmd-99", ref, "x", 2), "unknown_command")):
            r = e.execution_rejected(*args)
            self.assertEqual([x["reason"] for x in r.ignored], [why])
            self.assertEqual(e.command(cid)["state"], "ACCEPTED")
        e.execution_started(cid, ref, 3)
        self.assertEqual([x["reason"] for x in e.execution_rejected(cid, ref, "x", 4).ignored], ["already_started"])
        self.assertEqual(e.command(cid)["state"], "RUNNING")   # a reported start cannot be taken back

    def test_terminating_terminal_and_not_dispatched(self):
        e = eng()
        cid, ref = dispatched(e)
        e.terminate(cid, "CANCEL_REQUESTED", 2)
        self.assertEqual([x["reason"] for x in e.execution_rejected(cid, ref, "x", 3).ignored], ["terminating"])
        e.termination_confirmed(cid, ref, 4)
        self.assertEqual([x["reason"] for x in e.execution_rejected(cid, ref, "x", 5).ignored], ["terminal"])
        S.ready(e, t=6)
        r = e.submit(S.vel_cmd(0.1, client_request_id="req-2"), 6, defer_dispatch=True)
        ref2 = e.command(r.command_id)["backend_reference"]
        self.assertEqual([x["reason"] for x in e.execution_rejected(r.command_id, ref2, "x", 7).ignored], ["not_dispatched"])

    def test_a_late_start_after_a_rejection_is_ignored(self):
        e = eng()
        cid, ref = dispatched(e)
        e.execution_rejected(cid, ref, "x", 2)
        self.assertEqual([x["reason"] for x in e.execution_started(cid, ref, 3).ignored], ["terminal"])


class TestNewEvents(unittest.TestCase):
    def test_backend_health_changed_once_per_change_after_the_joint_events(self):
        e = eng()
        S.ready(e, t=1)
        r = e.backend_health("DEGRADED", 2)
        types = [(ev["stream"]["kind"], ev["event_type"]) for ev in r.events]
        self.assertEqual(types[-1], ("backend", "BACKEND_HEALTH_CHANGED"))
        self.assertEqual(r.events[-1]["data"], {"from": "AVAILABLE", "to": "DEGRADED"})
        self.assertEqual(e.backend_health("DEGRADED", 3).events, [])
        self.assertEqual(e.backend_health("AVAILABLE", 4).events[-1]["data"], {"from": "DEGRADED", "to": "AVAILABLE"})

    def test_feedback_status_changed_when_the_status_changes_and_not_otherwise(self):
        e = eng()
        r = e.status_report("joint-1", "IDLE", 0, 0)
        self.assertNotIn("FEEDBACK_STATUS_CHANGED", [ev["event_type"] for ev in r.events])
        r = e.feedback("joint-1", S.sample(0.0), 1)
        ev = [x for x in r.events if x["event_type"] == "FEEDBACK_STATUS_CHANGED"]
        self.assertEqual([x["data"] for x in ev], [{"joint_id": "joint-1", "from": "MISSING", "to": "VALID"}])
        self.assertEqual(ev[0]["stream"], {"kind": "joint", "id": "joint-1"})
        r = e.feedback("joint-1", S.sample(0.0), 2)
        self.assertNotIn("FEEDBACK_STATUS_CHANGED", [x["event_type"] for x in r.events])
        r = e.tick(300)                                   # older than max_feedback_age_ms (200)
        self.assertEqual([x["data"]["to"] for x in r.events if x["event_type"] == "FEEDBACK_STATUS_CHANGED"
                          and x["data"]["joint_id"] == "joint-1"], ["STALE"])
        r = e.feedback("joint-1", S.sample(0.0, validity="INVALID"), 301)
        self.assertEqual([x["data"]["to"] for x in r.events if x["event_type"] == "FEEDBACK_STATUS_CHANGED"], ["INVALID"])
        self.assertEqual([x for x in e.tick(302).events if x["event_type"] == "FEEDBACK_STATUS_CHANGED"], [])


class TestBackendDescription(unittest.TestCase):
    def test_a_changed_description_affects_later_admissions_only(self):
        e = eng()
        S.ready(e, t=1)
        first = e.submit(S.vel_cmd(0.1), 1)
        self.assertTrue(first.admission.accepted)
        new = copy.deepcopy(S.base.BACKEND)
        new["capabilities"]["supported_modes"] = ["position"]
        e.update_backend_description(new)
        self.assertEqual(e.command(first.command_id)["state"], "ACCEPTED")        # already admitted: unchanged
        later = e.submit(S.vel_cmd(0.1, client_request_id="req-2"), 2)
        self.assertEqual((later.admission.accepted, later.admission.code), (False, "BACKEND_CAPABILITY_UNSUPPORTED"))

    def test_health_is_not_taken_from_the_description(self):
        e = eng()
        S.ready(e, t=1)
        new = copy.deepcopy(S.base.BACKEND)
        new["health"] = "UNAVAILABLE"
        e.update_backend_description(new)
        self.assertEqual(e.joint_state("joint-1", 1)["backend_status"], "AVAILABLE")
        with self.assertRaises(ValueError):
            e.update_backend_description("not a dict")

    def test_joint_type_view(self):
        e = eng()
        self.assertEqual((e.joint_type("joint-1"), e.joint_type("joint-p"), e.joint_type("nope")), ("revolute", "prismatic", None))


if __name__ == "__main__":
    unittest.main()
