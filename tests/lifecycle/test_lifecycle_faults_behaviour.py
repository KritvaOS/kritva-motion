"""Behaviour and negative tests of the joint fault model (KOS-MOTION-003 PR-05).

These tests are not mapped to a conformance ID. They cover what the per-ID tests in
test_lifecycle_faults.py do not: input rules, ignored and duplicate inputs, the rules for when the
cause of a fault counts as resolved, the schema of the joint state, invariants after mixed sequences
and determinism. Deterministic and offline. Software evidence only (contract 2.2).
"""
import ast
import json
import unittest
from pathlib import Path

import lifecycle_support as S
from kritva_motion.lifecycle import model

ROOT = Path(__file__).resolve().parents[2]
BOUND = 1000


def confirm(e, cid, t):
    return e.termination_confirmed(cid, "ref-" + cid, t)


def running(e, t=1, jid="joint-1", unit="rad/s"):
    S.ready(e, jid, t)
    cid, _ = S.submit_start(e, S.vel_cmd(0.1, jid=jid, unit=unit), t, t)
    return cid


def clear(e, fault_id, t, jid="joint-1", **kw):
    kw.setdefault("human_operator_attested", True)
    return e.submit(S.env("CLEAR_FAULT", jid, parameters={"fault_id": fault_id}), t, **kw)


def stopped(e, t, jid="joint-1"):
    sid = e.submit(S.stop_cmd(jid), t).command_id
    confirm(e, sid, t)
    return sid


def invariants(test, e, t):
    """What must hold in every reachable state of the joint fault model."""
    ids = []
    for jid in ("joint-1", "joint-c", "joint-p"):
        snap = e.joint_state(jid, t)
        active = [f["fault_id"] for f in e.faults(jid) if f["state"] == "ACTIVE"]
        ids += [f["fault_id"] for f in e.faults(jid)]
        test.assertEqual(snap["health_state"] == "FAULTED", bool(active), (jid, snap))
        test.assertEqual(snap.get("fault_ids", []), active)
        test.assertEqual(snap["health_state"] == "DEGRADED", bool(snap.get("degradation_reasons")) and not active)
        test.assertEqual(snap["control_state"] == "ACTIVE", "active_command_id" in snap, (jid, snap))
        for h in e.joint_transitions(jid):
            (model.check_joint_transition)(h["dimension"], h["from"], h["to"])
    test.assertEqual(len(ids), len(set(ids)))
    for c in e.commands():
        if c["state"] in model.TERMINAL_STATES:
            test.assertEqual(c["phase"], "NONE")
            test.assertIsNotNone(c["reason_code"])


class TestInputRules(unittest.TestCase):
    def test_joint_fault_inputs(self):
        e = S.engine()
        for code in ("FEEDBACK_LOST", "TERMINATION_UNCONFIRMED", "BACKEND_UNAVAILABLE", "NOPE", None):
            with self.assertRaises(ValueError):                              # decided by the engine, or not a joint fault
                e.joint_fault("joint-1", code, 1)
        self.assertEqual(e.faults("joint-1"), [])
        self.assertEqual([x["reason"] for x in e.joint_fault("nope", "TRACKING_ERROR", 1).ignored], ["unknown_joint"])
        e.joint_fault("joint-1", "TRACKING_ERROR", 2)
        self.assertEqual([x["reason"] for x in e.joint_fault("joint-1", "TRACKING_ERROR", 3).ignored], ["duplicate_fault"])
        e.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 4)                 # another code is another fault
        self.assertEqual([f["code"] for f in e.faults("joint-1")], ["TRACKING_ERROR", "JOINT_LIMIT_VIOLATION"])

    def test_backend_fault_inputs(self):
        e = S.engine()
        for code in ("TRACKING_ERROR", "NOPE", None):
            with self.assertRaises(ValueError):
                e.backend_fault(code, 1)
        r = e.backend_fault("BACKEND_UNAVAILABLE", 2, joints=["joint-1", "nope"])
        self.assertEqual([x["reason"] for x in r.ignored], ["unknown_joint"])
        self.assertEqual([len(e.faults(j)) for j in ("joint-1", "joint-c", "joint-p")], [1, 0, 0])
        r = e.backend_fault("BACKEND_UNAVAILABLE", 3)                        # joint-1 already has it; the others get it
        self.assertEqual([x["reason"] for x in r.ignored], ["duplicate_fault"])
        self.assertEqual([len(e.faults(j)) for j in ("joint-1", "joint-c", "joint-p")], [1, 1, 1])
        self.assertEqual([x["event_type"] for x in r.events].count("BACKEND_FAULT_RAISED"), 0)   # the condition was already active
        self.assertEqual([x["reason"] for x in e.backend_fault_cleared(4, code="BACKEND_EXECUTION_FAILURE").ignored],
                         ["no_backend_fault"])
        self.assertEqual([x["event_type"] for x in e.backend_fault_cleared(5, code="BACKEND_UNAVAILABLE").events],
                         ["BACKEND_FAULT_CLEARED"])
        self.assertEqual([x["reason"] for x in e.backend_fault_cleared(6).ignored], ["no_backend_fault"])

    def test_clock_rules_apply_to_the_new_inputs(self):
        e = S.engine()
        e.tick(10)
        for call in (lambda: e.joint_fault("joint-1", "TRACKING_ERROR", 5),
                     lambda: e.backend_fault("BACKEND_UNAVAILABLE", 5),
                     lambda: e.backend_fault_cleared(5)):
            with self.assertRaises(Exception) as cm:
                call()
            self.assertEqual(type(cm.exception).__name__, "ClockError")
        self.assertEqual(e.faults("joint-1"), [])

    def test_no_command_type_is_left_unimplemented(self):
        tree = ast.parse((ROOT / "src" / "kritva_motion" / "lifecycle" / "engine.py").read_text())
        raised = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "NotImplementedError"]
        self.assertEqual(raised, [])
        tree = ast.parse((ROOT / "src" / "kritva_motion" / "lifecycle" / "model.py").read_text())
        self.assertEqual([n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "NotImplementedError"], [])


class TestWhenACauseIsResolved(unittest.TestCase):
    """Interpretation I-27: the rules the engine gives admission as cause_resolved."""

    def test_feedback_lost_is_resolved_by_valid_fresh_feedback_only(self):
        e = S.engine()
        x = running(e, 1)
        e.tick(300)
        confirm(e, x, 301)
        fid = e.faults("joint-1")[0]["fault_id"]
        self.assertEqual(e.faults("joint-1")[0]["code"], "FEEDBACK_LOST")
        r = clear(e, fid, 302)                                               # the feedback is still stale
        self.assertEqual(r.admission.code, "FAULT_NOT_CLEARABLE")
        e.feedback("joint-1", S.sample(0.0), 303)                            # feedback is back, but the fault stays until cleared
        self.assertEqual(e.joint_state("joint-1", 303)["health_state"], "FAULTED")
        ok = clear(e, fid, 304)
        self.assertTrue(ok.admission.accepted, ok.admission)
        self.assertEqual(e.joint_state("joint-1", 304)["health_state"], "READY")
        # another loss is another fault, not the old one coming back
        x2, _ = S.submit_start(e, S.vel_cmd(0.1), 305, 305)
        e.tick(600)
        self.assertEqual([(f["code"], f["state"]) for f in e.faults("joint-1")],
                         [("FEEDBACK_LOST", "CLEARED"), ("FEEDBACK_LOST", "ACTIVE")])
        invariants(self, e, 600)

    def test_backend_fault_is_resolved_when_the_backend_condition_ends(self):
        e = S.engine()
        S.ready(e, t=1)
        e.backend_fault("BACKEND_COMMUNICATION_LOSS", 2, joints=["joint-1"])
        fid = e.faults("joint-1")[0]["fault_id"]
        stopped(e, 3)                                                        # a stop does not end a backend condition
        e.feedback("joint-1", S.sample(0.0), 4)
        self.assertEqual(clear(e, fid, 4).admission.code, "FAULT_NOT_CLEARABLE")
        e.backend_fault_cleared(5)
        e.feedback("joint-1", S.sample(0.0), 6)
        ok = clear(e, fid, 6)
        self.assertTrue(ok.admission.accepted, ok.admission)
        self.assertEqual(e.joint_state("joint-1", 6)["health_state"], "READY")

    def test_stop_related_faults_need_a_confirmed_termination_after_them(self):
        e = S.engine()
        S.ready(e, t=1)
        e.joint_fault("joint-1", "TRACKING_ERROR", 2)
        fid = e.faults("joint-1")[0]["fault_id"]
        self.assertEqual(clear(e, fid, 3).admission.code, "FAULT_NOT_CLEARABLE")
        e.status_report("joint-1", "IDLE", 0, 3)                             # already IDLE: ignored, and not a stop either
        self.assertEqual(clear(e, fid, 3).admission.code, "FAULT_NOT_CLEARABLE")
        stopped(e, 4)
        e.feedback("joint-1", S.sample(0.0), 5)
        self.assertTrue(clear(e, fid, 5).admission.accepted)
        # a stop confirmed before the fault does not count for a later fault
        e.joint_fault("joint-1", "TRACKING_ERROR", 6)
        fid2 = e.faults("joint-1")[1]["fault_id"]
        self.assertEqual(clear(e, fid2, 7).admission.code, "FAULT_NOT_CLEARABLE")

    def test_the_clearance_policy_is_read_per_fault_code(self):
        e = S.engine(S.config(fault_clearance={"TRACKING_ERROR": "CLIENT_AUTHORIZED", "JOINT_LIMIT_VIOLATION": "HUMAN_REQUIRED"}))
        S.ready(e, t=1)
        e.joint_fault("joint-1", "TRACKING_ERROR", 2)
        e.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 3)
        a, b = [f["fault_id"] for f in e.faults("joint-1")]
        stopped(e, 4)
        e.feedback("joint-1", S.sample(0.0), 5)
        env = lambda fid: S.env("CLEAR_FAULT", "joint-1", parameters={"fault_id": fid})
        self.assertEqual(e.submit(env(b), 5).admission.code, "HUMAN_CONFIRMATION_REQUIRED")
        self.assertEqual(e.submit(env(b), 5, human_operator_attested=True).admission.code, None)
        self.assertTrue(e.submit(env(a), 5).admission.accepted)


class TestFaultPropagation(unittest.TestCase):
    def test_a_fault_on_a_held_joint_is_an_advisory_stop_and_the_hold_is_not_assumed_released(self):
        e = S.engine()
        S.ready(e, t=1)
        h = e.submit(S.hold_cmd(), 1).command_id
        e.execution_started(h, "ref-" + h, 1)
        e.hold_confirmed(h, "ref-" + h, 1)
        r = e.joint_fault("joint-1", "TRACKING_ERROR", 2)
        self.assertEqual([(q["op"], q["command_id"], q["backend_reference"], q["cause"]) for q in r.requests],
                         [("request_termination", None, None, "FAULT")])
        snap = e.joint_state("joint-1", 2)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("HOLDING", "FAULTED"))   # follows confirmation
        sid = e.submit(S.stop_cmd(), 3).command_id
        confirm(e, sid, 4)
        self.assertEqual(e.joint_state("joint-1", 4)["control_state"], "IDLE")

    def test_no_advisory_stop_when_the_backend_cannot_take_it(self):
        for label, backend in (("no controlled stop", {"capabilities": {"controlled_stop": False}}),
                               ("unavailable", {"health": "UNAVAILABLE"})):
            with self.subTest(case=label):
                be = S.base.BACKEND.copy()
                be["capabilities"] = dict(be["capabilities"], **backend.get("capabilities", {}))
                be["health"] = backend.get("health", "AVAILABLE")
                e = S.engine(backend=be)
                e.status_report("joint-1", "HOLDING", 0, 1)
                self.assertEqual(e.joint_fault("joint-1", "TRACKING_ERROR", 2).requests, [])
        # on an IDLE joint nothing needs stopping
        e = S.engine()
        S.ready(e, t=1)
        self.assertEqual(e.joint_fault("joint-1", "TRACKING_ERROR", 2).requests, [])

    def test_a_pending_clear_fault_is_not_a_slot_command_and_does_not_block_a_stop(self):
        e = S.engine()
        S.ready(e, t=1)
        e.joint_fault("joint-1", "TRACKING_ERROR", 2)
        fa = e.faults("joint-1")[0]["fault_id"]
        stopped(e, 3)
        e.feedback("joint-1", S.sample(0.0), 4)
        c = clear(e, fa, 4, defer_dispatch=True).command_id
        s = e.submit(S.stop_cmd(), 5)
        self.assertTrue(s.admission.accepted, s.admission)
        self.assertEqual(e.command(c)["state"], "ACCEPTED")
        self.assertEqual(e.command(s.command_id)["references"], s.command_id)   # the STOP did not join the CLEAR_FAULT

    def test_a_fault_ends_a_pending_clear_fault_of_that_joint_only(self):
        e = S.engine()
        S.ready(e, t=1)
        e.joint_fault("joint-1", "TRACKING_ERROR", 2)
        fa = e.faults("joint-1")[0]["fault_id"]
        stopped(e, 3)
        e.feedback("joint-1", S.sample(0.0), 4)
        c = clear(e, fa, 4, defer_dispatch=True).command_id
        e.joint_fault("joint-p", "TRACKING_ERROR", 5)                        # another joint
        self.assertEqual(e.command(c)["state"], "ACCEPTED")
        e.dispatch(c, 5)
        self.assertEqual((e.command(c)["state"], e.command(c)["reason_code"]), ("COMPLETED", "FAULT_CLEARED"))
        self.assertEqual([t["to"] for t in e.command(c)["transitions"]], ["ACCEPTED", "RUNNING", "COMPLETED"])   # I-3

    def test_a_deferred_clear_fault_whose_preconditions_lapse_stays_pending(self):
        e = S.engine()
        S.ready(e, t=1)
        e.joint_fault("joint-1", "TRACKING_ERROR", 2)
        fa = e.faults("joint-1")[0]["fault_id"]
        stopped(e, 3)
        e.feedback("joint-1", S.sample(0.0), 4)
        c = clear(e, fa, 4, defer_dispatch=True).command_id
        r = e.dispatch(c, 400)                                               # required feedback is now stale
        self.assertEqual([x["reason"] for x in r.ignored], ["precondition_not_met:FAULT_NOT_CLEARABLE"])
        self.assertEqual((e.command(c)["state"], e.faults("joint-1")[0]["state"]), ("ACCEPTED", "ACTIVE"))
        e.feedback("joint-1", S.sample(0.0), 401)
        e.dispatch(c, 401)
        self.assertEqual(e.command(c)["state"], "COMPLETED")
        self.assertEqual([x["reason"] for x in e.dispatch(c, 402).ignored], ["terminal"])

    def test_faults_view_returns_copies_and_keeps_cleared_records(self):
        e = S.engine()
        S.ready(e, t=1)
        e.joint_fault("joint-1", "TRACKING_ERROR", 2, "u2")
        view = e.faults("joint-1")
        view[0]["state"] = "CLEARED"
        self.assertEqual(e.faults("joint-1")[0]["state"], "ACTIVE")
        stopped(e, 3)
        e.feedback("joint-1", S.sample(0.0), 4)
        c = clear(e, view[0]["fault_id"], 4, utc="u4").command_id
        f = e.faults("joint-1")[0]
        self.assertEqual((f["state"], f["cleared_at"], f["cleared_ms"], f["cleared_by"], f["raised_at"]),
                         ("CLEARED", "u4", 4, c, "u2"))


class TestFeedbackLoss(unittest.TestCase):
    def test_loss_is_decided_only_for_a_running_command_that_is_not_terminating(self):
        e = S.engine()
        x = running(e, 1)
        e.terminate(x, "CANCEL_REQUESTED", 50)                               # a termination is already outstanding
        e.tick(900)
        self.assertEqual(e.faults("joint-1"), [])                            # no loss on top of it
        e2 = S.engine()
        S.ready(e2, t=1)
        e2.submit(S.vel_cmd(0.1), 1)                                         # accepted, never started
        e2.tick(900)
        self.assertEqual(e2.faults("joint-1"), [])
        e3 = S.engine()
        S.ready(e3, t=1)
        e3.submit(S.vel_cmd(0.1), 1, defer_dispatch=True)
        e3.tick(900)
        self.assertEqual(e3.faults("joint-1"), [])

    def test_loss_is_independent_per_joint(self):
        e = S.engine()
        a = running(e, 1)
        b = running(e, 1, jid="joint-p", unit="m/s")
        e.feedback("joint-p", S.sample(0.0), 150)                            # only joint-p keeps its feedback
        e.tick(250)
        self.assertEqual([f["code"] for f in e.faults("joint-1")], ["FEEDBACK_LOST"])
        self.assertEqual(e.faults("joint-p"), [])
        self.assertEqual((e.command(a)["phase"], e.command(b)["phase"]), ("TERMINATING", "NONE"))
        invariants(self, e, 250)

    def test_optional_feedback_degradation_is_one_reason_once(self):
        cfg = S.config(feedback_required=False, feedback_timeout_policy="DEGRADE")
        e = S.engine(cfg)
        running(e, 1)
        first = e.tick(300)
        again = e.tick(310)
        self.assertEqual(len(first.events), 1)
        self.assertEqual(again.events, [])
        self.assertEqual(e.joint_state("joint-1", 310)["degradation_reasons"], ["FEEDBACK_OPTIONAL_UNAVAILABLE"])
        e.backend_health("DEGRADED", 311)                                    # a second reason
        self.assertEqual(e.joint_state("joint-1", 311)["degradation_reasons"],
                         ["FEEDBACK_OPTIONAL_UNAVAILABLE", "BACKEND_DEGRADED"])
        e.feedback("joint-1", S.sample(0.0), 312)                            # one ends, the health stays DEGRADED
        snap = e.joint_state("joint-1", 312)
        self.assertEqual((snap["health_state"], snap["degradation_reasons"]), ("DEGRADED", ["BACKEND_DEGRADED"]))
        e.backend_health("AVAILABLE", 313)
        self.assertEqual(e.joint_state("joint-1", 313)["health_state"], "READY")

    def test_a_fault_outranks_a_degradation_and_the_degradation_comes_back_after_the_clear(self):
        cfg = S.config(feedback_required=False, feedback_timeout_policy="DEGRADE")
        e = S.engine(cfg)
        x = running(e, 1)
        e.backend_health("DEGRADED", 2)
        e.joint_fault("joint-1", "TRACKING_ERROR", 3)
        snap = e.joint_state("joint-1", 3)
        self.assertEqual((snap["health_state"], snap["fault_ids"], snap["degradation_reasons"]),
                         ("FAULTED", [e.faults("joint-1")[0]["fault_id"]], ["BACKEND_DEGRADED"]))
        invariants(self, e, 3)
        confirm(e, x, 4)
        e.backend_health("AVAILABLE", 5)
        self.assertEqual(e.joint_state("joint-1", 5)["health_state"], "FAULTED")       # the degradation ending does not clear the fault
        invariants(self, e, 5)


class TestJointStateSchema(unittest.TestCase):
    """The joint record is the motion-joint-state schema document (contract 13.2, 13.5) in every state tested."""

    @classmethod
    def setUpClass(cls):
        import jsonschema
        schema = json.loads((ROOT / "contract" / "motion-joint-state.schema.json").read_text())
        cls.validator = jsonschema.Draft202012Validator(schema)

    def check(self, e, t, jid="joint-1"):
        snap = e.joint_state(jid, t)
        errors = sorted(self.validator.iter_errors(snap), key=str)
        self.assertEqual(errors, [], snap)
        return snap

    def test_states_after_faults_and_degradation_validate(self):
        e = S.engine(S.config(feedback_required=False, feedback_timeout_policy="DEGRADE"))
        self.check(e, 0)                                                     # UNKNOWN and READY, no fault
        running(e, 1)
        self.check(e, 1)                                                     # ACTIVE with active_command_id
        e.tick(300)
        self.assertEqual(self.check(e, 300)["health_state"], "DEGRADED")     # degradation_reasons present
        e.joint_fault("joint-1", "TRACKING_ERROR", 301)
        self.assertEqual(self.check(e, 301)["health_state"], "FAULTED")      # fault_ids present
        confirm(e, "cmd-1", 302)
        stopped(e, 303)
        self.check(e, 303)
        clear(e, e.faults("joint-1")[0]["fault_id"], 304)
        self.assertEqual(self.check(e, 304)["health_state"], "DEGRADED")
        e.feedback("joint-1", S.sample(0.2, velocity=0.0), 305, "2026-11-09T00:00:05Z")
        self.assertEqual(self.check(e, 305)["health_state"], "READY")
        self.assertEqual(self.check(e, 700)["is_current"], False)            # STALE implies is_current false

    def test_required_feedback_lost_state_validates(self):
        e = S.engine()
        x = running(e, 1)
        e.tick(300)
        snap = self.check(e, 300)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("ACTIVE", "FAULTED"))
        confirm(e, x, 301)
        self.assertEqual(self.check(e, 301)["control_state"], "IDLE")
        e.backend_fault("BACKEND_UNAVAILABLE", 302)
        for jid in ("joint-1", "joint-c", "joint-p"):
            self.check(e, 302, jid)


class TestInvariantsAndDeterminism(unittest.TestCase):
    def script(self):
        """A mixed sequence: movement, cancel, faults, recovery, degradation, backend loss."""
        e = S.engine(S.config(fault_clearance={"TRACKING_ERROR": "CLIENT_AUTHORIZED"}))
        out = []
        S.ready(e, t=1)
        S.ready(e, "joint-p", 1)
        a = e.submit(S.vel_cmd(0.1), 1, "u1")
        out.append(a)
        out.append(e.execution_started(a.command_id, "ref-" + a.command_id, 2, "u2"))
        b = e.submit(S.vel_cmd(0.1, jid="joint-p", unit="m/s"), 2, "u2")
        out.append(b)
        out.append(e.execution_started(b.command_id, "ref-" + b.command_id, 3, "u3"))
        out.append(e.submit(S.cancel_cmd(a.command_id), 5, "u5"))
        out.append(e.joint_fault("joint-1", "TRACKING_ERROR", 6, "u6"))
        out.append(e.backend_fault("BACKEND_COMMUNICATION_LOSS", 7, "u7", joints=["joint-p"]))
        out.append(confirm(e, a.command_id, 8))
        out.append(e.tick(1007, "u1007"))
        out.append(e.backend_fault_cleared(1008, "u1008"))
        out.append(e.submit(S.stop_cmd(), 1009, "u1009"))
        out.append(e.termination_confirmed("cmd-4", "ref-cmd-4", 1010, "u1010"))
        out.append(e.feedback("joint-1", S.sample(0.0), 1011, "u1011"))
        out.append(e.submit(S.env("CLEAR_FAULT", "joint-1", parameters={"fault_id": "fault-1"}), 1012, "u1012"))
        return e, [(x.admission, x.command_id, x.requests, x.events, x.ignored) for x in out]

    def test_invariants_hold_at_every_step_and_at_the_end(self):
        e, _ = self.script()
        invariants(self, e, 1012)
        self.assertEqual([f["state"] for f in e.faults("joint-1")][:1], ["CLEARED"])

    def test_same_inputs_give_identical_outputs(self):
        e1, o1 = self.script()
        e2, o2 = self.script()
        self.assertEqual(o1, o2)
        self.assertEqual((e1.commands(), e1.faults("joint-1"), e1.faults("joint-p"), e1.joint_transitions("joint-1")),
                         (e2.commands(), e2.faults("joint-1"), e2.faults("joint-p"), e2.joint_transitions("joint-1")))


class TestModel(unittest.TestCase):
    def test_outcome_with_fault_causes(self):
        f = model.outcome_of_causes
        self.assertEqual(f(["FAULT"], ["TRACKING_ERROR"]), ("FAILED", "TRACKING_ERROR"))
        self.assertEqual(f(["STOP_REQUESTED", "FAULT"], ["JOINT_LIMIT_VIOLATION"]), ("FAILED", "JOINT_LIMIT_VIOLATION"))
        self.assertEqual(f(["EXECUTION_TIMEOUT", "FAULT", "FAULT"], ["FEEDBACK_LOST", "TRACKING_ERROR"]), ("FAILED", "FEEDBACK_LOST"))
        self.assertEqual(f(["CANCEL_REQUESTED", "STOP_REQUESTED"]), ("CANCELLED", "STOPPED"))
        for bad in ([], ["FAULT"], ["FAULT", "CANCEL_REQUESTED"]):
            with self.assertRaises(model.IllegalTransition):
                f(bad)

    def test_every_fault_code_is_a_failed_reason_code(self):
        for code in model.JOINT_FAULT_CODES + model.BACKEND_FAULT_CODES:
            self.assertIn(code, model.REASON_CODES["FAILED"])
        self.assertEqual(set(model.REPORTED_JOINT_FAULTS) | {"FEEDBACK_LOST", "TERMINATION_UNCONFIRMED"}, set(model.JOINT_FAULT_CODES))


if __name__ == "__main__":
    unittest.main()
