"""Conformance tests mapped one-to-one to conformance IDs (AC-206).

Each method below is the single executable test named by one IN_SCOPE entry of
tests/manifest/conformance_manifest.json. The method name is the ID with hyphens replaced by
underscores. The tests are deterministic and offline. They show that the reference validator
follows the contract text for the supplied data; they are software evidence only, never physical or
safety validation. IDs that need the runtime, the idempotency store, events or history stay
DEFERRED in the manifest and are not tested here.
"""
import copy
import dataclasses
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kritva_motion import admission as ad  # noqa: E402
from kritva_motion import config_validation as cv  # noqa: E402
import test_admission as base  # noqa: E402
import test_admission_state as st  # noqa: E402

env, joint, CAPS, CONFIG, BACKEND = base.env, base.joint, base.CAPS, base.CONFIG, base.BACKEND
NAN, INF = math.nan, math.inf
FULL = ("SET_POSITION", "SET_VELOCITY", "STOP", "HOLD", "CANCEL")


def cfg_of(*joints):
    return {"config_version": "1", "joints": list(joints)}


def rules(config, caps=CAPS):
    r = cv.validate_configuration(config, caps)
    return r, {v.rule for v in r.violations}


def outcome(c):
    r = st.run(c)
    return None if r is None else (r.code, r.step)


def rec(op="SET_POSITION", state="RUNNING", joint_id="joint-1", **extra):
    return dict({"operation": op, "state": state, "visible": True, "joint_id": joint_id}, **extra)


class TestConformance(unittest.TestCase):
    # ---- configuration -------------------------------------------------------------------
    def test_CT_CFG_02(self):
        good, _ = rules(CONFIG)
        self.assertTrue(good.valid)
        incomplete = joint()
        del incomplete["velocity_max"]
        bad = {
            "missing required field": cfg_of(incomplete),
            "inverted position range": cfg_of(joint(position_min=1.0, position_max=-1.0)),
            "duplicate joint id": cfg_of(joint(), joint()),
            "unknown field": cfg_of(joint(surprise=1)),
            "no joints key": {"config_version": "1"},
        }
        for name, config in bad.items():
            with self.subTest(name):
                r, found = rules(config)
                self.assertFalse(r.valid)
                self.assertTrue(found)

    def test_CT_CFG_07(self):
        r, found = rules(cfg_of(joint(feedback_timeout_policy="SHRUG")))
        self.assertFalse(r.valid)
        self.assertIn("CFG_UNKNOWN_POLICY", found)
        r, found = rules(cfg_of(joint()), dict(CAPS, controlled_stop=False))
        self.assertFalse(r.valid)
        self.assertIn("CFG_BACKEND_CANNOT_SATISFY", found)
        r, found = rules(cfg_of(joint(joint_id="joint-c", continuous=True, modes=["position", "velocity"], position_min=None)))
        self.assertFalse(r.valid)
        cont = copy.deepcopy(base.CONTINUOUS)
        cont["modes"] = ["position", "velocity"]
        r, found = rules(cfg_of(cont))
        self.assertFalse(r.valid)
        self.assertIn("CFG_CONTINUOUS_POSITION_MODE", found)
        self.assertTrue(rules(cfg_of(base.CONTINUOUS))[0].valid)

    def test_CT_CFG_08(self):
        for op in ("SET_POSITION", "HOLD"):
            with self.subTest(op=op):
                r, found = rules(cfg_of(joint(degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": [op]})))
                self.assertFalse(r.valid)
                self.assertIn("CFG_DEGRADATION_UNSAFE_OPERATION", found)
        ok = joint(feedback_required=False, feedback_timeout_policy="DEGRADE",
                   degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_VELOCITY"]})
        self.assertTrue(rules(cfg_of(ok))[0].valid)

    # ---- validation ----------------------------------------------------------------------
    def test_CT_VAL_01(self):
        seen = set()
        for i, (want, step, c) in enumerate(base.fixtures()):
            with self.subTest(i=i, want=want):
                r = ad.first_failure(c, 9)
                self.assertEqual((r.code, r.step), (want, step))
                seen.add(want)
        for c in (st.ctx(snapshot=st.snap(control_state="UNKNOWN")), st.ctx(snapshot=st.snap(health_state="FAULTED", fault_ids=["f"])),
                  st.ctx(snapshot=st.snap(feedback_status="MISSING", is_current=False)), st.mutate(11, st.ctx())):
            seen.add(st.run(c).code)
        self.assertNotIn("LIMIT_ACCELERATION", seen)  # reserved in v0.1.0 (contract 8.3)
        self.assertTrue({"TARGET_STATE_UNKNOWN", "TARGET_FAULTED", "FEEDBACK_UNAVAILABLE", "TARGET_BUSY", "INVALID_SCHEMA"} <= seen)

    def test_CT_VAL_02(self):
        for pair in ((3, 8), (5, 9), (2, 7), (7, 10), (4, 11), (8, 9), (6, 8)):
            with self.subTest(pair=pair):
                c = st.ctx()
                for s in sorted(pair, reverse=True):
                    c = st.mutate(s, c)
                self.assertEqual(st.run(c).step, min(pair))
        c = st.ctx()
        for s in (11, 10, 9, 8, 7, 6, 5, 4, 3, 2):
            c = st.mutate(s, c)
        self.assertEqual(ad.admit(c).step, 2)

    def test_CT_VAL_03(self):
        edge = {"position": (1.5, -1.5), "velocity": (1.0, -1.0)}
        for p in edge["position"]:
            self.assertIsNone(base.fail(base.ctx(env(parameters={"target_position": p, "unit": "rad"}))), p)
        for p in (1.5 + 1e-9, -1.5 - 1e-9):
            self.assertEqual(base.code(base.ctx(env(parameters={"target_position": p, "unit": "rad"}))), ("LIMIT_POSITION", 8))
        for v in edge["velocity"]:
            self.assertIsNone(base.fail(base.ctx(env("SET_VELOCITY", parameters={"target_velocity": v, "unit": "rad/s"}))), v)
        for v in (1.0 + 1e-9, -1.0 - 1e-9):
            self.assertEqual(base.code(base.ctx(env("SET_VELOCITY", parameters={"target_velocity": v, "unit": "rad/s"}))), ("LIMIT_VELOCITY", 8))
        # Acceleration is a constraint, not a target: equal is accepted, beyond the configured maximum is INVALID_CONSTRAINT.
        self.assertIsNone(base.fail(base.ctx(env(constraints={"max_acceleration": 2.0}))))
        self.assertEqual(base.code(base.ctx(env(constraints={"max_acceleration": 2.0 + 1e-9}))), ("INVALID_CONSTRAINT", 8))

    def test_CT_VAL_04(self):
        widening = [{"max_velocity": 1.0001}, {"position_max": 1.5001}, {"position_min": -1.5001}, {"max_acceleration": 2.0001}]
        for k in widening:
            with self.subTest(k=k):
                self.assertEqual(base.code(base.ctx(env(constraints=k))), ("INVALID_CONSTRAINT", 8))
        narrowing = {"max_velocity": 0.5, "position_max": 1.0, "position_min": -1.0, "max_acceleration": 1.0}
        self.assertIsNone(base.fail(base.ctx(env(constraints=narrowing))))
        # Enforced: a target between the constraint and the configured limit is refused.
        c = env(parameters={"target_position": 1.2, "unit": "rad"}, constraints={"position_max": 1.0})
        self.assertEqual(base.code(base.ctx(c)), ("LIMIT_POSITION", 8))
        c = env("SET_VELOCITY", parameters={"target_velocity": 0.8, "unit": "rad/s"}, constraints={"max_velocity": 0.5})
        self.assertEqual(base.code(base.ctx(c)), ("LIMIT_VELOCITY", 8))

    def test_CT_VAL_05(self):
        narrow = dict(BACKEND, joint_limits={"joint-1": {"position_min": -1.0, "position_max": 1.0, "velocity_max": 0.5}})
        self.assertEqual(base.code(base.ctx(env(parameters={"target_position": 1.2, "unit": "rad"}), backend=narrow)), ("LIMIT_POSITION", 8))
        self.assertEqual(base.code(base.ctx(env("SET_VELOCITY", parameters={"target_velocity": 0.7, "unit": "rad/s"}), backend=narrow)), ("LIMIT_VELOCITY", 8))
        wide = dict(BACKEND, joint_limits={"joint-1": {"position_min": -9.0, "position_max": 9.0, "velocity_max": 9.0}})
        self.assertEqual(base.code(base.ctx(env(parameters={"target_position": 1.6, "unit": "rad"}), backend=wide)), ("LIMIT_POSITION", 8))
        self.assertEqual(base.code(base.ctx(env("SET_VELOCITY", parameters={"target_velocity": 1.5, "unit": "rad/s"}), backend=wide)), ("LIMIT_VELOCITY", 8))
        eff = ad.effective_limits(joint(), wide["joint_limits"]["joint-1"], None)
        self.assertEqual((eff.position_min, eff.position_max, eff.velocity_max), (-1.5, 1.5, 1.0))

    def test_CT_VAL_06(self):
        for p in (1.6, -1.6, 100.0):
            r = ad.admit(base.ctx(env(parameters={"target_position": p, "unit": "rad"})))
            self.assertFalse(r.accepted)
            self.assertEqual(r.code, "LIMIT_POSITION")
        for v in (1.1, -1.1, 50.0):
            r = ad.admit(base.ctx(env("SET_VELOCITY", parameters={"target_velocity": v, "unit": "rad/s"})))
            self.assertFalse(r.accepted)
            self.assertEqual(r.code, "LIMIT_VELOCITY")
        self.assertFalse(hasattr(ad.admit(base.ctx(env(parameters={"target_position": 9.0, "unit": "rad"}))), "clamped_value"))

    def test_CT_VAL_07(self):
        cases = [
            env(parameters={"target_position": NAN, "unit": "rad"}),
            env(parameters={"target_position": INF, "unit": "rad"}),
            env(parameters={"target_position": -INF, "unit": "rad"}),
            env("SET_VELOCITY", parameters={"target_velocity": NAN, "unit": "rad/s"}),
            env("SET_VELOCITY", parameters={"target_velocity": INF, "unit": "rad/s"}),
            env(constraints={"max_velocity": NAN}),
            env(constraints={"position_min": -INF}),
            env(deadline_ms=NAN),
            env("STOP", execution_timeout_ms=INF),
        ]
        for i, cmd in enumerate(cases):
            with self.subTest(i=i):
                self.assertEqual(base.code(base.ctx(cmd)), ("NON_FINITE_VALUE", 2))

    def test_CT_VAL_08(self):
        cases = [
            (env(parameters={"target_position": 0.5, "unit": "m"}), "joint-1"),
            (env("SET_VELOCITY", parameters={"target_velocity": 0.1, "unit": "m/s"}), "joint-1"),
            (env(target_id="joint-p", parameters={"target_position": 0.1, "unit": "rad"}), "joint-p"),
            (env("SET_VELOCITY", target_id="joint-p", parameters={"target_velocity": 0.1, "unit": "rad/s"}), "joint-p"),
        ]
        for i, (cmd, _j) in enumerate(cases):
            with self.subTest(i=i):
                self.assertEqual(base.code(base.ctx(cmd)), ("UNIT_MISMATCH", 7))
        self.assertIsNone(base.fail(base.ctx(env(target_id="joint-p", parameters={"target_position": 0.1, "unit": "m"}))))
        self.assertIsNone(base.fail(base.ctx(env("SET_VELOCITY", target_id="joint-p", parameters={"target_velocity": 0.1, "unit": "m/s"}))))

    def test_CT_VAL_09(self):
        for t in ("joint_group", "end_effector", "robot"):
            with self.subTest(target=t):
                self.assertEqual(base.code(base.ctx(env(target={"type": t, "id": "g"}))), ("UNSUPPORTED_TARGET_TYPE", 6))
        self.assertEqual(base.code(base.ctx(env("EXECUTE_TRAJECTORY"))), ("UNSUPPORTED_COMMAND", 6))
        for p in (1, 5, -1):
            with self.subTest(priority=p):
                self.assertEqual(base.code(base.ctx(env(priority=p))), ("UNSUPPORTED_PRIORITY", 7))
        self.assertIsNone(base.fail(base.ctx(env(priority=0))))

    def test_CT_VAL_10(self):
        for kind in ("SET_TORQUE", "SET_CURRENT", "SET_PWM"):
            with self.subTest(kind=kind):
                self.assertEqual(base.code(base.ctx(env(command_type=kind))), ("INVALID_SCHEMA", 2))
        for key, unit in (("target_torque", "N*m"), ("target_current", "A"), ("target_pwm", "1")):
            with self.subTest(key=key):
                self.assertEqual(base.code(base.ctx(env(parameters={key: 0.1, "unit": unit}))), ("INVALID_SCHEMA", 2))

    def test_CT_VAL_12(self):
        c = base.ctx(env(target_id="joint-c", parameters={"target_position": 0.5, "unit": "rad"}))
        self.assertEqual(base.code(c), ("UNSUPPORTED_MODE", 7))
        ok = base.ctx(env("SET_VELOCITY", target_id="joint-c", parameters={"target_velocity": 0.1, "unit": "rad/s"}))
        self.assertIsNone(base.fail(ok))

    def test_CT_VAL_13(self):
        narrow = dict(BACKEND, joint_limits={"joint-1": {"position_min": -0.5, "position_max": 0.5, "velocity_max": 0.2}})
        self.assertEqual(base.code(base.ctx(env(parameters={"target_position": 0.9, "unit": "rad"}), backend=narrow)), ("LIMIT_POSITION", 8))
        self.assertEqual(base.code(base.ctx(env("SET_VELOCITY", parameters={"target_velocity": 0.3, "unit": "rad/s"}), backend=narrow)), ("LIMIT_VELOCITY", 8))
        explicit = dict(BACKEND, joint_limits={"joint-1": {"no_narrower_limit": True}})
        self.assertIsNone(base.fail(base.ctx(backend=explicit)))
        for silent in ({}, {"joint-1": {}}):
            with self.subTest(silent=silent):
                self.assertEqual(base.code(base.ctx(backend=dict(BACKEND, joint_limits=silent))), ("BACKEND_CAPABILITY_UNSUPPORTED", 9))

    def test_CT_VAL_14(self):
        s = st.snap(control_state="UNKNOWN", health_state="READY")
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                self.assertEqual(outcome(st.ctx(env(op), snapshot=s)), ("TARGET_STATE_UNKNOWN", 10))
        for op in ("STOP", "CANCEL"):
            with self.subTest(op=op):
                self.assertIsNone(outcome(st.ctx(env(op), snapshot=s)))
        # The check precedes the health checks and the feedback checks.
        stale = st.snap(control_state="UNKNOWN", health_state="READY", feedback_status="STALE", is_current=False)
        self.assertEqual(outcome(st.ctx(snapshot=stale)), ("TARGET_STATE_UNKNOWN", 10))
        faulted = st.snap(control_state="UNKNOWN", health_state="FAULTED", fault_ids=["f"])
        self.assertEqual(outcome(st.ctx(snapshot=faulted)), ("TARGET_STATE_UNKNOWN", 10))
        self.assertTrue(self._query_ok())  # queries have no joint-state input and stay available

    @staticmethod
    def _query_ok():
        q = ad.QueryContext(query_type="GET_JOINT_STATE", argument="joint-1", active_config=copy.deepcopy(CONFIG),
                            commands={"cmd-1": {"visible": True}})
        return ad.admit_query(q).allowed

    # ---- arbitration ---------------------------------------------------------------------
    def test_CT_ARB_01(self):
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                c = st.ctx(env(op), commands={"cmd-5": rec()})
                r = ad.admit(c)
                self.assertEqual((r.accepted, r.code, r.step), (False, "TARGET_BUSY", 11))
                self.assertEqual(r.conflict, {"target": {"type": "joint", "id": "joint-1"}, "command_id": "cmd-5"})
        c = st.ctx(commands={"cmd-5": rec()})
        self.assertEqual(c.commands["cmd-5"]["state"], "RUNNING")  # the stored command is not replaced by admission
        ad.admit(c)
        self.assertEqual(c.commands, {"cmd-5": rec()})

    def test_CT_ARB_05(self):
        done = {"cmd-1": {"operation": "SET_POSITION", "state": "COMPLETED", "visible": True}}
        self.assertEqual(base.code(base.ctx(env("CANCEL"), commands=done)), ("COMMAND_ALREADY_TERMINAL", 6))
        for state in ("CANCELLED", "FAILED"):
            with self.subTest(state=state):
                c = base.ctx(env("CANCEL"), commands={"cmd-1": {"operation": "SET_POSITION", "state": state, "visible": True}})
                self.assertEqual(base.code(c), ("COMMAND_ALREADY_TERMINAL", 6))
        c = base.ctx(env("CANCEL", parameters={"command_id": "unknown"}))
        self.assertEqual(base.code(c), ("COMMAND_NOT_FOUND", 6))

    def test_CT_ARB_06(self):
        for status in ("MISSING", "INVALID"):
            with self.subTest(status=status):
                s = st.snap(feedback_status=status, is_current=False)
                self.assertEqual(outcome(st.ctx(env("HOLD"), snapshot=s)), ("FEEDBACK_UNAVAILABLE", 10))
        stale = st.snap(feedback_status="STALE", is_current=False)
        self.assertEqual(outcome(st.ctx(env("HOLD"), snapshot=stale)), ("FEEDBACK_STALE", 10))
        nocap = dict(BACKEND, capabilities=dict(CAPS, position_hold=False))
        self.assertEqual(outcome(st.ctx(env("HOLD"), backend=nocap)), ("BACKEND_CAPABILITY_UNSUPPORTED", 9))
        self.assertIsNone(outcome(st.ctx(env("HOLD"))))

    def test_CT_ARB_08(self):
        # Priority is not supported in v0.1.0: any non-default value is refused, and the default never
        # bypasses a limit, a capability check or the movement slot.
        self.assertEqual(outcome(st.ctx(env(priority=9))), ("UNSUPPORTED_PRIORITY", 7))
        self.assertEqual(outcome(st.ctx(env(priority=0, parameters={"target_position": 9.0, "unit": "rad"}))), ("LIMIT_POSITION", 8))
        self.assertEqual(outcome(st.ctx(env(priority=0), backend=dict(BACKEND, health="UNAVAILABLE"))), ("BACKEND_UNAVAILABLE", 9))
        self.assertEqual(outcome(st.ctx(env(priority=0), commands={"cmd-5": rec()})), ("TARGET_BUSY", 11))
        self.assertEqual(outcome(st.ctx(env(priority=7), commands={"cmd-5": rec()})), ("UNSUPPORTED_PRIORITY", 7))

    def test_CT_ARB_12(self):
        busy = {"cmd-5": rec(), "cmd-1": rec()}  # cmd-1 is the command CANCEL refers to
        for op in ("STOP", "CANCEL"):
            with self.subTest(op=op):
                self.assertIsNone(outcome(st.ctx(env(op), commands=busy)))
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                self.assertEqual(outcome(st.ctx(env(op), commands=busy)), ("TARGET_BUSY", 11))
        # CLEAR_FAULT never produces TARGET_BUSY; an active movement blocks it earlier, at step 10.
        r = st.run(st.clear(commands=busy))
        self.assertNotEqual(r.code, "TARGET_BUSY")
        self.assertEqual(r.code, "FAULT_NOT_CLEARABLE")
        # Pending HOLD occupies the slot; an engaged HOLD does not.
        pending = {"cmd-5": rec("HOLD", "ACCEPTED", hold_engaged=False)}
        engaged = {"cmd-5": rec("HOLD", "RUNNING", hold_engaged=True)}
        self.assertEqual(outcome(st.ctx(env("SET_POSITION"), commands=pending)), ("TARGET_BUSY", 11))
        self.assertIsNone(outcome(st.ctx(env("SET_POSITION"), commands=engaged, snapshot=st.snap(control_state="HOLDING"))))
        # A query is not on the command path at all.
        self.assertTrue(self._query_ok())

    def test_CT_ARB_14(self):
        for op in ("SET_POSITION", "SET_VELOCITY"):
            with self.subTest(op=op):
                c = base.ctx(env("CANCEL"), commands={"cmd-1": {"operation": op, "state": "RUNNING", "visible": True}})
                self.assertIsNone(base.fail(c))
        pending = {"cmd-1": {"operation": "HOLD", "state": "ACCEPTED", "hold_engaged": False, "visible": True}}
        self.assertIsNone(base.fail(base.ctx(env("CANCEL"), commands=pending)))
        for op, extra in (("STOP", {}), ("CLEAR_FAULT", {}), ("CANCEL", {}), ("HOLD", {"hold_engaged": True})):
            with self.subTest(op=op, extra=extra):
                c = base.ctx(env("CANCEL"), commands={"cmd-1": dict({"operation": op, "state": "RUNNING", "visible": True}, **extra)})
                self.assertEqual(base.code(c), ("COMMAND_NOT_CANCELLABLE", 6))

    # ---- feedback, faults, authorization, backend ----------------------------------------
    def test_CT_FB_01(self):
        # Freshness uses Motion's monotonic receipt time and the maximum age, never a backend timestamp.
        for recv, ref, want in ((1000.0, 1200.0, None), (1000.0, 1200.5, ("FEEDBACK_STALE", 10))):
            with self.subTest(recv=recv, ref=ref):
                self.assertEqual(outcome(st.ctx(feedback_received_monotonic_ms=recv, reference_time_ms=ref)), want)
        # A snapshot that carries an old or odd backend timestamp changes nothing.
        for ts in (0, 10**15, -5):
            with self.subTest(backend_timestamp=ts):
                s = st.snap(backend_timestamp_ms=ts, timestamp_ms=ts)
                self.assertIsNone(outcome(st.ctx(snapshot=s)))
                self.assertEqual(outcome(st.ctx(snapshot=s, feedback_received_monotonic_ms=1000.0, reference_time_ms=1300.0)), ("FEEDBACK_STALE", 10))

    def test_CT_FLT_04(self):
        s = st.snap(health_state="FAULTED", fault_ids=["f"])
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                self.assertEqual(outcome(st.ctx(env(op), snapshot=s)), ("TARGET_FAULTED", 10))
        self.assertIsNone(outcome(st.ctx(env("SET_POSITION"))))

    def test_CT_FLT_06(self):
        self.assertIsNone(outcome(st.clear()))
        no_perm = dataclasses.replace(st.clear(), permission_granted=False)
        self.assertEqual(ad.admit(no_perm).code, "PERMISSION_DENIED")
        unresolved = st.clear(faults={"fault-1": {"joint_id": "joint-1", "visible": True, "code": "FEEDBACK_LOST", "cause_resolved": False}})
        self.assertEqual(outcome(unresolved), ("FAULT_NOT_CLEARABLE", 10))
        active = st.clear(commands={"cmd-9": rec()})
        self.assertEqual(outcome(active), ("FAULT_NOT_CLEARABLE", 10))
        human = st.clear(config=st.cfg(fault_clearance={"FEEDBACK_LOST": "HUMAN_REQUIRED"}))
        self.assertEqual(outcome(human), ("HUMAN_CONFIRMATION_REQUIRED", 10))
        self.assertIsNone(outcome(dataclasses.replace(human, human_operator_attested=True)))

    def test_CT_FLT_12(self):
        degraded = st.snap(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED"])
        faulted = st.snap(health_state="FAULTED", fault_ids=["f"])
        for op in ("STOP", "CANCEL"):
            for name, s in (("degraded", degraded), ("faulted", faulted)):
                with self.subTest(op=op, state=name):
                    self.assertIsNone(outcome(st.ctx(env(op), snapshot=s)))
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op, state="faulted"):
                self.assertEqual(outcome(st.ctx(env(op), snapshot=faulted)), ("TARGET_FAULTED", 10))
            with self.subTest(op=op, state="degraded"):
                self.assertEqual(outcome(st.ctx(env(op), snapshot=degraded)), ("TARGET_DEGRADED", 10))
        permit = st.cfg(degradation_policy={"BACKEND_DEGRADED": ["SET_VELOCITY"]})
        self.assertIsNone(outcome(st.ctx(env("SET_VELOCITY"), snapshot=degraded, config=permit)))
        self.assertEqual(outcome(st.ctx(env("SET_POSITION"), snapshot=degraded, config=permit)), ("TARGET_DEGRADED", 10))
        # Faulted joint with a clearable fault: CLEAR_FAULT is the one command that proceeds.
        self.assertIsNone(outcome(st.clear()))

    def test_CT_FLT_13(self):
        s = st.snap(health_state="DEGRADED", degradation_reasons=["BACKEND_DEGRADED"])
        no_policy = st.cfg()
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op):
                self.assertEqual(outcome(st.ctx(env(op), snapshot=s, config=no_policy)), ("TARGET_DEGRADED", 10))
        empty = st.cfg(degradation_policy={"BACKEND_DEGRADED": []})
        for op in ("SET_POSITION", "SET_VELOCITY", "HOLD"):
            with self.subTest(op=op, policy="empty"):
                self.assertEqual(outcome(st.ctx(env(op), snapshot=s, config=empty)), ("TARGET_DEGRADED", 10))
        for op in ("STOP", "CANCEL"):
            self.assertIsNone(outcome(st.ctx(env(op), snapshot=s, config=no_policy)))
        self.assertTrue(self._query_ok())  # queries have no joint-state input and stay available

    def test_CT_FLT_23(self):
        none_for_joint = st.clear(faults={})
        self.assertEqual(ad.admit(none_for_joint).code, "FAULT_NOT_FOUND")
        other_joint = st.clear(faults={"fault-1": {"joint_id": "joint-p", "visible": True, "code": "FEEDBACK_LOST", "cause_resolved": True}})
        self.assertEqual(ad.admit(other_joint).code, "FAULT_NOT_FOUND")
        unknown_id = st.clear(command=env("CLEAR_FAULT", parameters={"fault_id": "no-such-fault"}))
        r = ad.admit(unknown_id)
        self.assertEqual((r.code, r.step), ("FAULT_NOT_FOUND", 6))
        invisible = st.clear(faults={"fault-1": {"joint_id": "joint-1", "visible": False, "code": "FEEDBACK_LOST", "cause_resolved": True}})
        self.assertEqual(ad.admit(invisible).code, "FAULT_NOT_FOUND")

    def test_CT_AUTH_05(self):
        stored = {"status": "IDENTICAL", "stored_decision": {"accepted": True, "code": None}}
        revoked = st.ctx(idempotency=stored, permission_granted=False)
        r = ad.admit(revoked)
        self.assertEqual((r.accepted, r.code, r.step, r.replay), (False, "PERMISSION_DENIED", 3, False))
        granted = ad.admit(st.ctx(idempotency=stored))
        self.assertEqual((granted.accepted, granted.replay), (True, True))
        expired = ad.admit(st.ctx(idempotency=stored, identity="EXPIRED"))
        self.assertEqual(expired.code, "UNAUTHENTICATED")

    def test_CT_BE_05(self):
        for name, entry in (("wider", {"position_min": -9.0, "position_max": 9.0, "velocity_max": 9.0, "acceleration_max": 99.0}),
                            ("none declared", {"no_narrower_limit": True}), ("empty", {})):
            with self.subTest(name):
                eff = ad.effective_limits(joint(), entry, None)
                self.assertEqual((eff.position_min, eff.position_max, eff.velocity_max, eff.acceleration_max), (-1.5, 1.5, 1.0, 2.0))
        narrower = ad.effective_limits(joint(), {"position_min": -1.0, "position_max": 1.0, "velocity_max": 0.5, "acceleration_max": 1.0}, None)
        self.assertEqual((narrower.position_min, narrower.position_max, narrower.velocity_max, narrower.acceleration_max), (-1.0, 1.0, 0.5, 1.0))
        wide = dict(BACKEND, joint_limits={"joint-1": {"position_min": -9.0, "position_max": 9.0, "velocity_max": 9.0}})
        self.assertEqual(base.code(base.ctx(env(parameters={"target_position": 2.0, "unit": "rad"}), backend=wide)), ("LIMIT_POSITION", 8))


if __name__ == "__main__":
    unittest.main()
