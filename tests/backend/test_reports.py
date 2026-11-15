"""Tests of the backend report and answer records (contract 17.4 and 17.5, KOS-MOTION-004 PR-02).

Records only: what a well-formed report or answer is. How the driver applies them is PR-04. Deterministic,
offline, no clock. Software evidence only.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from kritva_motion.backend import (BACKEND_FAULT_CODES, REPORT_KINDS, DispatchAnswer, Report, ReportError,  # noqa: E402
                                   TerminationAnswer, make_report, validate_report)

REF = "ref-1"
TARGET = {"type": "joint", "id": "j1"}
FEEDBACK = {"validity": "VALID", "measured_position": 0.5, "measured_velocity": 0.0, "backend_timestamp": 12.5,
            "clock_domain": "backend-monotonic", "clock_synchronized": False}


class TestReports(unittest.TestCase):
    def test_the_kinds_are_the_contract_names_and_there_is_no_termination_unconfirmed(self):
        self.assertEqual(set(REPORT_KINDS), {"execution_started", "execution_rejected", "termination_confirmed", "hold_confirmed",
                                             "hold_released", "hold_release_failed", "feedback", "health", "fault", "fault_cleared"})
        self.assertNotIn("termination_unconfirmed", REPORT_KINDS)   # Motion decides it (17.5)
        self.assertNotIn("termination_request_accepted", REPORT_KINDS)   # that is an answer, not a report

    def test_each_kind_can_be_built_well_formed(self):
        make_report("execution_started", backend_reference=REF)
        make_report("execution_rejected", backend_reference=REF, reason="BUSY")
        make_report("termination_confirmed", backend_reference=REF, target=TARGET)
        make_report("hold_confirmed", backend_reference=REF)
        make_report("hold_released", backend_reference=REF)
        make_report("hold_release_failed", backend_reference=REF)
        make_report("feedback", joint_id="j1", record=FEEDBACK)
        make_report("health", health="DEGRADED")
        make_report("fault", code="BACKEND_COMMUNICATION_LOSS", joints=("j1",))
        make_report("fault_cleared")

    def test_an_execution_report_needs_the_backend_reference(self):
        for kind in ("execution_started", "hold_confirmed", "hold_released", "hold_release_failed"):
            with self.subTest(kind):
                self.assertEqual([p.path for p in validate_report(Report(kind))], ["backend_reference"])

    def test_a_termination_confirmation_is_bound_to_reference_and_target(self):
        self.assertEqual([p.path for p in validate_report(Report("termination_confirmed", backend_reference=REF))], ["target"])
        self.assertEqual([p.path for p in validate_report(Report("termination_confirmed", target=TARGET))], ["backend_reference"])
        self.assertTrue(validate_report(Report("termination_confirmed", backend_reference=REF, target={"type": "robot", "id": "r"})))

    def test_a_rejection_names_its_reason(self):
        self.assertEqual([p.path for p in validate_report(Report("execution_rejected", backend_reference=REF))], ["reason"])

    def test_feedback_record_rules(self):
        bad = dict(FEEDBACK, validity="OK")
        self.assertIn("record.validity", [p.path for p in validate_report(Report("feedback", joint_id="j1", record=bad))])
        bad = dict(FEEDBACK, measured_position=None)
        self.assertIn("record.measured_position", [p.path for p in validate_report(Report("feedback", joint_id="j1", record=bad))])
        bad = dict(FEEDBACK, clock_synchronized="no")
        self.assertIn("record.clock_synchronized", [p.path for p in validate_report(Report("feedback", joint_id="j1", record=bad))])
        invalid = dict(FEEDBACK, validity="INVALID", measured_position=None)
        self.assertEqual(validate_report(Report("feedback", joint_id="j1", record=invalid)), [])   # an INVALID record is a legal report
        self.assertIn("joint_id", [p.path for p in validate_report(Report("feedback", record=FEEDBACK))])

    def test_health_and_fault_codes_are_the_contract_values(self):
        self.assertTrue(validate_report(Report("health", health="READY")))
        self.assertTrue(validate_report(Report("fault", code="MOTOR_JAMMED")))
        self.assertTrue(validate_report(Report("fault_cleared", code="MOTOR_JAMMED")))
        self.assertEqual(set(BACKEND_FAULT_CODES), {"BACKEND_UNAVAILABLE", "BACKEND_COMMUNICATION_LOSS", "BACKEND_EXECUTION_FAILURE"})

    def test_joints_is_a_tuple_of_ids_or_none(self):
        self.assertTrue(validate_report(Report("fault", code="BACKEND_UNAVAILABLE", joints=["j1"])))
        self.assertTrue(validate_report(Report("fault", code="BACKEND_UNAVAILABLE", joints=("bad id",))))
        self.assertEqual(validate_report(Report("fault", code="BACKEND_UNAVAILABLE", joints=None)), [])

    def test_unknown_kind_and_not_a_report(self):
        self.assertTrue(validate_report(Report("teleport")))
        self.assertTrue(validate_report({"kind": "feedback"}))

    def test_make_report_raises_with_every_problem(self):
        with self.assertRaises(ReportError) as ctx:
            make_report("termination_confirmed")
        self.assertEqual(sorted(p.path for p in ctx.exception.problems), ["backend_reference", "target"])

    def test_a_report_is_immutable(self):
        r = make_report("execution_started", backend_reference=REF)
        with self.assertRaises(Exception):
            r.kind = "feedback"

    def test_a_simulated_report_says_so(self):
        self.assertTrue(make_report("execution_started", backend_reference=REF, simulated=True).simulated)
        self.assertFalse(make_report("execution_started", backend_reference=REF).simulated)


class TestAnswers(unittest.TestCase):
    def test_dispatch_accepted_carries_a_reference_and_no_reason(self):
        a = DispatchAnswer(True, backend_reference=REF)
        self.assertTrue(a.accepted)
        for kwargs in ({"accepted": True}, {"accepted": True, "backend_reference": REF, "reason": "x"}):
            with self.subTest(kwargs), self.assertRaises(ReportError):
                DispatchAnswer(**kwargs)

    def test_dispatch_rejected_carries_a_reason_and_no_reference(self):
        self.assertFalse(DispatchAnswer(False, reason="BUSY").accepted)
        for kwargs in ({"accepted": False}, {"accepted": False, "reason": "x", "backend_reference": REF}):
            with self.subTest(kwargs), self.assertRaises(ReportError):
                DispatchAnswer(**kwargs)

    def test_termination_request_accepted_is_not_a_confirmation(self):
        a = TerminationAnswer(True)
        self.assertTrue(a.accepted)
        self.assertFalse(hasattr(a, "confirmed"))   # the answer has no confirmation field: 17.5 keeps them apart
        self.assertFalse(TerminationAnswer(False, reason="NOT_SUPPORTED").accepted)
        for kwargs in ({"accepted": False}, {"accepted": True, "reason": "x"}):
            with self.subTest(kwargs), self.assertRaises(ReportError):
                TerminationAnswer(**kwargs)


if __name__ == "__main__":
    unittest.main()
