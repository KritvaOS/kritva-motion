"""Tests for admission steps 10 and 11 and the query path (AC-202, AC-204).

Step 10 is the joint-state preconditions with the exemption matrix of contract 8.6 and the
CLEAR_FAULT checks of 13.6; step 11 is arbitration (TARGET_BUSY). Everything runs on a supplied,
structurally valid context: the tests show correct decisions for that context, not that a live
snapshot is current. The validator never reads the system clock; freshness uses the supplied
monotonic times. Software evidence only, never physical or safety validation.
"""
import copy
import dataclasses
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kritva_motion import admission as ad  # noqa: E402
import test_admission as base  # noqa: E402

env, joint, SNAPSHOT = base.env, base.joint, base.SNAPSHOT


def snap(**over):
    s = copy.deepcopy(SNAPSHOT)
    s.update(over)
    return s


def cfg(**joint_over):
    c = copy.deepcopy(base.CONFIG)
    c["joints"][0] = joint(**joint_over)
    return c


def ctx(cmd=None, snapshot="default", config=None, **over):
    kw = {}
    if snapshot != "default":
        kw["joint_state"] = snapshot
    if config is not None:
        kw["active_config"] = config
    kw.update(over)
    return base.ctx(cmd, **kw)


def run(c):
    return ad.first_failure(c, 11)


def code(c):
    r = run(c)
    return None if r is None else (r.code, r.step)


CLEARABLE = dict(faults={"fault-1": {"joint_id": "joint-1", "visible": True, "code": "FEEDBACK_LOST", "cause_resolved": True}})
CLIENT_OK = cfg(fault_clearance={"FEEDBACK_LOST": "CLIENT_AUTHORIZED"})


def clear(**over):
    kw = dict(snapshot=snap(health_state="FAULTED", fault_ids=["fault-1"]), config=CLIENT_OK, **CLEARABLE)
    kw.update(over)
    return ctx(env("CLEAR_FAULT"), **kw)


class TestStep10Matrix(unittest.TestCase):
    """Contract 8.6: control state first, then the health columns."""

    def test_control_unknown_blocks_movement_and_hold_whatever_the_health(self):
        for health, extra in (("READY", {}), ("DEGRADED", {"degradation_reasons": ["BACKEND_DEGRADED"]}),
                              ("FAULTED", {"fault_ids": ["f"]})):
            for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
                with self.subTest(health=health, op=op):
                    s = snap(control_state="UNKNOWN", health_state=health, **extra)
                    self.assertEqual(code(ctx(env(op), snapshot=s)), ("TARGET_STATE_UNKNOWN", 10))

    def test_stop_and_cancel_stay_available_on_every_state(self):
        for control in ("IDLE", "ACTIVE", "HOLDING", "UNKNOWN"):
            for health, extra in (("READY", {}), ("DEGRADED", {"degradation_reasons": ["BACKEND_DEGRADED"]}),
                                  ("FAULTED", {"fault_ids": ["f"]})):
                for op in ("STOP", "CANCEL"):
                    with self.subTest(control=control, health=health, op=op):
                        extra2 = {"active_command_id": "cmd-9"} if control == "ACTIVE" else {}
                        s = snap(control_state=control, health_state=health, **extra, **extra2)
                        self.assertIsNone(code(ctx(env(op), snapshot=s)))

    def test_faulted_joint_rejects_movement_and_hold(self):
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                s = snap(health_state="FAULTED", fault_ids=["f"])
                self.assertEqual(code(ctx(env(op), snapshot=s)), ("TARGET_FAULTED", 10))

    def test_degraded_joint_without_a_policy_rejects_movement_and_hold(self):
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                s = snap(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED"])
                self.assertEqual(code(ctx(env(op), snapshot=s)), ("TARGET_DEGRADED", 10))

    def test_degraded_joint_with_a_policy_permits_only_the_listed_operations(self):
        config = cfg(degradation_policy={"BACKEND_DEGRADED": ["SET_VELOCITY", "HOLD"]})
        s = snap(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED"])
        self.assertIsNone(code(ctx(env("SET_VELOCITY"), snapshot=s, config=config)))
        self.assertIsNone(code(ctx(env("HOLD"), snapshot=s, config=config)))
        self.assertEqual(code(ctx(env("SET_POSITION"), snapshot=s, config=config)), ("TARGET_DEGRADED", 10))

    def test_every_active_degradation_reason_must_permit_the_operation(self):
        config = cfg(degradation_policy={"BACKEND_DEGRADED": ["SET_VELOCITY"], "FEEDBACK_OPTIONAL_UNAVAILABLE": []})
        s = snap(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED", "FEEDBACK_OPTIONAL_UNAVAILABLE"])
        self.assertEqual(code(ctx(env("SET_VELOCITY"), snapshot=s, config=config)), ("TARGET_DEGRADED", 10))

    def test_degraded_without_reasons_fails_closed(self):
        self.assertEqual(code(ctx(env("SET_VELOCITY"), snapshot=snap(health_state="DEGRADED"))), ("TARGET_DEGRADED", 10))

    def test_no_snapshot_or_another_joints_snapshot_is_an_unknown_state(self):
        for s in (None, snap(joint_id="joint-p"), "garbage"):
            with self.subTest(s=repr(s)[:30]):
                self.assertEqual(code(ctx(snapshot=s)), ("TARGET_STATE_UNKNOWN", 10))

    def test_values_outside_the_enums_fail_closed(self):
        self.assertEqual(code(ctx(snapshot=snap(control_state="WEIRD"))), ("TARGET_STATE_UNKNOWN", 10))
        self.assertEqual(code(ctx(snapshot=snap(health_state="WEIRD"))), ("TARGET_FAULTED", 10))

    def test_ready_idle_and_holding_joints_accept_movement(self):
        for control in ("IDLE", "HOLDING"):
            for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
                with self.subTest(control=control, op=op):
                    self.assertIsNone(code(ctx(env(op), snapshot=snap(control_state=control))))


class TestFeedback(unittest.TestCase):
    """Contract 6.3, 11.3, 11.4 and 13.8: freshness against the supplied monotonic reference time."""

    def test_missing_or_invalid_feedback_is_unavailable(self):
        for st in ("MISSING", "INVALID"):
            for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
                with self.subTest(st=st, op=op):
                    self.assertEqual(code(ctx(env(op), snapshot=snap(feedback_status=st, is_current=False))), ("FEEDBACK_UNAVAILABLE", 10))

    def test_stale_feedback(self):
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                self.assertEqual(code(ctx(env(op), snapshot=snap(feedback_status="STALE", is_current=False))), ("FEEDBACK_STALE", 10))

    def test_age_against_max_feedback_age_ms(self):  # max_feedback_age_ms is 200 in the fixture
        for recv, ref, want in ((1000.0, 1200.0, None), (1000.0, 1200.5, ("FEEDBACK_STALE", 10)), (1000.0, 1000.0, None),
                                (1000.0, 999.0, ("FEEDBACK_STALE", 10))):
            with self.subTest(recv=recv, ref=ref):
                self.assertEqual(code(ctx(feedback_received_monotonic_ms=recv, reference_time_ms=ref)), want)

    def test_valid_status_that_is_not_current_is_stale(self):
        self.assertEqual(code(ctx(snapshot=snap(is_current=False))), ("FEEDBACK_STALE", 10))

    def test_missing_times_or_position_are_unavailable(self):
        self.assertEqual(code(ctx(reference_time_ms=None)), ("FEEDBACK_UNAVAILABLE", 10))
        self.assertEqual(code(ctx(feedback_received_monotonic_ms=None)), ("FEEDBACK_UNAVAILABLE", 10))
        s = copy.deepcopy(SNAPSHOT)
        del s["measured_position"]
        self.assertEqual(code(ctx(snapshot=s)), ("FEEDBACK_UNAVAILABLE", 10))
        self.assertIsNone(code(ctx(env("SET_VELOCITY"), snapshot=s)))  # velocity needs no position

    def test_unavailable_is_reported_before_stale(self):
        self.assertEqual(code(ctx(snapshot=snap(feedback_status="MISSING", is_current=False))), ("FEEDBACK_UNAVAILABLE", 10))

    def test_set_velocity_needs_feedback_only_when_it_is_required(self):
        optional = cfg(feedback_required=False, feedback_timeout_policy="DEGRADE")
        s = snap(feedback_status="MISSING", is_current=False)
        self.assertIsNone(code(ctx(env("SET_VELOCITY"), snapshot=s, config=optional)))
        self.assertEqual(code(ctx(env("SET_VELOCITY"), snapshot=s)), ("FEEDBACK_UNAVAILABLE", 10))
        self.assertEqual(code(ctx(env("SET_POSITION"), snapshot=s, config=optional)), ("FEEDBACK_UNAVAILABLE", 10))
        self.assertEqual(code(ctx(env("HOLD"), snapshot=s, config=optional)), ("FEEDBACK_UNAVAILABLE", 10))

    def test_degradation_permission_does_not_waive_feedback(self):  # CT-FLT-18
        config = cfg(degradation_policy={"BACKEND_DEGRADED": ["SET_POSITION", "HOLD", "SET_VELOCITY"]})
        s = snap(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED"], feedback_status="MISSING", is_current=False)
        for op in ("SET_POSITION", "HOLD", "SET_VELOCITY"):
            with self.subTest(op=op):
                self.assertEqual(code(ctx(env(op), snapshot=s, config=config)), ("FEEDBACK_UNAVAILABLE", 10))

    def test_optional_feedback_lost_joint_permits_only_set_velocity(self):  # CT-FLT-13
        config = cfg(feedback_required=False, feedback_timeout_policy="DEGRADE",
                     degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_VELOCITY"]})
        s = snap(health_state="DEGRADED", degradation_reasons=["FEEDBACK_OPTIONAL_UNAVAILABLE"], feedback_status="MISSING", is_current=False)
        self.assertIsNone(code(ctx(env("SET_VELOCITY"), snapshot=s, config=config)))
        self.assertEqual(code(ctx(env("SET_POSITION"), snapshot=s, config=config)), ("TARGET_DEGRADED", 10))
        self.assertEqual(code(ctx(env("HOLD"), snapshot=s, config=config)), ("TARGET_DEGRADED", 10))
        self.assertIsNone(code(ctx(env("STOP"), snapshot=s, config=config)))  # STOP stays available


class TestClearFault(unittest.TestCase):  # contract 13.6
    def test_a_clearable_fault_passes(self):
        self.assertIsNone(code(clear()))

    def test_each_precondition_is_checked(self):
        cases = {
            "cause not resolved": clear(faults={"fault-1": {"joint_id": "joint-1", "visible": True, "code": "FEEDBACK_LOST", "cause_resolved": False}}),
            "backend degraded": clear(backend=dict(base.BACKEND, health="DEGRADED")),
            "backend unavailable": clear(backend=dict(base.BACKEND, health="UNAVAILABLE")),
            "no backend": clear(backend=None),
            "control unknown": clear(snapshot=snap(health_state="FAULTED", fault_ids=["fault-1"], control_state="UNKNOWN")),
            "no snapshot": clear(snapshot=None),
            "stale required feedback": clear(snapshot=snap(health_state="FAULTED", fault_ids=["fault-1"], feedback_status="STALE", is_current=False)),
            "control active": clear(snapshot=snap(health_state="FAULTED", fault_ids=["fault-1"], control_state="ACTIVE", active_command_id="cmd-9")),
            "movement record": clear(commands={"cmd-9": {"operation": "SET_VELOCITY", "state": "RUNNING", "visible": True, "joint_id": "joint-1"}}),
            "pending hold record": clear(commands={"cmd-9": {"operation": "HOLD", "state": "ACCEPTED", "visible": True, "joint_id": "joint-1"}}),
            "termination outstanding": clear(commands={"cmd-9": {"operation": "STOP", "state": "RUNNING", "visible": True, "joint_id": "joint-1", "phase": "TERMINATING"}}),
        }
        for name, c in cases.items():
            with self.subTest(name):
                self.assertEqual(code(c), ("FAULT_NOT_CLEARABLE", 10))

    def test_what_does_not_block_clearing(self):
        s = snap(health_state="FAULTED", fault_ids=["fault-1"])
        ok = {
            "engaged hold": clear(snapshot=snap(health_state="FAULTED", fault_ids=["fault-1"], control_state="HOLDING"),
                                  commands={"cmd-9": {"operation": "HOLD", "state": "RUNNING", "hold_engaged": True, "visible": True, "joint_id": "joint-1"}}),
            "terminal command": clear(commands={"cmd-9": {"operation": "SET_POSITION", "state": "FAILED", "visible": True, "joint_id": "joint-1"}}),
            "another joint busy": clear(commands={"cmd-9": {"operation": "SET_POSITION", "state": "RUNNING", "visible": True, "joint_id": "joint-p"}}),
            "optional feedback missing": clear(config=cfg(fault_clearance={"FEEDBACK_LOST": "CLIENT_AUTHORIZED"}, feedback_required=False, feedback_timeout_policy="DEGRADE"),
                                               snapshot=snap(health_state="FAULTED", fault_ids=["fault-1"], feedback_status="MISSING", is_current=False)),
            "degraded joint with a fault": clear(snapshot=snap(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED"], fault_ids=["fault-1"])),
        }
        for name, c in ok.items():
            with self.subTest(name):
                self.assertIsNone(code(c))
        self.assertIsNotNone(s)

    def test_human_required_by_default_and_when_configured(self):
        unconfigured = clear(config=cfg())
        self.assertEqual(code(unconfigured), ("HUMAN_CONFIRMATION_REQUIRED", 10))
        explicit = clear(config=cfg(fault_clearance={"FEEDBACK_LOST": "HUMAN_REQUIRED"}))
        self.assertEqual(code(explicit), ("HUMAN_CONFIRMATION_REQUIRED", 10))
        self.assertIsNone(code(dataclasses.replace(explicit, human_operator_attested=True)))
        self.assertIsNone(code(dataclasses.replace(unconfigured, human_operator_attested=True)))

    def test_client_authorized_needs_no_human_attribute(self):
        self.assertFalse(clear().human_operator_attested)
        self.assertIsNone(code(clear()))

    def test_not_clearable_is_reported_before_human_confirmation(self):
        c = clear(config=cfg(), backend=dict(base.BACKEND, health="DEGRADED"))
        self.assertEqual(code(c), ("FAULT_NOT_CLEARABLE", 10))

    def test_a_fault_without_a_code_needs_a_human(self):
        c = clear(faults={"fault-1": {"joint_id": "joint-1", "visible": True, "cause_resolved": True}})
        self.assertEqual(code(c), ("HUMAN_CONFIRMATION_REQUIRED", 10))

    def test_clear_fault_is_not_an_override_on_an_unknown_faulted_joint(self):  # CT-FLT-17
        c = clear(snapshot=snap(health_state="FAULTED", fault_ids=["fault-1"], control_state="UNKNOWN"))
        self.assertEqual(code(c), ("FAULT_NOT_CLEARABLE", 10))


class TestStep11(unittest.TestCase):
    def rec(self, op="SET_POSITION", state="RUNNING", joint_id="joint-1", **extra):
        return dict({"operation": op, "state": state, "visible": True, "joint_id": joint_id}, **extra)

    def test_active_movement_makes_the_joint_busy(self):
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                r = run(ctx(env(op), commands={"cmd-5": self.rec()}))
                self.assertEqual((r.code, r.step), ("TARGET_BUSY", 11))
                self.assertEqual(r.conflict, {"target": {"type": "joint", "id": "joint-1"}, "command_id": "cmd-5"})

    def test_stop_cancel_and_clear_fault_are_never_busy(self):
        busy = {"cmd-5": self.rec(), "cmd-1": self.rec()}
        self.assertIsNone(code(ctx(env("STOP"), commands=busy)))
        self.assertIsNone(code(ctx(env("CANCEL"), commands=busy)))

    def test_clear_fault_does_not_take_the_slot_but_needs_no_active_execution(self):
        c = clear(commands={"cmd-5": self.rec()})
        self.assertEqual(code(c), ("FAULT_NOT_CLEARABLE", 10))  # step 10, not TARGET_BUSY

    def test_pending_hold_occupies_the_slot_and_engaged_hold_does_not(self):
        pending = self.rec("HOLD", "ACCEPTED", hold_engaged=False)
        engaged = self.rec("HOLD", "RUNNING", hold_engaged=True)
        self.assertEqual(code(ctx(env("HOLD"), commands={"cmd-5": pending})), ("TARGET_BUSY", 11))
        self.assertEqual(code(ctx(env("SET_POSITION"), commands={"cmd-5": pending})), ("TARGET_BUSY", 11))
        self.assertIsNone(code(ctx(env("SET_POSITION"), commands={"cmd-5": engaged}, snapshot=snap(control_state="HOLDING"))))
        self.assertIsNone(code(ctx(env("HOLD"), commands={"cmd-5": engaged}, snapshot=snap(control_state="HOLDING"))))

    def test_terminal_and_other_joint_records_do_not_conflict(self):
        for st in ("COMPLETED", "CANCELLED", "FAILED"):
            self.assertIsNone(code(ctx(commands={"cmd-5": self.rec(state=st)})))
        self.assertIsNone(code(ctx(commands={"cmd-5": self.rec(joint_id="joint-p")})))

    def test_the_first_conflicting_command_by_sorted_id_is_named(self):
        r = run(ctx(commands={"cmd-b": self.rec(), "cmd-a": self.rec()}))
        self.assertEqual(r.conflict["command_id"], "cmd-a")

    def test_an_unknown_record_state_counts_as_active(self):
        self.assertEqual(code(ctx(commands={"cmd-5": self.rec(state="???")})), ("TARGET_BUSY", 11))

    def test_active_snapshot_without_a_record_is_busy(self):
        s = snap(control_state="ACTIVE", active_command_id="cmd-7")
        r = run(ctx(snapshot=s))
        self.assertEqual((r.code, r.conflict["command_id"]), ("TARGET_BUSY", "cmd-7"))
        self.assertIsNone(run(ctx(env("STOP"), snapshot=s)))  # STOP preempts explicitly and is never busy (9.3)

    def test_busy_is_reported_after_state_preconditions(self):
        s = snap(health_state="FAULTED", fault_ids=["f"])
        self.assertEqual(code(ctx(snapshot=s, commands={"cmd-5": self.rec()})), ("TARGET_FAULTED", 10))


def mutate(step, c):
    """Single-step violations for steps 10 and 11 (steps 1 to 9 come from test_admission)."""
    R = dataclasses.replace
    if step == 10:
        return R(c, joint_state=snap(control_state="UNKNOWN"))
    if step == 11:
        return R(c, commands={"cmd-5": {"operation": "SET_VELOCITY", "state": "RUNNING", "visible": True, "joint_id": "joint-1"}})
    return base.mutate(step, c)


class TestAllElevenSteps(unittest.TestCase):
    def test_each_single_violation_reports_its_own_step(self):
        for s in range(1, 12):
            with self.subTest(step=s):
                self.assertEqual(run(mutate(s, ctx())).step, s)

    def test_adjacent_steps_report_the_earlier(self):
        for s in range(1, 11):
            with self.subTest(pair=(s, s + 1)):
                self.assertEqual(run(mutate(s + 1, mutate(s, ctx()))).step, s)
                self.assertEqual(run(mutate(s, mutate(s + 1, ctx()))).step, s)

    def test_all_steps_violated_reports_step_1(self):
        c = ctx()
        for s in range(11, 0, -1):
            c = mutate(s, c)
        self.assertEqual(ad.admit(c).code, "UNAUTHENTICATED")

    def test_admit_accepts_every_command_type_on_a_ready_idle_joint(self):
        for op in ("SET_POSITION", "SET_VELOCITY", "STOP", "HOLD", "CANCEL"):
            with self.subTest(op=op):
                r = ad.admit(ctx(env(op)))
                self.assertEqual((r.accepted, r.code), (True, None))
        self.assertTrue(ad.admit(clear()).accepted)

    def test_admit_returns_the_conflict_for_target_busy(self):
        r = ad.admit(mutate(11, ctx()))
        self.assertEqual((r.accepted, r.code, r.step, r.conflict["command_id"]), (False, "TARGET_BUSY", 11, "cmd-5"))

    def test_every_admission_code_of_steps_1_to_11_has_a_fixture(self):
        text = (ROOT / "contract" / "ERROR_CODES.md").read_text(encoding="utf-8")
        listed = {m.group(1): int(m.group(2)) for m in re.finditer(r"^\| `([A-Z_]+)` \| (\d+) \|", text, re.M)}
        covered = {w for w, _, _ in base.fixtures()}
        for c in (
            ctx(snapshot=snap(control_state="UNKNOWN")), ctx(snapshot=snap(health_state="FAULTED", fault_ids=["f"])),
            ctx(snapshot=snap(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED"])),
            ctx(snapshot=snap(feedback_status="MISSING", is_current=False)), ctx(snapshot=snap(is_current=False)),
            clear(backend=dict(base.BACKEND, health="DEGRADED")), clear(config=cfg()), mutate(11, ctx()),
        ):
            covered.add(run(c).code)
        self.assertEqual(set(listed) - {"LIMIT_ACCELERATION"} - covered, set())
        self.assertEqual(covered - set(listed), set())


class TestQueryPath(unittest.TestCase):
    """Queries are authorized on their own path and stay available in every joint state (6.4)."""

    def q(self, **over):
        kw = dict(query_type="GET_JOINT_STATE", argument="joint-1", active_config=copy.deepcopy(base.CONFIG),
                  commands={"cmd-1": {"visible": True}})
        kw.update(over)
        return ad.QueryContext(**kw)

    def test_valid_queries(self):
        self.assertTrue(ad.admit_query(self.q()).allowed)
        self.assertTrue(ad.admit_query(self.q(query_type="GET_COMMAND_STATUS", argument="cmd-1")).allowed)
        for t in ("GET_COMMAND_HISTORY", "GET_FAULTS"):
            self.assertTrue(ad.admit_query(self.q(query_type=t, argument=None, active_config=None)).allowed)

    def test_identity_then_authorization_then_references(self):
        self.assertEqual(ad.admit_query(self.q(identity="EXPIRED", permission_granted=False)).code, "UNAUTHENTICATED")
        self.assertEqual(ad.admit_query(self.q(permission_granted=False, argument="nope")).code, "PERMISSION_DENIED")
        self.assertEqual(ad.admit_query(self.q(argument="nope")).code, "UNKNOWN_TARGET")
        self.assertEqual(ad.admit_query(self.q(active_config=None)).code, "CONFIG_NOT_ACTIVE")

    def test_an_unseen_command_is_not_found_not_denied(self):
        for commands in ({}, {"cmd-1": {"visible": False}}):
            r = ad.admit_query(self.q(query_type="GET_COMMAND_STATUS", argument="cmd-1", commands=commands))
            self.assertEqual(r.code, "COMMAND_NOT_FOUND")

    def test_unknown_query_type(self):
        self.assertEqual(ad.admit_query(self.q(query_type="GET_TORQUE")).code, "INVALID_SCHEMA")

    def test_the_query_path_has_no_health_or_state_input(self):
        names = {f.name for f in dataclasses.fields(ad.QueryContext)}
        self.assertEqual(names, {"query_type", "argument", "identity", "permission_granted", "active_config", "commands"})

    def test_command_authorization_does_not_apply_to_queries(self):
        # A client without command permission can still pass the separate query authorization,
        # and a joint in any state can be queried.
        denied = ctx(permission_granted=False)
        self.assertEqual(ad.admit(denied).code, "PERMISSION_DENIED")
        self.assertTrue(ad.admit_query(self.q()).allowed)


if __name__ == "__main__":
    unittest.main()
