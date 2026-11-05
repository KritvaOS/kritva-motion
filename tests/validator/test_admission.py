"""Tests for the admission validator, steps 1 to 9 (AC-202, AC-203; conformance IDs CT-VAL-*).

Fixtures are plain data. The tests are deterministic and offline: no clock, no randomness, no
network. Passing them is software evidence only, never physical or safety validation. Steps 10 and
11 are tested in test_admission_state.py, which also runs the adjacent pairs (9,10) and (10,11).
"""
import ast
import copy
import dataclasses
import json
import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from kritva_motion import admission as ad  # noqa: E402
from kritva_motion import config_validation as cv  # noqa: E402

NAN, INF = float("nan"), float("inf")
CAPS = {"controlled_stop": True, "position_hold": True,
        "supported_modes": ["position", "velocity"], "supported_joint_types": ["revolute", "prismatic"]}


def joint(**over):
    j = {"joint_id": "joint-1", "name": "Shoulder", "joint_type": "revolute", "positive_direction": "counter-clockwise",
         "position_min": -1.5, "position_max": 1.5, "velocity_max": 1.0, "acceleration_max": 2.0,
         "modes": ["position", "velocity"], "max_feedback_age_ms": 200, "feedback_required": True,
         "feedback_timeout_policy": "STOP_AND_FAULT", "termination_confirm_timeout_ms": 1000,
         "position_tolerance": 0.01, "settling_duration_ms": 100,
         "default_execution_timeout_ms": 5000, "default_deadline_ms": 10000,
         "max_execution_timeout_ms": 10000, "max_deadline_ms": 20000}
    j.update(over)
    return j


CONTINUOUS = joint(joint_id="joint-c", continuous=True, modes=["velocity"])
del CONTINUOUS["position_min"], CONTINUOUS["position_max"]
PRISMATIC = joint(joint_id="joint-p", joint_type="prismatic", position_min=0.0, position_max=0.5, velocity_max=0.2)
SNAPSHOT = {"joint_id": "joint-1", "control_state": "IDLE", "health_state": "READY", "feedback_status": "VALID",
            "is_current": True, "measured_position": 0.0, "backend_status": "AVAILABLE", "config_version": "1"}
CONFIG = {"config_version": "1", "joints": [joint(), CONTINUOUS, PRISMATIC]}
LIMITS = {"joint-1": {"no_narrower_limit": True}, "joint-c": {"no_narrower_limit": True}, "joint-p": {"no_narrower_limit": True}}
BACKEND = {"health": "AVAILABLE", "capabilities": CAPS, "joint_limits": LIMITS}


def env(kind="SET_POSITION", target_id="joint-1", **over):
    params = {"SET_POSITION": {"target_position": 0.5, "unit": "rad"},
              "SET_VELOCITY": {"target_velocity": 0.1, "unit": "rad/s"},
              "STOP": {}, "HOLD": {}, "CANCEL": {"command_id": "cmd-1"}, "CLEAR_FAULT": {"fault_id": "fault-1"},
              "EXECUTE_TRAJECTORY": {}}[kind]
    c = {"contract_version": "0.1.0", "client_request_id": "req-1", "command_type": kind, "parameters": params}
    if kind != "CANCEL":
        c["target"] = {"type": "joint", "id": target_id}
    c.update(over)
    return c


def ctx(cmd=None, **over):
    base = dict(
        command=cmd if cmd is not None else env(), active_config=copy.deepcopy(CONFIG), backend=copy.deepcopy(BACKEND),
        commands={"cmd-1": {"operation": "SET_POSITION", "state": "RUNNING", "visible": True}},
        faults={"fault-1": {"joint_id": "joint-1", "visible": True, "code": "FEEDBACK_LOST", "cause_resolved": True}},
        joint_state=copy.deepcopy(SNAPSHOT), feedback_received_monotonic_ms=1000.0, reference_time_ms=1100.0)
    base.update(over)
    return ad.AdmissionContext(**base)


def fail(c, through=9):
    return ad.first_failure(c, through)


def code(c, through=9):
    r = fail(c, through)
    return None if r is None else (r.code, r.step)


class TestFixturesAreValid(unittest.TestCase):
    def test_configuration_fixture_is_valid(self):
        self.assertTrue(cv.validate_configuration(CONFIG, CAPS).valid)

    def test_every_command_type_passes_steps_1_to_9(self):
        for kind in ("SET_POSITION", "SET_VELOCITY", "STOP", "HOLD", "CANCEL", "CLEAR_FAULT"):
            with self.subTest(kind=kind):
                self.assertIsNone(fail(ctx(env(kind))))

    def test_limit_boundaries_are_inside(self):
        for pos in (-1.5, 1.5):
            self.assertIsNone(fail(ctx(env(parameters={"target_position": pos, "unit": "rad"}))))
        for vel in (-1.0, 1.0):
            self.assertIsNone(fail(ctx(env("SET_VELOCITY", parameters={"target_velocity": vel, "unit": "rad/s"}))))


# (code, step, context) - at least one fixture per admission code of steps 1 to 9.
def fixtures():
    cmd = env
    yield "UNAUTHENTICATED", 1, ctx(identity="MISSING")
    yield "UNAUTHENTICATED", 1, ctx(identity="EXPIRED")
    yield "UNAUTHENTICATED", 1, ctx(identity="INVALID")
    yield "INVALID_SCHEMA", 2, ctx(cmd(client_request_id="has space"))
    yield "INVALID_SCHEMA", 2, ctx(cmd(surprise=1))
    yield "INVALID_SCHEMA", 2, ctx({"command_type": "STOP"})
    yield "INVALID_SCHEMA", 2, ctx("not an object")
    yield "INVALID_SCHEMA", 2, ctx(cmd(command_type="JUMP"))
    yield "INVALID_SCHEMA", 2, ctx(cmd(target={"type": "wheel", "id": "w"}))
    yield "INVALID_SCHEMA", 2, ctx(cmd("CANCEL", target={"type": "joint", "id": "joint-1"}))
    yield "INVALID_SCHEMA", 2, ctx(cmd(deadline_ms=0))  # non-positive is a schema error (see TASK.md section 10)
    yield "NON_FINITE_VALUE", 2, ctx(cmd(parameters={"target_position": NAN, "unit": "rad"}))
    yield "NON_FINITE_VALUE", 2, ctx(cmd("SET_VELOCITY", parameters={"target_velocity": INF, "unit": "rad/s"}))
    yield "NON_FINITE_VALUE", 2, ctx(cmd(constraints={"max_velocity": INF}))
    yield "NON_FINITE_VALUE", 2, ctx(cmd(deadline_ms=NAN))
    yield "UNSUPPORTED_CONTRACT_VERSION", 2, ctx(cmd(contract_version="1.0.0"))
    yield "PERMISSION_DENIED", 3, ctx(permission_granted=False)
    yield "REQUEST_ID_CONFLICT", 4, ctx(idempotency={"status": "DIFFERENT"})
    yield "CONFIG_NOT_ACTIVE", 5, ctx(active_config=None)
    yield "UNSUPPORTED_COMMAND", 6, ctx(cmd("EXECUTE_TRAJECTORY"))
    for t in ("joint_group", "end_effector", "robot"):
        yield "UNSUPPORTED_TARGET_TYPE", 6, ctx(cmd(target={"type": t, "id": "g"}))
    yield "UNKNOWN_TARGET", 6, ctx(cmd(target_id="no-such-joint"))
    yield "COMMAND_NOT_FOUND", 6, ctx(cmd("CANCEL", parameters={"command_id": "missing"}))
    yield "COMMAND_NOT_FOUND", 6, ctx(commands={"cmd-1": {"operation": "SET_POSITION", "state": "RUNNING", "visible": False}}, command=cmd("CANCEL"))
    yield "FAULT_NOT_FOUND", 6, ctx(cmd("CLEAR_FAULT", parameters={"fault_id": "missing"}))
    yield "FAULT_NOT_FOUND", 6, ctx(cmd("CLEAR_FAULT"), faults={"fault-1": {"joint_id": "joint-p", "visible": True}})
    yield "FAULT_NOT_FOUND", 6, ctx(cmd("CLEAR_FAULT"), faults={"fault-1": {"joint_id": "joint-1", "visible": False}})
    yield "COMMAND_ALREADY_TERMINAL", 6, ctx(cmd("CANCEL"), commands={"cmd-1": {"operation": "SET_POSITION", "state": "COMPLETED", "visible": True}})
    for op in ("STOP", "CLEAR_FAULT", "CANCEL"):
        yield "COMMAND_NOT_CANCELLABLE", 6, ctx(cmd("CANCEL"), commands={"cmd-1": {"operation": op, "state": "RUNNING", "visible": True}})
    yield "COMMAND_NOT_CANCELLABLE", 6, ctx(cmd("CANCEL"), commands={"cmd-1": {"operation": "HOLD", "state": "RUNNING", "hold_engaged": True, "visible": True}})
    yield "UNSUPPORTED_MODE", 7, ctx(cmd(target_id="joint-c"))  # SET_POSITION on a continuous joint
    yield "UNSUPPORTED_MODE", 7, ctx(cmd(), active_config={"config_version": "1", "joints": [joint(modes=["velocity"])]})
    yield "UNSUPPORTED_MODE", 7, ctx(cmd("SET_VELOCITY"), active_config={"config_version": "1", "joints": [joint(modes=["position"])]})
    yield "UNSUPPORTED_PRIORITY", 7, ctx(cmd(priority=5))
    yield "UNIT_MISMATCH", 7, ctx(cmd(parameters={"target_position": 0.5, "unit": "m"}))
    yield "UNIT_MISMATCH", 7, ctx(cmd("SET_VELOCITY", parameters={"target_velocity": 0.1, "unit": "m/s"}))
    yield "UNIT_MISMATCH", 7, ctx(cmd(target_id="joint-p", parameters={"target_position": 0.1, "unit": "rad"}))
    yield "LIMIT_POSITION", 8, ctx(cmd(parameters={"target_position": 1.5001, "unit": "rad"}))
    yield "LIMIT_POSITION", 8, ctx(cmd(parameters={"target_position": -1.6, "unit": "rad"}))
    yield "LIMIT_VELOCITY", 8, ctx(cmd("SET_VELOCITY", parameters={"target_velocity": -1.01, "unit": "rad/s"}))
    yield "INVALID_CONSTRAINT", 8, ctx(cmd(constraints={"max_velocity": 1.5}))
    yield "INVALID_CONSTRAINT", 8, ctx(cmd(constraints={"position_max": 2.0}))
    yield "INVALID_CONSTRAINT", 8, ctx(cmd(constraints={"position_min": -2.0}))
    yield "INVALID_CONSTRAINT", 8, ctx(cmd(constraints={"max_acceleration": 3.0}))
    yield "INVALID_CONSTRAINT", 8, ctx(cmd(constraints={"position_min": 1.0, "position_max": 0.5}))
    yield "INVALID_CONSTRAINT", 8, ctx(cmd("SET_VELOCITY", target_id="joint-c", parameters={"target_velocity": 0.1, "unit": "rad/s"}, constraints={"position_min": 0.0}))
    yield "INVALID_TIMEOUT", 8, ctx(cmd(deadline_ms=20001))
    yield "INVALID_TIMEOUT", 8, ctx(cmd("STOP", execution_timeout_ms=10001))
    yield "BACKEND_UNAVAILABLE", 9, ctx(backend=None)
    yield "BACKEND_UNAVAILABLE", 9, ctx(backend=dict(BACKEND, health="UNAVAILABLE"))
    yield "BACKEND_UNAVAILABLE", 9, ctx(backend=dict(BACKEND, health="FAULTED"))
    yield "BACKEND_UNAVAILABLE", 9, ctx(cmd("STOP"), backend=dict(BACKEND, health="UNAVAILABLE"))
    for kind, capkey in (("STOP", "controlled_stop"), ("HOLD", "position_hold")):
        yield "BACKEND_CAPABILITY_UNSUPPORTED", 9, ctx(cmd(kind), backend=dict(BACKEND, capabilities=dict(CAPS, **{capkey: False})))
    yield "BACKEND_CAPABILITY_UNSUPPORTED", 9, ctx(backend=dict(BACKEND, capabilities=dict(CAPS, supported_modes=["velocity"])))
    yield "BACKEND_CAPABILITY_UNSUPPORTED", 9, ctx(cmd("SET_VELOCITY"), backend=dict(BACKEND, capabilities=dict(CAPS, supported_modes=["position"])))
    yield "BACKEND_CAPABILITY_UNSUPPORTED", 9, ctx(backend=dict(BACKEND, capabilities=dict(CAPS, supported_joint_types=["prismatic"])))
    yield "BACKEND_CAPABILITY_UNSUPPORTED", 9, ctx(backend=dict(BACKEND, joint_limits={}))  # no numerical limits declared


class TestEveryCode(unittest.TestCase):
    def test_fixtures_give_the_expected_code_and_step(self):
        for i, (want, step, c) in enumerate(fixtures()):
            with self.subTest(i=i, want=want):
                r = fail(c)
                self.assertIsNotNone(r)
                self.assertEqual((r.code, r.step), (want, step))
                self.assertTrue(r.field and r.message)

    def test_every_reachable_admission_code_of_steps_1_to_9_has_a_fixture(self):
        text = (ROOT / "contract" / "ERROR_CODES.md").read_text(encoding="utf-8")
        listed = {m.group(1): int(m.group(2)) for m in re.finditer(r"^\| `([A-Z_]+)` \| (\d+) \|", text, re.M) if int(m.group(2)) <= 9}
        self.assertIn("LIMIT_ACCELERATION", listed)
        reserved = {"LIMIT_ACCELERATION"}  # contract 8.3, MOTION-AD-045: not produced in v0.1.0
        covered = {w for w, _, _ in fixtures()}
        self.assertEqual(set(listed) - reserved - covered, set())
        self.assertEqual(covered - set(listed), set())
        for w, s, _ in fixtures():
            self.assertEqual(listed[w], s, f"{w} is recorded at step {listed[w]} in ERROR_CODES.md")

    def test_limit_acceleration_is_never_produced(self):
        self.assertNotIn("LIMIT_ACCELERATION", {w for w, _, _ in fixtures()})
        self.assertNotIn('"LIMIT_ACCELERATION"', (ROOT / "src" / "kritva_motion" / "admission.py").read_text(encoding="utf-8").replace('"LIMIT_ACCELERATION", 8', "").split("def _step1")[1])


# One single-step violation per step, applied to a context that is otherwise valid.
def mutate(step, c):
    cmd = copy.deepcopy(c.command)
    R = dataclasses.replace
    if step == 1:
        return R(c, identity="EXPIRED")
    if step == 2:
        cmd["client_request_id"] = "has space"
        return R(c, command=cmd)
    if step == 3:
        return R(c, permission_granted=False)
    if step == 4:
        return R(c, idempotency={"status": "DIFFERENT"})
    if step == 5:
        return R(c, active_config=None)
    if step == 6:
        cmd["target"] = {"type": "joint", "id": "no-such-joint"}
        return R(c, command=cmd)
    if step == 7:
        cmd["parameters"]["unit"] = "m"
        return R(c, command=cmd)
    if step == 8:
        cmd["parameters"]["target_position"] = 9.0
        return R(c, command=cmd)
    if step == 9:
        return R(c, backend=dict(c.backend, health="UNAVAILABLE"))
    raise AssertionError(step)


class TestOrder(unittest.TestCase):
    def test_each_single_violation_reports_its_own_step(self):
        for s in range(1, 10):
            with self.subTest(step=s):
                r = fail(mutate(s, ctx()))
                self.assertEqual(r.step, s)

    def test_adjacent_steps_report_the_earlier(self):
        for s in range(1, 9):
            with self.subTest(pair=(s, s + 1)):
                c = mutate(s + 1, mutate(s, ctx()))
                self.assertEqual(fail(c).step, s)
                c = mutate(s, mutate(s + 1, ctx()))  # the order the mutations are applied must not matter
                self.assertEqual(fail(c).step, s)

    def test_all_steps_violated_reports_step_1(self):
        c = ctx()
        for s in range(9, 0, -1):
            c = mutate(s, c)
        self.assertEqual(fail(c).code, "UNAUTHENTICATED")

    def test_first_failure_stops_at_the_requested_step(self):
        self.assertIsNone(fail(mutate(9, ctx()), through=8))
        self.assertEqual(fail(mutate(9, ctx()), through=9).step, 9)

    def test_a_valid_context_is_accepted_by_admit(self):
        r = ad.admit(ctx())
        self.assertEqual((r.accepted, r.code, r.step, r.replay), (True, None, None, False))


class TestSubOrder(unittest.TestCase):
    """The deterministic order inside one step (admission.py docstring)."""

    def test_step_2_schema_then_non_finite_then_version(self):
        self.assertEqual(code(ctx(env(client_request_id="bad id", parameters={"target_position": NAN, "unit": "rad"}, contract_version="1.0.0"))), ("INVALID_SCHEMA", 2))
        self.assertEqual(code(ctx(env(parameters={"target_position": NAN, "unit": "rad"}, contract_version="1.0.0"))), ("NON_FINITE_VALUE", 2))
        self.assertEqual(code(ctx(env(contract_version="1.0.0"))), ("UNSUPPORTED_CONTRACT_VERSION", 2))

    def test_step_2_reports_the_first_non_finite_field_in_a_fixed_order(self):
        r = fail(ctx(env(parameters={"target_position": NAN, "unit": "rad"}, constraints={"max_velocity": INF})))
        self.assertEqual(r.field, "constraints.max_velocity")  # constraints sorts before parameters

    def test_step_6_type_then_target_type_then_id_then_reference(self):
        self.assertEqual(code(ctx(env("EXECUTE_TRAJECTORY", target_id="x") | {"target": {"type": "robot", "id": "x"}})), ("UNSUPPORTED_COMMAND", 6))
        self.assertEqual(code(ctx(env(target={"type": "robot", "id": "no-such"}))), ("UNSUPPORTED_TARGET_TYPE", 6))
        self.assertEqual(code(ctx(env("CLEAR_FAULT", target_id="no-such", parameters={"fault_id": "missing"}))), ("UNKNOWN_TARGET", 6))

    def test_step_6_cancel_not_found_then_terminal_then_not_cancellable(self):
        c = ctx(env("CANCEL"), commands={"cmd-1": {"operation": "STOP", "state": "COMPLETED", "visible": True}})
        self.assertEqual(code(c), ("COMMAND_ALREADY_TERMINAL", 6))
        c = ctx(env("CANCEL"), commands={"cmd-1": {"operation": "STOP", "state": "RUNNING", "visible": False}})
        self.assertEqual(code(c), ("COMMAND_NOT_FOUND", 6))

    def test_step_6_hold_pending_engagement_is_cancellable(self):
        c = ctx(env("CANCEL"), commands={"cmd-1": {"operation": "HOLD", "state": "ACCEPTED", "hold_engaged": False, "visible": True}})
        self.assertIsNone(fail(c))

    def test_step_7_mode_then_priority_then_unit(self):
        c = ctx(env(target_id="joint-c", priority=5, parameters={"target_position": 0.1, "unit": "m"}))
        self.assertEqual(code(c), ("UNSUPPORTED_MODE", 7))
        c = ctx(env(priority=5, parameters={"target_position": 0.1, "unit": "m"}))
        self.assertEqual(code(c), ("UNSUPPORTED_PRIORITY", 7))

    def test_step_8_constraint_then_limit_then_timeout(self):
        c = ctx(env(parameters={"target_position": 9.0, "unit": "rad"}, constraints={"max_velocity": 5.0}, deadline_ms=99999))
        self.assertEqual(code(c), ("INVALID_CONSTRAINT", 8))
        c = ctx(env(parameters={"target_position": 9.0, "unit": "rad"}, deadline_ms=99999))
        self.assertEqual(code(c), ("LIMIT_POSITION", 8))
        c = ctx(env("SET_VELOCITY", parameters={"target_velocity": 9.0, "unit": "rad/s"}, deadline_ms=99999))
        self.assertEqual(code(c), ("LIMIT_VELOCITY", 8))
        self.assertEqual(code(ctx(env(deadline_ms=99999))), ("INVALID_TIMEOUT", 8))

    def test_step_9_unavailable_then_capability(self):
        b = dict(BACKEND, health="UNAVAILABLE", capabilities=dict(CAPS, controlled_stop=False))
        self.assertEqual(code(ctx(env("STOP"), backend=b)), ("BACKEND_UNAVAILABLE", 9))

    def test_several_failures_inside_one_step_are_deterministic(self):
        c = ctx(env(client_request_id="bad id", surprise=1, target={"type": "wheel", "id": "w"}))
        self.assertEqual({fail(c).field for _ in range(5)}, {"surprise"})  # unknown fields come first, sorted


class TestLimits(unittest.TestCase):  # AC-203
    def test_effective_limits_is_the_intersection(self):
        j = joint()
        eff = ad.effective_limits(j, {"position_min": -1.2, "position_max": 1.4, "velocity_max": 0.8, "acceleration_max": 1.5},
                                  {"position_min": -1.0, "max_velocity": 0.9, "max_acceleration": 1.0})
        self.assertEqual((eff.position_min, eff.position_max, eff.velocity_max, eff.acceleration_max, eff.empty), (-1.0, 1.4, 0.8, 1.0, False))

    def test_effective_acceleration_maximum(self):
        j = joint()
        self.assertEqual(ad.effective_limits(j, {}, None).acceleration_max, 2.0)
        self.assertEqual(ad.effective_limits(j, {"position_min": -1, "position_max": 1, "velocity_max": 1, "acceleration_max": 1.5}, None).acceleration_max, 1.5)
        self.assertEqual(ad.effective_limits(j, {}, {"max_acceleration": 0.5}).acceleration_max, 0.5)
        self.assertIsNone(ad.effective_limits(drop(j, "acceleration_max"), {}, None).acceleration_max)
        self.assertEqual(ad.effective_limits(drop(j, "acceleration_max"), {}, {"max_acceleration": 0.5}).acceleration_max, 0.5)

    def test_undeclared_backend_narrows_nothing_here(self):
        eff = ad.effective_limits(joint(), None, None)
        self.assertEqual((eff.position_min, eff.position_max, eff.velocity_max), (-1.5, 1.5, 1.0))

    def test_continuous_joint_has_no_position_range(self):
        eff = ad.effective_limits(CONTINUOUS, {}, None)
        self.assertEqual((eff.position_min, eff.position_max, eff.empty), (None, None, False))

    def test_empty_intersection(self):
        eff = ad.effective_limits(joint(), {"position_min": 1.6, "position_max": 2.0, "velocity_max": 1.0}, None)
        self.assertTrue(eff.empty)

    def test_empty_intersection_is_rejected_invalid_constraint(self):
        b = dict(BACKEND, joint_limits={"joint-1": {"position_min": 1.6, "position_max": 2.0, "velocity_max": 1.0}})
        self.assertEqual(code(ctx(backend=b)), ("INVALID_CONSTRAINT", 8))

    def test_backend_narrower_limits_apply(self):
        b = dict(BACKEND, joint_limits={"joint-1": {"position_min": -1.0, "position_max": 1.0, "velocity_max": 0.5}})
        self.assertEqual(code(ctx(env(parameters={"target_position": 1.1, "unit": "rad"}), backend=b)), ("LIMIT_POSITION", 8))
        self.assertEqual(code(ctx(env("SET_VELOCITY", parameters={"target_velocity": 0.6, "unit": "rad/s"}), backend=b)), ("LIMIT_VELOCITY", 8))
        self.assertIsNone(fail(ctx(env(parameters={"target_position": 1.0, "unit": "rad"}), backend=b)))

    def test_command_constraints_narrow_and_may_equal(self):
        c = env(parameters={"target_position": 0.6, "unit": "rad"}, constraints={"position_max": 0.5, "max_velocity": 1.0, "max_acceleration": 2.0, "unit_system": "SI"})
        self.assertEqual(code(ctx(c)), ("LIMIT_POSITION", 8))
        c = env(parameters={"target_position": 0.5, "unit": "rad"}, constraints={"position_max": 0.5, "max_velocity": 1.0, "max_acceleration": 2.0})
        self.assertIsNone(fail(ctx(c)))

    def test_constraint_equal_bounds_are_not_contradictory(self):
        c = env(parameters={"target_position": 0.5, "unit": "rad"}, constraints={"position_min": 0.5, "position_max": 0.5})
        self.assertIsNone(fail(ctx(c)))

    def test_constraints_do_not_widen_via_the_backend_either(self):
        c = env("SET_VELOCITY", parameters={"target_velocity": 0.9, "unit": "rad/s"}, constraints={"max_velocity": 0.95})
        b = dict(BACKEND, joint_limits={"joint-1": {"position_min": -1, "position_max": 1, "velocity_max": 0.5}})
        self.assertEqual(code(ctx(c, backend=b)), ("LIMIT_VELOCITY", 8))

    def test_non_finite_is_rejected_not_clamped(self):
        for v in (NAN, INF, -INF):
            self.assertEqual(code(ctx(env(parameters={"target_position": v, "unit": "rad"}))), ("NON_FINITE_VALUE", 2))

    def test_limit_acceleration_stays_reserved(self):
        # A huge acceleration constraint is a widening constraint, not an acceleration limit rejection.
        self.assertEqual(code(ctx(env(constraints={"max_acceleration": 1e9}))), ("INVALID_CONSTRAINT", 8))

    def test_acceleration_constraint_is_accepted_when_it_narrows_or_equals(self):
        self.assertIsNone(fail(ctx(env(constraints={"max_acceleration": 2.0}))))
        self.assertIsNone(fail(ctx(env(constraints={"max_acceleration": 0.0}))))

    def test_configured_acceleration_absent_allows_any_constraint(self):
        cfg = {"config_version": "1", "joints": [drop(joint(), "acceleration_max")]}
        self.assertIsNone(fail(ctx(env(constraints={"max_acceleration": 1e9}), active_config=cfg)))


def drop(d, *keys):
    d = copy.deepcopy(d)
    for k in keys:
        d.pop(k)
    return d


class TestIdempotencyReplay(unittest.TestCase):
    def test_identical_request_returns_the_stored_decision(self):
        c = ctx(idempotency={"status": "IDENTICAL", "stored_decision": {"accepted": False, "code": "LIMIT_POSITION"}},
                permission_granted=True)
        r = ad.admit(c)
        self.assertEqual((r.accepted, r.code, r.step, r.replay), (False, "LIMIT_POSITION", 4, True))

    def test_identical_accepted_request_is_a_replay_without_a_command_id(self):
        r = ad.admit(ctx(idempotency={"status": "IDENTICAL", "stored_decision": {"accepted": True, "code": None}}))
        self.assertEqual((r.accepted, r.replay), (True, True))
        self.assertFalse(hasattr(r, "command_id"))

    def test_a_replay_is_returned_only_after_steps_1_to_3(self):
        c = ctx(identity="EXPIRED", idempotency={"status": "IDENTICAL", "stored_decision": {"accepted": True, "code": None}})
        self.assertEqual(ad.admit(c).code, "UNAUTHENTICATED")
        c = ctx(permission_granted=False, idempotency={"status": "IDENTICAL", "stored_decision": {"accepted": True, "code": None}})
        self.assertEqual(ad.admit(c).code, "PERMISSION_DENIED")

    def test_a_replay_is_returned_before_later_failures(self):
        c = ctx(env(parameters={"target_position": 9.0, "unit": "rad"}),
                idempotency={"status": "IDENTICAL", "stored_decision": {"accepted": True, "code": None}})
        self.assertTrue(ad.admit(c).replay)


class TestResultAndPurity(unittest.TestCase):
    def test_rejection_result_shape_has_no_command_id_or_state(self):
        r = ad.admit(ctx(identity="MISSING"))
        self.assertEqual({f.name for f in dataclasses.fields(r)}, {"accepted", "code", "step", "field", "message", "replay", "conflict"})
        self.assertEqual((r.accepted, r.code, r.step), (False, "UNAUTHENTICATED", 1))

    def test_inputs_are_not_modified(self):
        for _, _, c in fixtures():
            before = copy.deepcopy(dataclasses.asdict(c)) if not isinstance(c.command, float) else None
            fail(c)
            if before is not None:
                after = dataclasses.asdict(c)
                self.assertEqual(json.dumps(before, sort_keys=True, default=str), json.dumps(after, sort_keys=True, default=str))

    def test_same_input_same_result(self):
        for _, _, c in fixtures():
            self.assertEqual(fail(c), fail(c))

    def test_patterns_match_the_schema(self):
        s = json.loads((ROOT / "contract" / "motion-command.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(ad.VERSION_PATTERN, s["properties"]["contract_version"]["pattern"])
        self.assertEqual(ad.ID_PATTERN, s["properties"]["client_request_id"]["pattern"])
        self.assertEqual(ad.ID_PATTERN, s["$defs"]["target"]["properties"]["id"]["pattern"])

    def test_imports_and_calls(self):
        tree = ast.parse((ROOT / "src" / "kritva_motion" / "admission.py").read_text(encoding="utf-8"))
        imported, calls = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.add(node.func.id)
        self.assertEqual(imported, {"math", "re", "dataclasses", "typing"})
        self.assertFalse(calls & {"open", "print", "input", "exec", "eval", "__import__"})


if __name__ == "__main__":
    unittest.main()
