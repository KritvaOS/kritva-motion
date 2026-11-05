"""Tests for the configuration validator (AC-201; conformance IDs CT-CFG-02, CT-CFG-07, CT-CFG-08).

Fixtures are plain data. The tests are deterministic and offline. Passing them is software evidence
only, never physical or safety validation.
"""
import ast
import copy
import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from kritva_motion import config_validation as cv  # noqa: E402


def joint(**over):
    j = {
        "joint_id": "joint-1", "name": "Shoulder", "joint_type": "revolute", "positive_direction": "counter-clockwise",
        "position_min": -1.5, "position_max": 1.5, "velocity_max": 1.0, "acceleration_max": 2.0,
        "modes": ["position", "velocity"], "max_feedback_age_ms": 200, "feedback_required": True,
        "feedback_timeout_policy": "STOP_AND_FAULT", "termination_confirm_timeout_ms": 1000,
        "degradation_policy": {"BACKEND_DEGRADED": ["SET_VELOCITY"]},
        "position_tolerance": 0.01, "settling_duration_ms": 100,
        "default_execution_timeout_ms": 5000, "default_deadline_ms": 10000,
        "fault_clearance": {"FEEDBACK_LOST": "CLIENT_AUTHORIZED", "TRACKING_ERROR": "HUMAN_REQUIRED"},
    }
    j.update(over)
    return j


def config(*joints, **over):
    c = {"config_version": "1", "joints": list(joints) or [joint()]}
    c.update(over)
    return c


def caps(**over):
    c = {"controlled_stop": True, "position_hold": True,
         "supported_modes": ["position", "velocity"], "supported_joint_types": ["revolute", "prismatic"]}
    c.update(over)
    return c


def rules(result):
    return [v.rule for v in result.violations]


def drop(j, *keys):
    j = copy.deepcopy(j)
    for k in keys:
        j.pop(k)
    return j


class TestValid(unittest.TestCase):
    def test_valid_configuration(self):
        r = cv.validate_configuration(config(), caps())
        self.assertTrue(r.valid)
        self.assertEqual(r.violations, ())

    def test_valid_continuous_velocity_joint(self):
        j = drop(joint(continuous=True, modes=["velocity"]), "position_min", "position_max")
        self.assertTrue(cv.validate_configuration(config(j), caps()).valid)

    def test_valid_prismatic_joint_and_degrade_with_optional_feedback(self):
        j = joint(joint_type="prismatic", feedback_required=False, feedback_timeout_policy="DEGRADE",
                  degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_VELOCITY"]})
        self.assertTrue(cv.validate_configuration(config(j), caps()).valid)

    def test_optional_fields_may_be_absent(self):
        j = drop(joint(), "acceleration_max", "degradation_policy", "fault_clearance")
        self.assertTrue(cv.validate_configuration(config(j), caps()).valid)

    def test_boundary_values_are_accepted(self):
        self.assertTrue(cv.validate_configuration(config(joint(settling_duration_ms=0)), caps()).valid)


class TestPolicyRules(unittest.TestCase):
    """AC-201 named cases."""

    def test_unknown_feedback_timeout_policy(self):  # CT-CFG-07
        r = cv.validate_configuration(config(joint(feedback_timeout_policy="IGNORE")), caps())
        self.assertEqual(rules(r), ["CFG_UNKNOWN_POLICY"])
        self.assertEqual(r.violations[0].path, "joints[0].feedback_timeout_policy")

    def test_hold_is_never_a_feedback_loss_response(self):
        r = cv.validate_configuration(config(joint(feedback_timeout_policy="HOLD")), caps())
        self.assertEqual(rules(r), ["CFG_UNKNOWN_POLICY"])
        self.assertIn("HOLD", r.violations[0].message)

    def test_unknown_clearance_value_and_fault_code(self):
        j = joint(fault_clearance={"FEEDBACK_LOST": "ANYONE", "bad code": "HUMAN_REQUIRED"})
        r = cv.validate_configuration(config(j), caps())
        self.assertEqual(sorted(rules(r)), ["CFG_BAD_ID", "CFG_UNKNOWN_POLICY"])

    def test_unknown_degradation_reason_and_operation(self):
        j = joint(degradation_policy={"WEATHER": ["SET_VELOCITY"], "BACKEND_DEGRADED": ["JUMP"]})
        r = cv.validate_configuration(config(j), caps())
        self.assertEqual(rules(r), ["CFG_UNKNOWN_POLICY", "CFG_UNKNOWN_POLICY"] if False else ["CFG_UNKNOWN_POLICY"] * 2)

    def test_continuous_joint_with_position_mode(self):  # CT-CFG-07
        j = drop(joint(continuous=True), "position_min", "position_max")
        r = cv.validate_configuration(config(j), caps())
        self.assertEqual(rules(r), ["CFG_CONTINUOUS_POSITION_MODE"])

    def test_degrade_with_feedback_required(self):
        r = cv.validate_configuration(config(joint(feedback_timeout_policy="DEGRADE", feedback_required=True)), caps())
        self.assertEqual(rules(r), ["CFG_DEGRADE_FEEDBACK_REQUIRED"])

    def test_degradation_policy_lists_set_position_for_optional_feedback(self):  # CT-CFG-08
        j = joint(degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_POSITION"]})
        r = cv.validate_configuration(config(j), caps())
        self.assertEqual(rules(r), ["CFG_DEGRADATION_UNSAFE_OPERATION"])

    def test_degradation_policy_lists_hold_for_optional_feedback(self):  # CT-CFG-08
        j = joint(degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["HOLD"]})
        self.assertEqual(rules(cv.validate_configuration(config(j), caps())), ["CFG_DEGRADATION_UNSAFE_OPERATION"])

    def test_set_position_is_allowed_for_backend_degraded(self):
        j = joint(degradation_policy={"BACKEND_DEGRADED": ["SET_POSITION", "SET_VELOCITY", "HOLD"]})
        self.assertTrue(cv.validate_configuration(config(j), caps()).valid)

    def test_stop_and_fault_without_controlled_stop(self):  # CT-CFG-07
        r = cv.validate_configuration(config(), caps(controlled_stop=False))
        self.assertEqual(rules(r), ["CFG_BACKEND_CANNOT_SATISFY"])

    def test_degrade_does_not_need_controlled_stop(self):
        j = joint(feedback_required=False, feedback_timeout_policy="DEGRADE", degradation_policy={})
        self.assertTrue(cv.validate_configuration(config(j), caps(controlled_stop=False)).valid)

    def test_mode_and_joint_type_the_backend_does_not_support(self):
        r = cv.validate_configuration(config(), caps(supported_modes=["velocity"], supported_joint_types=["prismatic"]))
        self.assertEqual(sorted(rules(r)), ["CFG_BACKEND_CANNOT_SATISFY"] * 2)

    def test_hold_listed_without_backend_hold_support(self):
        j = joint(degradation_policy={"BACKEND_DEGRADED": ["HOLD"]})
        self.assertEqual(rules(cv.validate_configuration(config(j), caps(position_hold=False))), ["CFG_BACKEND_CANNOT_SATISFY"])


class TestCompletenessAndConsistency(unittest.TestCase):  # CT-CFG-02
    def test_each_required_joint_field_is_required(self):
        for f in cv.JOINT_REQUIRED:
            with self.subTest(field=f):
                r = cv.validate_configuration(config(drop(joint(), f)), caps())
                self.assertIn("CFG_MISSING_FIELD", rules(r))
                self.assertIn(f"joints[0].{f}", [v.path for v in r.violations])

    def test_missing_top_level_fields(self):
        r = cv.validate_configuration({}, caps())
        self.assertEqual(rules(r), ["CFG_MISSING_FIELD"] * 2)

    def test_unknown_fields_are_refused(self):
        r = cv.validate_configuration(config(joint(feedback_requierd=True), surprise=1), caps())
        self.assertEqual(sorted(rules(r)), ["CFG_UNKNOWN_FIELD"] * 2)

    def test_position_limits_required_unless_continuous(self):
        r = cv.validate_configuration(config(drop(joint(), "position_min", "position_max")), caps())
        self.assertEqual(rules(r), ["CFG_POSITION_LIMITS"])

    def test_position_min_must_be_below_position_max(self):
        for lo, hi in ((1.0, 1.0), (2.0, 1.0)):
            with self.subTest(lo=lo, hi=hi):
                r = cv.validate_configuration(config(joint(position_min=lo, position_max=hi)), caps())
                self.assertEqual(rules(r), ["CFG_POSITION_LIMITS"])

    def test_continuous_rules(self):
        r = cv.validate_configuration(config(joint(continuous=True, modes=["velocity"])), caps())
        self.assertEqual(rules(r), ["CFG_CONTINUOUS"])  # still carries position limits
        r = cv.validate_configuration(config(drop(joint(continuous=True, joint_type="prismatic", modes=["velocity"]), "position_min", "position_max")), caps())
        self.assertEqual(rules(r), ["CFG_CONTINUOUS"])
        r = cv.validate_configuration(config(joint(continuous="yes")), caps())
        self.assertIn("CFG_BAD_VALUE", rules(r))

    def test_non_finite_and_non_numeric_values(self):
        for bad in (math.nan, math.inf, -math.inf, "1", True, None):
            with self.subTest(bad=repr(bad)):
                r = cv.validate_configuration(config(joint(velocity_max=bad)), caps())
                self.assertEqual(rules(r), ["CFG_BAD_VALUE"])

    def test_non_positive_numbers(self):
        for field in ("velocity_max", "acceleration_max", "position_tolerance"):
            for bad in (0, -1):
                with self.subTest(field=field, bad=bad):
                    r = cv.validate_configuration(config(joint(**{field: bad})), caps())
                    self.assertEqual(rules(r), ["CFG_BAD_VALUE"])

    def test_durations_are_positive_integers(self):
        for field in ("max_feedback_age_ms", "termination_confirm_timeout_ms", "default_execution_timeout_ms", "default_deadline_ms"):
            for bad in (0, -5, 1.5, "10", True):
                with self.subTest(field=field, bad=bad):
                    r = cv.validate_configuration(config(joint(**{field: bad})), caps())
                    self.assertEqual(rules(r), ["CFG_BAD_VALUE"])
        self.assertEqual(rules(cv.validate_configuration(config(joint(settling_duration_ms=-1)), caps())), ["CFG_BAD_VALUE"])

    def test_identifiers_and_duplicates(self):
        for bad in ("", "has space", "x" * 129, 5):
            with self.subTest(bad=bad):
                self.assertEqual(rules(cv.validate_configuration(config(joint(joint_id=bad)), caps())), ["CFG_BAD_ID"])
        r = cv.validate_configuration(config(joint(), joint()), caps())
        self.assertEqual(rules(r), ["CFG_DUPLICATE_JOINT"])
        self.assertEqual(r.violations[0].path, "joints[1].joint_id")

    def test_empty_or_wrong_typed_structures(self):
        self.assertEqual(rules(cv.validate_configuration(config(joints=[]), caps())), ["CFG_BAD_VALUE"])
        self.assertEqual(rules(cv.validate_configuration({"config_version": "1", "joints": [5]}, caps())), ["CFG_BAD_VALUE"])
        self.assertEqual(rules(cv.validate_configuration([], caps())), ["CFG_BAD_VALUE"])
        self.assertEqual(rules(cv.validate_configuration(config(config_version=""), caps())), ["CFG_BAD_VALUE"])

    def test_bad_modes_and_joint_type(self):
        for bad in ([], ["position", "position"], ["jog"], "position"):
            with self.subTest(bad=bad):
                self.assertEqual(rules(cv.validate_configuration(config(joint(modes=bad)), caps())), ["CFG_UNKNOWN_VALUE"])
        self.assertEqual(rules(cv.validate_configuration(config(joint(joint_type="spherical")), caps())), ["CFG_UNKNOWN_VALUE"])

    def test_bad_capabilities(self):
        for bad in (None, {}, caps(controlled_stop="yes"), caps(supported_modes=["jog"]), dict(caps(), extra=1)):
            with self.subTest(bad=repr(bad)[:40]):
                self.assertIn("CFG_CAPABILITIES_INVALID", rules(cv.validate_configuration(config(), bad)))

    def test_missing_capabilities_do_not_hide_other_violations(self):
        r = cv.validate_configuration(config(joint(feedback_timeout_policy="IGNORE")), None)
        self.assertEqual(sorted(rules(r)), ["CFG_CAPABILITIES_INVALID", "CFG_UNKNOWN_POLICY"])


class TestSeveralViolationsAndDeterminism(unittest.TestCase):
    def test_several_violations_are_all_reported_in_a_fixed_order(self):
        j0 = joint(feedback_timeout_policy="DEGRADE", feedback_required=True, velocity_max=-1)
        j1 = drop(joint(joint_id="joint-2", continuous=True), "position_min", "position_max")  # position mode listed
        j1["degradation_policy"] = {"FEEDBACK_OPTIONAL_UNAVAILABLE": ["HOLD"]}
        r = cv.validate_configuration(config(j0, j1), caps())
        self.assertFalse(r.valid)
        self.assertEqual([(v.path.split(".")[0], v.rule) for v in r.violations], [
            ("joints[0]", "CFG_BAD_VALUE"),
            ("joints[0]", "CFG_DEGRADE_FEEDBACK_REQUIRED"),
            ("joints[1]", "CFG_CONTINUOUS_POSITION_MODE"),
            ("joints[1]", "CFG_DEGRADATION_UNSAFE_OPERATION"),
        ])

    def test_same_input_gives_the_same_result(self):
        c = config(joint(feedback_timeout_policy="IGNORE", fault_clearance={"X1": "NO", "A1": "NO"}))
        self.assertEqual(cv.validate_configuration(c, caps()), cv.validate_configuration(c, caps()))

    def test_inputs_are_not_modified(self):
        c, k = config(joint(feedback_timeout_policy="IGNORE")), caps()
        c0, k0 = copy.deepcopy(c), copy.deepcopy(k)
        cv.validate_configuration(c, k)
        self.assertEqual((c, k), (c0, k0))

    def test_every_violation_names_a_contract_section_and_a_path(self):
        r = cv.validate_configuration(config(joint(feedback_timeout_policy="IGNORE", velocity_max=0)), None)
        for v in r.violations:
            self.assertTrue(v.section and v.path and v.message)

    def test_result_is_json_friendly_data(self):
        r = cv.validate_configuration(config(joint(feedback_timeout_policy="IGNORE")), caps())
        json.dumps([v.__dict__ for v in r.violations])


class TestNoIo(unittest.TestCase):
    """AC-207 in part: the validator imports only the standard library and performs no I/O."""

    def test_imports_and_calls(self):
        tree = ast.parse((ROOT / "src" / "kritva_motion" / "config_validation.py").read_text(encoding="utf-8"))
        imported = set()
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.add(node.func.id)
        self.assertEqual(imported, {"math", "re", "dataclasses"})
        self.assertFalse(calls & {"open", "print", "input", "exec", "eval", "__import__"})


if __name__ == "__main__":
    unittest.main()
