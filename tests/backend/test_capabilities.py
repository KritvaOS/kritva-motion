"""Tests of the capability declaration validator (contract 17.2, KOS-MOTION-004 PR-02).

The validator is the instrument CT-BE-01 will use (the simulator's own declaration is checked in PR-03); this PR
checks the validator itself: it accepts a complete declaration and names every missing or malformed item with its
path, never stops at the first and never fills a default. Deterministic and offline. Software evidence only.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kritva_motion.backend import is_conforming, validate_declaration  # noqa: E402
from support import good_declaration  # noqa: E402


def paths(decl):
    return sorted(p.path for p in validate_declaration(decl))


def without(decl, *keys):
    d = copy.deepcopy(decl)
    node = d
    for k in keys[:-1]:
        node = node[k]
    del node[keys[-1]]
    return d


class TestCompleteDeclaration(unittest.TestCase):
    def test_a_complete_declaration_has_no_problem(self):
        self.assertEqual(validate_declaration(good_declaration()), [])
        self.assertTrue(is_conforming(good_declaration()))

    def test_no_feedback_rate_is_declared_explicitly_not_omitted(self):
        d = good_declaration()
        d["capabilities"]["feedback_rate_hz"] = None
        d["capabilities"]["feedback_rate_declared_absent"] = True
        self.assertEqual(validate_declaration(d), [])

    def test_unknown_fields_are_ignored_so_a_declaration_can_grow(self):
        d = good_declaration()
        d["vendor_note"] = "ignored"
        d["capabilities"]["extra"] = 1
        self.assertEqual(validate_declaration(d), [])

    def test_validation_does_not_change_its_input(self):
        d = good_declaration()
        before = copy.deepcopy(d)
        validate_declaration(d)
        self.assertEqual(d, before)


class TestEveryMissingItemIsNamed(unittest.TestCase):
    def test_each_top_level_item_missing(self):
        for key in ("supported_target_types", "health", "capabilities", "joint_limits", "clock"):
            with self.subTest(key):
                self.assertIn(key, paths(without(good_declaration(), key)))

    def test_each_capability_item_missing(self):
        for key in ("supported_joint_types", "supported_modes", "controlled_stop", "position_hold", "execution_cancellation",
                    "feedback", "feedback_rate_hz", "feedback_rate_declared_absent", "max_concurrent_executions"):
            with self.subTest(key):
                self.assertIn(f"capabilities.{key}", paths(without(good_declaration(), "capabilities", key)))

    def test_an_absent_boolean_is_a_problem_and_never_false(self):
        p = validate_declaration(without(good_declaration(), "capabilities", "controlled_stop"))
        self.assertEqual([x.path for x in p], ["capabilities.controlled_stop"])
        self.assertIn("explicitly", p[0].message)

    def test_every_problem_is_reported_not_only_the_first(self):
        d = good_declaration()
        del d["health"]
        del d["clock"]
        del d["capabilities"]["position_hold"]
        d["joint_limits"] = {}
        self.assertEqual(paths(d), ["capabilities.position_hold", "clock", "health", "joint_limits"])

    def test_feedback_availability_needs_both_position_and_velocity(self):
        d = good_declaration()
        del d["capabilities"]["feedback"]["velocity"]
        self.assertEqual(paths(d), ["capabilities.feedback.velocity"])

    def test_clock_needs_domain_and_synchronization_status(self):
        for key in ("domain", "synchronized"):
            with self.subTest(key):
                self.assertEqual(paths(without(good_declaration(), "clock", key)), [f"clock.{key}"])


class TestMalformedItems(unittest.TestCase):
    def check(self, mutate, expected_path):
        d = good_declaration()
        mutate(d)
        self.assertIn(expected_path, paths(d))

    def test_not_an_object(self):
        for bad in (None, [], "x", 3):
            with self.subTest(bad):
                self.assertEqual(paths(bad), [""])

    def test_target_types_and_enums(self):
        self.check(lambda d: d.update(supported_target_types=[]), "supported_target_types")
        self.check(lambda d: d.update(supported_target_types=["arm"]), "supported_target_types[0]")
        self.check(lambda d: d.update(supported_target_types=["joint", "joint"]), "supported_target_types")
        self.check(lambda d: d["capabilities"].update(supported_modes=["torque"]), "capabilities.supported_modes[0]")
        self.check(lambda d: d["capabilities"].update(supported_joint_types=["spherical"]), "capabilities.supported_joint_types[0]")

    def test_health_value(self):
        self.check(lambda d: d.update(health="READY"), "health")

    def test_booleans_must_be_booleans(self):
        for key in ("controlled_stop", "position_hold", "execution_cancellation"):
            with self.subTest(key):
                self.check(lambda d, k=key: d["capabilities"].update({k: "yes"}), f"capabilities.{key}")
        self.check(lambda d: d["clock"].update(synchronized=1), "clock.synchronized")

    def test_max_concurrent_executions(self):
        for bad in (0, -1, 1.5, True, "4"):
            with self.subTest(bad):
                self.check(lambda d, v=bad: d["capabilities"].update(max_concurrent_executions=v), "capabilities.max_concurrent_executions")

    def test_feedback_rate_rules(self):
        self.check(lambda d: d["capabilities"].update(feedback_rate_hz={"min": 100, "max": 10}), "capabilities.feedback_rate_hz")
        self.check(lambda d: d["capabilities"].update(feedback_rate_hz={"min": 0, "max": 10}), "capabilities.feedback_rate_hz")
        self.check(lambda d: d["capabilities"].update(feedback_rate_hz={"min": "a", "max": 10}), "capabilities.feedback_rate_hz")
        self.check(lambda d: d["capabilities"].update(feedback_rate_hz=None), "capabilities.feedback_rate_hz")   # absent flag not set
        self.check(lambda d: d["capabilities"].update(feedback_rate_declared_absent=True), "capabilities.feedback_rate_declared_absent")

    def test_joint_limits(self):
        self.check(lambda d: d["joint_limits"]["j1"].update(position_min=2.0), "joint_limits.j1")
        self.check(lambda d: d["joint_limits"]["j1"].update(velocity_max=0), "joint_limits.j1.velocity_max")
        self.check(lambda d: d["joint_limits"]["j1"].update(acceleration_max=-1), "joint_limits.j1.acceleration_max")
        self.check(lambda d: d["joint_limits"]["j1"].update(position_max=float("nan")), "joint_limits.j1.position_max")
        self.check(lambda d: d["joint_limits"]["j1"].pop("velocity_max"), "joint_limits.j1.velocity_max")
        self.check(lambda d: d["joint_limits"].update({"bad id": {"no_narrower_limit": True}}), "joint_limits.bad id")
        self.check(lambda d: d["joint_limits"].update(j2={"no_narrower_limit": False}), "joint_limits.j2.no_narrower_limit")
        self.check(lambda d: d["joint_limits"].update(j2={"no_narrower_limit": True, "velocity_max": 1.0}), "joint_limits.j2")

    def test_acceleration_is_optional(self):
        d = good_declaration()
        del d["joint_limits"]["j1"]["acceleration_max"]
        self.assertEqual(validate_declaration(d), [])


if __name__ == "__main__":
    unittest.main()
