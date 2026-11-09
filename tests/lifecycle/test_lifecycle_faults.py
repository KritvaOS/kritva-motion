"""Conformance tests of faults, degradation, recovery and CLEAR_FAULT (AC-307).

Each method is the single executable test named by one IN_SCOPE entry of
tests/manifest/conformance_manifest.json for the IDs that KOS-MOTION-003 PR-05 covers. The method
name is the ID with hyphens replaced by underscores. Deterministic and offline. Software evidence
only: every confirmation, report and fault here is a supplied input, never proof that anything
stopped, recovered or failed physically (contract 2.4, 17.5).

Configuration (tests/validator/test_admission.py): termination_confirm_timeout_ms 1000, max_feedback_age_ms
200 (a sample is fresh while its age is at most 200), feedback required, default execution timeout 5000.
Faults raised by the backend are TRACKING_ERROR and JOINT_LIMIT_VIOLATION (joint) and the BACKEND_*
codes (backend). A fault with no configured clearance policy is HUMAN_REQUIRED (contract 13.6), so a
CLEAR_FAULT is submitted with human_operator_attested=True unless a test says otherwise.
"""
import unittest

import lifecycle_support as S
from kritva_motion.lifecycle import model

BOUND = 1000
POLICY_ALL = {"BACKEND_DEGRADED": ["SET_POSITION", "SET_VELOCITY", "HOLD"]}


def states(e, *ids):
    return [(e.command(i)["state"], e.command(i)["reason_code"]) for i in ids]


def ops(*results):
    return [q["op"] for r in results for q in r.requests]


def running_move(e, t=1, jid="joint-1", unit="rad/s", **over):
    """A SET_VELOCITY command accepted and started at t on a joint made ready at t."""
    S.ready(e, jid, t)
    cid, _ = S.submit_start(e, S.vel_cmd(0.1, jid=jid, unit=unit, **over), t, t)
    return cid


def confirm(e, cid, t):
    return e.termination_confirmed(cid, "ref-" + cid, t)


def clear(e, fault_id, t, jid="joint-1", **kw):
    kw.setdefault("human_operator_attested", True)
    return e.submit(S.env("CLEAR_FAULT", jid, parameters={"fault_id": fault_id}), t, **kw)


def fresh(e, t, jid="joint-1", pos=0.0):
    e.feedback(jid, S.sample(pos), t)


def stopped(e, t, jid="joint-1"):
    """A confirmed STOP at t: the backend confirms the controlled-stop condition."""
    sid = e.submit(S.stop_cmd(jid), t).command_id
    confirm(e, sid, t)
    return sid


class TestFaultConformance(unittest.TestCase):
    # ------------------------------------------------------------------ feedback (11.5, 13.5)

    def test_CT_FB_04(self):
        """Required feedback lost during execution raises FEEDBACK_LOST and requests controlled stop; HOLD is not assumed."""
        e = S.engine()
        cid = running_move(e, 1)
        self.assertEqual(e.tick(201).requests, [])                       # age 200 is still fresh: no loss
        self.assertEqual(e.faults("joint-1"), [])
        res = e.tick(202, "u202")                                        # age 201: required feedback is lost
        self.assertEqual([(f["code"], f["fault_class"], f["state"]) for f in e.faults("joint-1")],
                         [("FEEDBACK_LOST", "JOINT", "ACTIVE")])
        fid = e.faults("joint-1")[0]["fault_id"]
        self.assertEqual([(q["op"], q["cause"], q["command_id"], q["fault_id"]) for q in res.requests],
                         [("request_termination", "FAULT", cid, fid)])    # a controlled stop, not a hold
        self.assertIn("JOINT_FAULT_RAISED", [x["event_type"] for x in res.events])
        c = e.command(cid)
        self.assertEqual((c["state"], c["phase"], c["reason_code"]), ("RUNNING", "TERMINATING", None))
        self.assertEqual([x["cause"] for x in c["termination"]["causes"]], ["FAULT"])
        snap = e.joint_state("joint-1", 202)
        self.assertEqual((snap["health_state"], snap["control_state"], snap["fault_ids"]), ("FAULTED", "ACTIVE", [fid]))
        e.tick(300)                                                      # one loss is one fault
        self.assertEqual(len(e.faults("joint-1")), 1)
        confirm(e, cid, 400)
        self.assertEqual(states(e, cid), [("FAILED", "FEEDBACK_LOST")])
        snap = e.joint_state("joint-1", 400)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("IDLE", "FAULTED"))   # stopped, never HOLDING
        self.assertEqual(e.submit(S.hold_cmd(), 401).admission.code, "TARGET_FAULTED")
        # an INVALID sample is a loss at once
        e2 = S.engine()
        x2 = running_move(e2, 1)
        r2 = e2.feedback("joint-1", S.sample(0.0, validity="INVALID"), 50)
        self.assertEqual([f["code"] for f in e2.faults("joint-1")], ["FEEDBACK_LOST"])
        self.assertEqual([(q["op"], q["cause"]) for q in r2.requests], [("request_termination", "FAULT")])
        self.assertEqual(e2.command(x2)["phase"], "TERMINATING")
        # a pending HOLD is execution too, and it is stopped, not repeated
        e3 = S.engine()
        S.ready(e3, t=1)
        hid = e3.submit(S.hold_cmd(), 1).command_id
        e3.execution_started(hid, "ref-" + hid, 2)
        r3 = e3.tick(300)
        self.assertEqual([(q["op"], q["cause"]) for q in r3.requests], [("request_termination", "FAULT")])
        confirm(e3, hid, 301)
        self.assertEqual(states(e3, hid), [("FAILED", "FEEDBACK_LOST")])
        self.assertEqual(e3.joint_state("joint-1", 301)["control_state"], "IDLE")
        # no loss is raised when nothing is executing
        e4 = S.engine()
        S.ready(e4, t=1)
        e4.tick(5000)
        self.assertEqual((e4.faults("joint-1"), e4.joint_state("joint-1", 5000)["health_state"]), ([], "READY"))

    def test_CT_FB_05(self):
        """Non-required feedback loss gives DEGRADED and non-feedback commands continue."""
        cfg = S.config(feedback_required=False, feedback_timeout_policy="DEGRADE",
                       degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_VELOCITY"]})
        e = S.engine(cfg)
        S.ready(e, t=1)
        cid, _ = S.submit_start(e, S.vel_cmd(0.1, duration=1000), 1, 1)
        self.assertEqual(e.tick(201).events, [])
        res = e.tick(202)                                                # the optional feedback is lost
        snap = e.joint_state("joint-1", 202)
        self.assertEqual((snap["health_state"], snap["control_state"], snap["degradation_reasons"]),
                         ("DEGRADED", "ACTIVE", ["FEEDBACK_OPTIONAL_UNAVAILABLE"]))
        self.assertEqual((res.requests, e.faults("joint-1")), ([], []))   # no stop, no fault
        c = e.command(cid)
        self.assertEqual((c["state"], c["phase"]), ("RUNNING", "NONE"))   # the command continues
        e.tick(1001)                                                     # and completes from the monotonic clock
        self.assertEqual(states(e, cid), [("COMPLETED", "DURATION_ELAPSED")])
        snap = e.joint_state("joint-1", 1001)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("IDLE", "DEGRADED"))
        # the policy permits only SET_VELOCITY: a SET_VELOCITY is accepted, SET_POSITION is not
        self.assertEqual(e.submit(S.pos_cmd(0.2), 1002).admission.code, "TARGET_DEGRADED")
        self.assertEqual(e.submit(S.hold_cmd(), 1002).admission.code, "TARGET_DEGRADED")
        self.assertTrue(e.submit(S.vel_cmd(0.1), 1002).admission.accepted)
        # feedback back: the reason ends and the health returns to READY, the running command untouched
        e.feedback("joint-1", S.sample(0.0), 1100)
        snap = e.joint_state("joint-1", 1100)
        self.assertEqual(snap["health_state"], "READY")
        self.assertNotIn("degradation_reasons", snap)
        # feedback that never arrived is the same loss, 200 ms after the start
        e2 = S.engine(cfg)
        e2.status_report("joint-1", "IDLE", 0, 1)
        m2, _ = S.submit_start(e2, S.vel_cmd(0.1), 1, 1)
        e2.tick(201)
        self.assertEqual(e2.joint_state("joint-1", 201)["health_state"], "READY")
        e2.tick(202)
        self.assertEqual(e2.joint_state("joint-1", 202)["feedback_status"], "MISSING")
        self.assertEqual(e2.joint_state("joint-1", 202)["health_state"], "DEGRADED")
        self.assertEqual(e2.command(m2)["state"], "RUNNING")

    def test_CT_FB_06(self):
        """is_current is true only when feedback is valid and fresh."""
        e = S.engine()
        s = e.joint_state("joint-1", 0)
        self.assertEqual((s["feedback_status"], s["is_current"]), ("MISSING", False))
        self.assertNotIn("measured_position", s)
        e.feedback("joint-1", S.sample(0.3), 10, "2026-11-09T00:00:10Z")
        for t, status, current in ((10, "VALID", True), (210, "VALID", True), (211, "STALE", False)):
            with self.subTest(t=t):
                s = e.joint_state("joint-1", t)
                self.assertEqual((s["feedback_status"], s["is_current"]), (status, current))
                self.assertEqual(s["measured_position"], 0.3)                 # last-known values stay reported
                self.assertEqual(s["last_valid_feedback_at"], "2026-11-09T00:00:10Z")
        e.feedback("joint-1", S.sample(0.9, validity="INVALID"), 300)
        s = e.joint_state("joint-1", 300)
        self.assertEqual((s["feedback_status"], s["is_current"], s["measured_position"]), ("INVALID", False, 0.3))
        e.feedback("joint-1", S.sample(0.4), 310)
        s = e.joint_state("joint-1", 310)
        self.assertEqual((s["feedback_status"], s["is_current"], s["measured_position"]), ("VALID", True, 0.4))
        # after a fault the record reports the same rule
        e2 = S.engine()
        running_move(e2, 1)
        e2.joint_fault("joint-1", "TRACKING_ERROR", 5)
        self.assertTrue(e2.joint_state("joint-1", 5)["is_current"])           # valid and fresh: current even though faulted
        self.assertFalse(e2.joint_state("joint-1", 500)["is_current"])        # same record, now stale

    # ------------------------------------------------------------------ fault propagation (13.4, 13.5)

    def test_CT_FLT_01(self):
        """A joint fault fails every non-terminal command on the joint with the fault code and faults the joint."""
        # a running movement
        e = S.engine()
        xid = running_move(e, 1)
        other = running_move(e, 1, jid="joint-p", unit="m/s")
        res = e.joint_fault("joint-1", "TRACKING_ERROR", 5, "u5")
        fault = e.faults("joint-1")[0]
        self.assertEqual((fault["code"], fault["fault_class"], fault["joint_id"], fault["state"]),
                         ("TRACKING_ERROR", "JOINT", "joint-1", "ACTIVE"))
        self.assertEqual([(q["op"], q["command_id"], q["cause"]) for q in res.requests],
                         [("request_termination", xid, "FAULT")])
        self.assertEqual(e.joint_state("joint-1", 5)["health_state"], "FAULTED")
        self.assertEqual(e.command(xid)["state"], "RUNNING")                  # not failed before the confirmation
        confirm(e, xid, 6)
        self.assertEqual(states(e, xid), [("FAILED", "TRACKING_ERROR")])
        self.assertEqual(e.command(xid)["phase"], "NONE")
        self.assertEqual(e.command(other)["state"], "RUNNING")                # another joint is not affected
        self.assertEqual(e.joint_state("joint-p", 6)["health_state"], "READY")
        # accepted and never dispatched: nothing to terminate, it fails at once
        e2 = S.engine()
        S.ready(e2, t=1)
        nid = e2.submit(S.vel_cmd(0.1), 1, defer_dispatch=True).command_id
        r2 = e2.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 2)
        self.assertEqual(states(e2, nid), [("FAILED", "JOINT_LIMIT_VIOLATION")])
        self.assertEqual(r2.requests, [])
        # dispatched, start not yet confirmed
        e3 = S.engine()
        S.ready(e3, t=1)
        d = e3.submit(S.vel_cmd(0.1), 1).command_id
        r3 = e3.joint_fault("joint-1", "TRACKING_ERROR", 2)
        self.assertEqual([(q["op"], q["cause"]) for q in r3.requests], [("request_termination", "FAULT")])
        self.assertEqual((e3.command(d)["state"], e3.command(d)["phase"]), ("ACCEPTED", "TERMINATING"))
        e3.execution_started(d, "ref-" + d, 3)                                # a late start never revives it
        confirm(e3, d, 4)
        self.assertEqual(states(e3, d), [("FAILED", "TRACKING_ERROR")])
        # a HOLD pending engagement
        e4 = S.engine()
        S.ready(e4, t=1)
        h = e4.submit(S.hold_cmd(), 1).command_id
        e4.execution_started(h, "ref-" + h, 2)
        e4.joint_fault("joint-1", "TRACKING_ERROR", 3)
        confirm(e4, h, 4)
        self.assertEqual(states(e4, h), [("FAILED", "TRACKING_ERROR")])
        self.assertEqual(e4.joint_state("joint-1", 4)["health_state"], "FAULTED")

    def test_CT_FLT_02(self):
        """A backend fault propagates to every affected joint and command record."""
        e = S.engine()
        a = running_move(e, 1)
        b = running_move(e, 1, jid="joint-p", unit="m/s")
        res = e.backend_fault("BACKEND_COMMUNICATION_LOSS", 5, "u5")
        self.assertEqual(res.events[0]["event_type"], "BACKEND_FAULT_RAISED")
        self.assertEqual(res.events[0]["stream"], {"kind": "backend", "id": "backend"})
        for jid in ("joint-1", "joint-p"):                                    # one fault record per affected joint
            fs = e.faults(jid)
            self.assertEqual([(f["code"], f["fault_class"]) for f in fs], [("BACKEND_COMMUNICATION_LOSS", "BACKEND")])
            self.assertEqual(e.joint_state(jid, 5)["health_state"], "FAULTED")
        self.assertEqual({(q["command_id"], q["cause"]) for q in res.requests if q["command_id"]}, {(a, "FAULT"), (b, "FAULT")})
        # joint-c has no command and its control state was never established: the stop request has nothing to bind to
        self.assertEqual([(q["target"]["id"], q["backend_reference"]) for q in res.requests if q["command_id"] is None],
                         [("joint-c", None)])
        confirm(e, a, 6)
        confirm(e, b, 7)
        self.assertEqual(states(e, a, b), [("FAILED", "BACKEND_COMMUNICATION_LOSS")] * 2)
        # the backend becoming healthy ends the backend condition and clears no joint fault record
        r = e.backend_fault_cleared(8, "u8")
        self.assertEqual([x["event_type"] for x in r.events], ["BACKEND_FAULT_CLEARED"])
        for jid in ("joint-1", "joint-p"):
            self.assertEqual(e.joint_state(jid, 8)["health_state"], "FAULTED")
            self.assertEqual([f["state"] for f in e.faults(jid)], ["ACTIVE"])
        # only the listed joints are affected; an unconfirmed termination fails with that reason
        e2 = S.engine()
        c = running_move(e2, 1)
        d = running_move(e2, 1, jid="joint-p", unit="m/s")
        e2.backend_fault("BACKEND_EXECUTION_FAILURE", 5, joints=["joint-1"])
        self.assertEqual((e2.faults("joint-p"), e2.command(d)["phase"]), ([], "NONE"))
        e2.tick(5 + BOUND)
        self.assertEqual(states(e2, c), [("FAILED", "TERMINATION_UNCONFIRMED")])
        self.assertEqual([f["code"] for f in e2.faults("joint-1")], ["BACKEND_EXECUTION_FAILURE", "TERMINATION_UNCONFIRMED"])
        self.assertEqual(e2.joint_state("joint-1", 5 + BOUND)["control_state"], "UNKNOWN")

    def test_CT_FLT_03(self):
        """The state after a fault is reported with fault_ids, last-known values and is_current = false as applicable."""
        e = S.engine()
        S.ready(e, t=1)
        e.feedback("joint-1", S.sample(0.3), 100, "2026-11-09T00:00:00Z")
        cid, _ = S.submit_start(e, S.vel_cmd(0.1), 101, 101)
        e.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 150)
        confirm(e, cid, 160)
        fid = e.faults("joint-1")[0]["fault_id"]
        snap = e.joint_state("joint-1", 160)
        self.assertEqual((snap["health_state"], snap["control_state"], snap["fault_ids"]), ("FAULTED", "IDLE", [fid]))
        self.assertEqual((snap["feedback_status"], snap["is_current"], snap["measured_position"]), ("VALID", True, 0.3))
        later = e.joint_state("joint-1", 400)                                   # the feedback is now older than 200 ms
        self.assertEqual((later["health_state"], later["fault_ids"]), ("FAULTED", [fid]))
        self.assertEqual((later["feedback_status"], later["is_current"]), ("STALE", False))
        self.assertEqual((later["measured_position"], later["last_valid_feedback_at"]), (0.3, "2026-11-09T00:00:00Z"))
        # with no valid feedback at all there are no values to report
        e2 = S.engine()
        e2.joint_fault("joint-1", "TRACKING_ERROR", 1)
        s2 = e2.joint_state("joint-1", 1)
        self.assertEqual((s2["health_state"], s2["feedback_status"], s2["is_current"]), ("FAULTED", "MISSING", False))
        self.assertNotIn("measured_position", s2)
        self.assertEqual(len(s2["fault_ids"]), 1)

    def test_CT_FLT_05(self):
        """Interrupted commands do not resume after recovery."""
        e = S.engine()
        xid = running_move(e, 1)
        e.joint_fault("joint-1", "TRACKING_ERROR", 5)
        confirm(e, xid, 6)
        fid = e.faults("joint-1")[0]["fault_id"]
        n_requests = []
        # recovery: the confirmation above is the stop, then an authorized CLEAR_FAULT
        fresh(e, 7)
        r = clear(e, fid, 8)
        self.assertTrue(r.admission.accepted, r.admission)
        self.assertEqual(e.joint_state("joint-1", 8)["health_state"], "READY")
        self.assertEqual(states(e, xid), [("FAILED", "TRACKING_ERROR")])
        n_requests += ops(r)
        for res in (e.tick(9), e.feedback("joint-1", S.sample(0.0), 10), e.tick(500),
                    e.execution_started(xid, "ref-" + xid, 501), e.dispatch(xid, 502)):
            n_requests += ops(res)
        self.assertEqual(n_requests, [])                                       # nothing is dispatched again
        self.assertEqual(states(e, xid), [("FAILED", "TRACKING_ERROR")])
        self.assertEqual([c["command_id"] for c in e.commands() if c["state"] not in model.TERMINAL_STATES], [])
        self.assertEqual(e.joint_state("joint-1", 502)["control_state"], "IDLE")
        self.assertNotIn("active_command_id", e.joint_state("joint-1", 502))

    # ------------------------------------------------------------------ the joint state machine (13.3)

    def test_CT_FLT_07(self):
        """The joint state machine transitions exactly as in 13.3 (table-driven)."""
        control_ok = {("IDLE", "ACTIVE"), ("ACTIVE", "IDLE"), ("IDLE", "HOLDING"), ("HOLDING", "ACTIVE"),
                      ("HOLDING", "IDLE"), ("IDLE", "UNKNOWN"), ("ACTIVE", "UNKNOWN"), ("HOLDING", "UNKNOWN"),
                      ("UNKNOWN", "IDLE"), ("UNKNOWN", "ACTIVE"), ("UNKNOWN", "HOLDING")}
        health_ok = {("READY", "DEGRADED"), ("DEGRADED", "READY"), ("READY", "FAULTED"), ("DEGRADED", "FAULTED"),
                     ("FAULTED", "READY"), ("FAULTED", "DEGRADED")}
        for dim, states_, ok in (("control", model.CONTROL_STATES, control_ok), ("health", model.HEALTH_STATES, health_ok)):
            for a in states_:
                for b in states_:
                    if a == b:
                        continue
                    with self.subTest(dimension=dim, frm=a, to=b):
                        if (a, b) in ok:
                            model.check_joint_transition(dim, a, b)
                        else:
                            with self.assertRaises(model.IllegalTransition):
                                model.check_joint_transition(dim, a, b)
        self.assertEqual(set(model.CONTROL_TRANSITIONS), control_ok)
        self.assertEqual(set(model.HEALTH_TRANSITIONS), health_ok)
        # the engine makes every listed change, and only through the table
        seen_control, seen_health = set(), set()

        def note(e, jid="joint-1"):
            for h in e.joint_transitions(jid):
                (seen_control if h["dimension"] == "control" else seen_health).add((h["from"], h["to"]))

        cfg = S.config(feedback_required=False, feedback_timeout_policy="DEGRADE",
                       degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_VELOCITY"]})
        e = S.engine(cfg)
        e.status_report("joint-1", "IDLE", 0, 1)                                # UNKNOWN to IDLE
        fresh(e, 1)
        S.submit_start(e, S.vel_cmd(0.1, duration=50), 1, 1)                    # IDLE to ACTIVE
        e.tick(51)                                                              # ACTIVE to IDLE (completion)
        hid = e.submit(S.hold_cmd(), 52).command_id
        e.execution_started(hid, "ref-" + hid, 53)
        e.hold_confirmed(hid, "ref-" + hid, 54)                                 # IDLE to HOLDING
        mid = e.submit(S.vel_cmd(0.1), 55).command_id
        e.execution_started(mid, "ref-" + mid, 56)                              # HOLDING to ACTIVE
        e.tick(300)                                                             # optional feedback lost: READY to DEGRADED
        e.joint_fault("joint-1", "TRACKING_ERROR", 301)                         # DEGRADED to FAULTED
        confirm(e, mid, 302)
        stopped(e, 303)
        f1 = e.faults("joint-1")[0]["fault_id"]
        self.assertTrue(clear(e, f1, 304).admission.accepted)                   # FAULTED to DEGRADED (the reason remains)
        fresh(e, 305)                                                           # DEGRADED to READY
        e.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 306)                  # READY to FAULTED
        stopped(e, 307)
        self.assertTrue(clear(e, e.faults("joint-1")[1]["fault_id"], 308).admission.accepted)   # FAULTED to READY
        note(e)
        # HOLDING to IDLE (a confirmed stop on a held joint) and HOLDING to UNKNOWN (backend lost while holding)
        e2 = S.engine()
        S.ready(e2, t=1)
        h2 = e2.submit(S.hold_cmd(), 1).command_id
        e2.execution_started(h2, "ref-" + h2, 1)
        e2.hold_confirmed(h2, "ref-" + h2, 1)
        stopped(e2, 2)
        e3 = S.engine()
        S.ready(e3, t=1)
        h3 = e3.submit(S.hold_cmd(), 1).command_id
        e3.execution_started(h3, "ref-" + h3, 1)
        e3.hold_confirmed(h3, "ref-" + h3, 1)
        e3.backend_health("FAULTED", 2)
        # ACTIVE to UNKNOWN (backend lost while running) and UNKNOWN to ACTIVE or HOLDING by a fresh report
        e4 = S.engine()
        running_move(e4, 1)
        e4.backend_health("UNAVAILABLE", 2)
        e4.backend_health("AVAILABLE", 3)
        e4.status_report("joint-1", "ACTIVE", 0, 3)
        e5 = S.engine()
        e5.status_report("joint-1", "HOLDING", 0, 1)
        # IDLE to UNKNOWN (a STOP that is never confirmed)
        e6 = S.engine()
        S.ready(e6, t=1)
        e6.submit(S.stop_cmd(), 2)
        e6.tick(2 + BOUND)
        for x in (e2, e3, e4, e5, e6):
            note(x)
        self.assertEqual(seen_control, control_ok)
        self.assertEqual(seen_health, health_ok)
        # a change the table does not list is refused and changes nothing
        e7 = S.engine()
        running_move(e7, 1)
        for dim, to in (("control", "HOLDING"), ("health", "UNKNOWN")):
            with self.assertRaises(model.IllegalTransition):
                (e7._set_control if dim == "control" else e7._set_health)("joint-1", to, "test", 9)
        snap = e7.joint_state("joint-1", 9)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("ACTIVE", "READY"))

    def test_CT_FLT_08(self):
        """FAILED and FAULTED are independent: a command can fail with the joint READY, and a joint fault can occur with no active command."""
        e = S.engine()
        S.ready(e, t=1)
        d = e.submit(S.vel_cmd(0.1, deadline_ms=100), 1, defer_dispatch=True).command_id
        e.tick(101)
        self.assertEqual(states(e, d), [("FAILED", "DEADLINE_EXPIRED")])
        snap = e.joint_state("joint-1", 101)
        self.assertEqual((snap["health_state"], e.faults("joint-1")), ("READY", []))      # FAILED is not FAULTED
        self.assertNotIn("fault_ids", snap)
        # a unconfirmed-bound failure of a rejected STOP leaves the joint READY too
        e1 = S.engine()
        S.ready(e1, t=1)
        s1 = e1.submit(S.stop_cmd(), 2).command_id
        e1.termination_refused(s1, "ref-" + s1, 3)
        self.assertEqual((states(e1, s1), e1.joint_state("joint-1", 3)["health_state"]),
                         ([("FAILED", "BACKEND_REJECTED_DISPATCH")], "READY"))
        # a joint fault with no command anywhere
        e2 = S.engine()
        S.ready(e2, t=1)
        r = e2.joint_fault("joint-1", "TRACKING_ERROR", 2)
        self.assertEqual(e2.commands(), [])
        snap = e2.joint_state("joint-1", 2)
        self.assertEqual((snap["health_state"], snap["control_state"], len(snap["fault_ids"])), ("FAULTED", "IDLE", 1))
        self.assertEqual(r.requests, [])                                        # an IDLE joint needs no stop
        self.assertNotIn("active_command_id", snap)

    def test_CT_FLT_09(self):
        """DEGRADED while a command is running preserves control_state = ACTIVE; clearing the degradation never reports IDLE."""
        cfg = S.config(feedback_required=False, feedback_timeout_policy="DEGRADE",
                       degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_VELOCITY"]})
        e = S.engine(cfg)
        S.ready(e, t=1)
        cid, _ = S.submit_start(e, S.vel_cmd(0.1), 1, 1)
        controls = [h for h in e.joint_transitions("joint-1") if h["dimension"] == "control"]
        e.tick(500)
        snap = e.joint_state("joint-1", 500)
        self.assertEqual((snap["health_state"], snap["control_state"], snap["active_command_id"]), ("DEGRADED", "ACTIVE", cid))
        e.feedback("joint-1", S.sample(0.0), 510)                              # the degradation clears
        snap = e.joint_state("joint-1", 510)
        self.assertEqual((snap["health_state"], snap["control_state"], snap["active_command_id"]), ("READY", "ACTIVE", cid))
        self.assertEqual([h for h in e.joint_transitions("joint-1") if h["dimension"] == "control"], controls)   # no control change at all
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        health = [(h["from"], h["to"]) for h in e.joint_transitions("joint-1") if h["dimension"] == "health"]
        self.assertEqual(health, [("READY", "DEGRADED"), ("DEGRADED", "READY")])
        # a degraded backend is the other reason, with the same rule
        e2 = S.engine(S.config(degradation_policy=POLICY_ALL))
        x2 = running_move(e2, 1)
        e2.backend_health("DEGRADED", 2)
        s2 = e2.joint_state("joint-1", 2)
        self.assertEqual((s2["health_state"], s2["control_state"], s2["degradation_reasons"]), ("DEGRADED", "ACTIVE", ["BACKEND_DEGRADED"]))
        e2.backend_health("AVAILABLE", 3)
        s2 = e2.joint_state("joint-1", 3)
        self.assertEqual((s2["health_state"], s2["control_state"], s2["active_command_id"]), ("READY", "ACTIVE", x2))
        self.assertEqual(e2.command(x2)["state"], "RUNNING")

    # ------------------------------------------------------------------ CLEAR_FAULT and recovery (13.6, 13.9)

    def test_CT_FLT_10(self):
        """After an unconfirmed termination control_state is UNKNOWN; CLEAR_FAULT is refused until a confirmed stop."""
        e = S.engine()
        xid = running_move(e, 1)
        e.terminate(xid, "CANCEL_REQUESTED", 2)
        e.tick(2 + BOUND)
        self.assertEqual(states(e, xid), [("FAILED", "TERMINATION_UNCONFIRMED")])
        snap = e.joint_state("joint-1", 2 + BOUND)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("UNKNOWN", "FAULTED"))
        fid = e.faults("joint-1")[0]["fault_id"]
        t = 3 + BOUND
        fresh(e, t)
        r = clear(e, fid, t)                                                     # even with the human attribute
        self.assertEqual((r.admission.accepted, r.admission.code, r.command_id), (False, "FAULT_NOT_CLEARABLE", None))
        self.assertEqual(e.joint_state("joint-1", t)["health_state"], "FAULTED")
        sid = e.submit(S.stop_cmd(), t + 1).command_id                           # the recovery step
        self.assertEqual(clear(e, fid, t + 2).admission.code, "FAULT_NOT_CLEARABLE")   # a stop that is not confirmed is not recovery
        confirm(e, sid, t + 3)
        self.assertEqual(e.joint_state("joint-1", t + 3)["control_state"], "IDLE")
        fresh(e, t + 4)
        ok = clear(e, fid, t + 4)
        self.assertTrue(ok.admission.accepted, ok.admission)
        self.assertEqual(states(e, ok.command_id), [("COMPLETED", "FAULT_CLEARED")])
        snap = e.joint_state("joint-1", t + 4)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("IDLE", "READY"))

    def test_CT_FLT_11(self):
        """CLEAR_FAULT clears exactly one fault; health returns to READY only when no other fault or degradation remains; a fault_id not on the target gives FAULT_NOT_FOUND."""
        cfg = S.config(fault_clearance={"TRACKING_ERROR": "CLIENT_AUTHORIZED"})
        e = S.engine(cfg)
        S.ready(e, t=1)
        e.joint_fault("joint-1", "TRACKING_ERROR", 2)
        e.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 3)
        f1, f2 = [f["fault_id"] for f in e.faults("joint-1")]
        stopped(e, 4)                                                            # resolves the stop-related causes
        fresh(e, 5)
        # a CLIENT_AUTHORIZED fault needs no human attribute; the other one does
        r1 = e.submit(S.env("CLEAR_FAULT", "joint-1", parameters={"fault_id": f1}), 5)
        self.assertTrue(r1.admission.accepted, r1.admission)
        self.assertEqual(states(e, r1.command_id), [("COMPLETED", "FAULT_CLEARED")])
        self.assertEqual([(f["fault_id"], f["state"]) for f in e.faults("joint-1")], [(f1, "CLEARED"), (f2, "ACTIVE")])
        snap = e.joint_state("joint-1", 5)
        self.assertEqual((snap["health_state"], snap["fault_ids"]), ("FAULTED", [f2]))   # one fault is left
        self.assertEqual(e.submit(S.env("CLEAR_FAULT", "joint-1", parameters={"fault_id": f2}), 6).admission.code,
                         "HUMAN_CONFIRMATION_REQUIRED")
        self.assertEqual(e.faults("joint-1")[0]["cleared_by"], r1.command_id)
        # an already cleared fault, an unknown fault and a fault of another joint are not found
        e.joint_fault("joint-p", "TRACKING_ERROR", 6)
        other = e.faults("joint-p")[0]["fault_id"]
        n = len(e.commands())
        for fid in (f1, "fault-999", other):
            with self.subTest(fault_id=fid):
                r = clear(e, fid, 7)
                self.assertEqual((r.admission.accepted, r.admission.code), (False, "FAULT_NOT_FOUND"))
        self.assertEqual(len(e.commands()), n)
        self.assertEqual(e.joint_state("joint-p", 7)["health_state"], "FAULTED")   # the other joint keeps its own fault
        r2 = clear(e, f2, 8)
        self.assertTrue(r2.admission.accepted, r2.admission)
        snap = e.joint_state("joint-1", 8)
        self.assertEqual(snap["health_state"], "READY")                          # no other fault or degradation remains
        self.assertNotIn("fault_ids", snap)
        # with a degradation condition remaining the last fault gives DEGRADED, not READY
        cfg2 = S.config(feedback_required=False, feedback_timeout_policy="DEGRADE",
                        fault_clearance={"TRACKING_ERROR": "CLIENT_AUTHORIZED"},
                        degradation_policy={"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_VELOCITY"]})
        e2 = S.engine(cfg2)
        S.ready(e2, t=1)
        m2, _ = S.submit_start(e2, S.vel_cmd(0.1), 1, 1)
        e2.tick(300)                                                             # the optional feedback is lost
        e2.joint_fault("joint-1", "TRACKING_ERROR", 301)
        confirm(e2, m2, 302)
        fid = e2.faults("joint-1")[0]["fault_id"]
        self.assertEqual(e2.joint_state("joint-1", 302)["health_state"], "FAULTED")
        ok = e2.submit(S.env("CLEAR_FAULT", "joint-1", parameters={"fault_id": fid}), 303)
        self.assertTrue(ok.admission.accepted, ok.admission)
        snap = e2.joint_state("joint-1", 303)
        self.assertEqual((snap["health_state"], snap["degradation_reasons"]), ("DEGRADED", ["FEEDBACK_OPTIONAL_UNAVAILABLE"]))
        self.assertNotIn("fault_ids", snap)
        e2.feedback("joint-1", S.sample(0.0), 304)
        self.assertEqual(e2.joint_state("joint-1", 304)["health_state"], "READY")

    def test_CT_FLT_14(self):
        """A fault during a pending CANCEL: target FAILED with the first fault code, the CANCEL command FAILED with the same reason, joint FAULTED, control state per confirmation."""
        e = S.engine()
        xid = running_move(e, 1)
        cid = e.submit(S.cancel_cmd(xid), 100).command_id
        self.assertEqual(e.command(xid)["phase"], "TERMINATING")
        res = e.joint_fault("joint-1", "TRACKING_ERROR", 600)
        t = e.command(xid)["termination"]
        self.assertEqual([x["cause"] for x in t["causes"]], ["CANCEL_REQUESTED", "FAULT"])
        self.assertEqual((t["requested_ms"], t["bound_ms"]), (100, BOUND))        # the bound is not restarted
        self.assertEqual([q for q in res.requests if q["op"] == "request_termination"], [])   # no second request
        e.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 650)                    # a second fault appends, the first one decides
        self.assertEqual([x["cause"] for x in e.command(xid)["termination"]["causes"]],
                         ["CANCEL_REQUESTED", "FAULT", "FAULT"])
        confirm(e, xid, 700)
        self.assertEqual(states(e, xid, cid), [("FAILED", "TRACKING_ERROR")] * 2)   # not CANCELLED, same reason
        snap = e.joint_state("joint-1", 700)
        self.assertEqual((snap["health_state"], snap["control_state"]), ("FAULTED", "IDLE"))
        self.assertEqual(len(snap["fault_ids"]), 2)
        # unconfirmed: both fail TERMINATION_UNCONFIRMED and the control state follows the missing confirmation
        e2 = S.engine()
        x2 = running_move(e2, 1)
        c2 = e2.submit(S.cancel_cmd(x2), 100).command_id
        e2.joint_fault("joint-1", "TRACKING_ERROR", 600)
        e2.tick(100 + BOUND)
        self.assertEqual(states(e2, x2, c2), [("FAILED", "TERMINATION_UNCONFIRMED")] * 2)
        snap = e2.joint_state("joint-1", 100 + BOUND)
        self.assertEqual((snap["health_state"], snap["control_state"]), ("FAULTED", "UNKNOWN"))
        self.assertEqual([f["code"] for f in e2.faults("joint-1")], ["TRACKING_ERROR", "TERMINATION_UNCONFIRMED"])

    def test_CT_FLT_15(self):
        """A confirmed STOP stays COMPLETED(STOP_CONFIRMED) when a fault is appended to its attempt; the fault stays recorded."""
        # the STOP joined the attempt of a running command
        e = S.engine()
        xid = running_move(e, 1)
        sid = e.submit(S.stop_cmd(), 100).command_id
        e.joint_fault("joint-1", "TRACKING_ERROR", 200)
        self.assertEqual([x["cause"] for x in e.command(xid)["termination"]["causes"]], ["STOP_REQUESTED", "FAULT"])
        confirm(e, xid, 300)
        self.assertEqual(states(e, xid, sid), [("FAILED", "TRACKING_ERROR"), ("COMPLETED", "STOP_CONFIRMED")])
        fault = e.faults("joint-1")
        self.assertEqual([f["state"] for f in fault], ["ACTIVE"])
        self.assertEqual(e.joint_state("joint-1", 300)["health_state"], "FAULTED")
        self.assertEqual(e.joint_state("joint-1", 300)["control_state"], "IDLE")
        # the STOP owns its attempt (nothing was active) and the fault is appended to it
        e2 = S.engine()
        S.ready(e2, t=1)
        s2 = e2.submit(S.stop_cmd(), 2).command_id
        r = e2.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 3)
        self.assertEqual([q for q in r.requests if q["op"] == "request_termination"], [])   # one request already outstanding
        self.assertEqual([x["cause"] for x in e2.command(s2)["termination"]["causes"]], ["STOP_REQUESTED", "FAULT"])
        e2.termination_request_accepted(s2, "ref-" + s2, 4)
        confirm(e2, s2, 5)
        self.assertEqual(states(e2, s2), [("COMPLETED", "STOP_CONFIRMED")])
        self.assertEqual([f["code"] for f in e2.faults("joint-1")], ["JOINT_LIMIT_VIOLATION"])
        self.assertEqual(e2.joint_state("joint-1", 5)["health_state"], "FAULTED")
        # unconfirmed it fails TERMINATION_UNCONFIRMED, as for any command
        e3 = S.engine()
        S.ready(e3, t=1)
        s3 = e3.submit(S.stop_cmd(), 2).command_id
        e3.joint_fault("joint-1", "TRACKING_ERROR", 3)
        e3.tick(2 + BOUND)
        self.assertEqual(states(e3, s3), [("FAILED", "TERMINATION_UNCONFIRMED")])

    def test_CT_FLT_16(self):
        """Initial control state is UNKNOWN; a stale or ambiguous backend report does not establish a state; the backend becoming available alone does not leave UNKNOWN."""
        e = S.engine()
        snap = e.joint_state("joint-1", 0)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("UNKNOWN", "READY"))
        self.assertEqual(e.submit(S.vel_cmd(0.1), 1).admission.code, "TARGET_STATE_UNKNOWN")   # never assumed IDLE
        for label, args in (("stale", ("IDLE", 201)), ("partial", (None, 0)), ("ambiguous", ("MOVING", 0)),
                            ("no age", ("IDLE", None)), ("negative age", ("IDLE", -1))):
            with self.subTest(report=label):
                r = e.status_report("joint-1", args[0], args[1], 2)
                self.assertEqual([x["reason"] for x in r.ignored], ["partial_ambiguous_or_stale"])
                self.assertEqual(e.joint_state("joint-1", 2)["control_state"], "UNKNOWN")
        # the backend becoming available, even after a loss, establishes nothing
        e.backend_health("UNAVAILABLE", 3)
        e.backend_health("DEGRADED", 4)
        e.backend_health("AVAILABLE", 5)
        snap = e.joint_state("joint-1", 5)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("UNKNOWN", "READY"))
        self.assertEqual(e.faults("joint-1"), [])
        # a fresh authoritative report does
        e.status_report("joint-1", "IDLE", 200, 6)
        self.assertEqual(e.joint_state("joint-1", 6)["control_state"], "IDLE")

    def test_CT_FLT_17(self):
        """Recovery path: confirmed STOP gives IDLE, then CLEAR_FAULT; without stop confirmation the joint stays FAULTED and UNKNOWN and CLEAR_FAULT is not an override."""
        e = S.engine()
        xid = running_move(e, 1)
        e.terminate(xid, "CANCEL_REQUESTED", 2)
        e.tick(2 + BOUND)
        fid = e.faults("joint-1")[0]["fault_id"]
        t = 10 + BOUND
        e.backend_health("UNAVAILABLE", t)                                       # the backend returns
        e.backend_health("AVAILABLE", t + 1)
        snap = e.joint_state("joint-1", t + 1)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("UNKNOWN", "FAULTED"))   # returning alone recovers nothing
        sid = e.submit(S.stop_cmd(), t + 2).command_id                           # an authorized STOP
        confirm(e, sid, t + 3)                                                   # the backend confirms the stopped condition
        self.assertEqual(states(e, sid), [("COMPLETED", "STOP_CONFIRMED")])
        snap = e.joint_state("joint-1", t + 3)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("IDLE", "FAULTED"))
        fresh(e, t + 4)
        ok = clear(e, fid, t + 4)
        self.assertTrue(ok.admission.accepted, ok.admission)
        snap = e.joint_state("joint-1", t + 4)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("IDLE", "READY"))
        # without a confirmed stop the lockout holds
        e2 = S.engine()
        x2 = running_move(e2, 1)
        e2.terminate(x2, "CANCEL_REQUESTED", 2)
        e2.tick(2 + BOUND)
        s2 = e2.submit(S.stop_cmd(), 20 + BOUND).command_id
        e2.tick(20 + 2 * BOUND)                                                  # the STOP is never confirmed
        self.assertEqual(states(e2, s2), [("FAILED", "TERMINATION_UNCONFIRMED")])
        t2 = 30 + 2 * BOUND
        e2.backend_health("UNAVAILABLE", t2)
        e2.backend_health("AVAILABLE", t2 + 1)
        fresh(e2, t2 + 2)
        snap = e2.joint_state("joint-1", t2 + 2)
        self.assertEqual((snap["control_state"], snap["health_state"], len(snap["fault_ids"])), ("UNKNOWN", "FAULTED", 2))
        n = len(e2.commands())
        for f in e2.faults("joint-1"):                                           # no fault can be cleared: not an override
            r = clear(e2, f["fault_id"], t2 + 2)
            self.assertEqual((r.admission.accepted, r.admission.code), (False, "FAULT_NOT_CLEARABLE"))
        self.assertEqual(len(e2.commands()), n)
        for cmd in (S.vel_cmd(0.1), S.pos_cmd(0.2), S.hold_cmd()):
            self.assertFalse(e2.submit(cmd, t2 + 3).admission.accepted)          # ordinary motion stays unavailable
        self.assertEqual(e2.joint_state("joint-1", t2 + 3)["health_state"], "FAULTED")

    def test_CT_FLT_18(self):
        """Degradation permission does not make SET_POSITION or HOLD admissible without valid fresh feedback; SET_VELOCITY is accepted only with its completion evidence."""
        e = S.engine(S.config(degradation_policy=POLICY_ALL))
        S.ready(e, t=1)
        e.backend_health("DEGRADED", 2)
        self.assertEqual(e.joint_state("joint-1", 2)["health_state"], "DEGRADED")
        # the policy permits all three, and the feedback is fresh: accepted
        for cmd in (S.pos_cmd(0.2), S.vel_cmd(0.1), S.hold_cmd()):
            e1 = S.engine(S.config(degradation_policy=POLICY_ALL))
            S.ready(e1, t=1)
            e1.backend_health("DEGRADED", 2)
            self.assertTrue(e1.submit(cmd, 3).admission.accepted)
        # the same permission with stale feedback: nothing that needs feedback is admissible
        for cmd in (S.pos_cmd(0.2), S.hold_cmd(), S.vel_cmd(0.1)):
            r = e.submit(cmd, 1000)
            self.assertEqual((r.admission.accepted, r.admission.code), (False, "FEEDBACK_STALE"))
        # with feedback missing altogether
        e2 = S.engine(S.config(degradation_policy=POLICY_ALL))
        e2.status_report("joint-1", "IDLE", 0, 1)
        e2.backend_health("DEGRADED", 2)
        for cmd in (S.pos_cmd(0.2), S.hold_cmd(), S.vel_cmd(0.1)):
            self.assertEqual(e2.submit(cmd, 3).admission.code, "FEEDBACK_UNAVAILABLE")
        # a degradation reason with no policy permits no movement
        e3 = S.engine()
        S.ready(e3, t=1)
        e3.backend_health("DEGRADED", 2)
        for cmd in (S.pos_cmd(0.2), S.hold_cmd(), S.vel_cmd(0.1)):
            self.assertEqual(e3.submit(cmd, 3).admission.code, "TARGET_DEGRADED")
        # a SET_VELOCITY whose feedback is not required is accepted under the policy and is never completed without evidence
        cfg = S.config(feedback_required=False, feedback_timeout_policy="DEGRADE", degradation_policy=POLICY_ALL)
        e4 = S.engine(cfg)
        e4.status_report("joint-1", "IDLE", 0, 1)
        e4.backend_health("DEGRADED", 2)
        forever, _ = S.submit_start(e4, S.vel_cmd(0.1), 3, 3)
        e4.tick(10**8)
        self.assertNotEqual(e4.command(forever)["state"], "COMPLETED")           # only a stop, timeout or fault ends it
        # position and hold still need their feedback even when the feedback itself is optional
        e5 = S.engine(cfg)
        e5.status_report("joint-1", "IDLE", 0, 1)
        e5.backend_health("DEGRADED", 2)
        self.assertEqual(e5.submit(S.pos_cmd(0.2), 3).admission.code, "FEEDBACK_UNAVAILABLE")
        self.assertEqual(e5.submit(S.hold_cmd(), 3).admission.code, "FEEDBACK_UNAVAILABLE")
        self.assertTrue(e5.submit(S.vel_cmd(0.1), 3).admission.accepted)
        # queries and STOP stay available
        self.assertTrue(e3.submit(S.stop_cmd(), 4).admission.accepted)
        self.assertEqual(e3.joint_state("joint-1", 4)["health_state"], "DEGRADED")

    def test_CT_FLT_19(self):
        """A newly connected joint is UNKNOWN and READY with no fault record; no fault is created and CLEAR_FAULT is not needed."""
        e = S.engine()
        for jid in ("joint-1", "joint-c", "joint-p"):
            snap = e.joint_state(jid, 0)
            self.assertEqual((snap["control_state"], snap["health_state"]), ("UNKNOWN", "READY"))
            self.assertNotIn("fault_ids", snap)
            self.assertEqual(e.faults(jid), [])
        e.tick(1000)                                                             # time passing creates nothing
        e.backend_health("UNAVAILABLE", 1001)
        e.backend_health("AVAILABLE", 1002)                                      # connecting to the backend creates nothing
        e.feedback("joint-1", S.sample(0.0), 1003)
        for jid in ("joint-1", "joint-c", "joint-p"):
            self.assertEqual(e.faults(jid), [])
            self.assertEqual(e.joint_state(jid, 1003)["health_state"], "READY")
        # there is nothing to clear, and recovery needs no CLEAR_FAULT
        r = clear(e, "fault-1", 1004)
        self.assertEqual((r.admission.accepted, r.admission.code, r.command_id), (False, "FAULT_NOT_FOUND", None))
        e.status_report("joint-1", "IDLE", 0, 1005)
        snap = e.joint_state("joint-1", 1005)
        self.assertEqual((snap["control_state"], snap["health_state"], e.faults("joint-1")), ("IDLE", "READY", []))
        self.assertEqual(e.commands(), [])

    def test_CT_FLT_20(self):
        """Recovery of an UNKNOWN joint without a fault record by a fresh authoritative status report, and separately by a confirmed STOP; a stale, partial or ambiguous report leaves it UNKNOWN."""
        # by a fresh report, for each state a report may establish
        for state in ("IDLE", "HOLDING", "ACTIVE"):
            with self.subTest(report=state):
                e = S.engine()
                self.assertEqual([x["reason"] for x in e.status_report("joint-1", state, 201, 1).ignored],
                                 ["partial_ambiguous_or_stale"])
                self.assertEqual(e.joint_state("joint-1", 1)["control_state"], "UNKNOWN")
                r = e.status_report("joint-1", state, 200, 2)                    # exactly as old as allowed
                self.assertEqual(r.ignored, [])
                snap = e.joint_state("joint-1", 2)
                self.assertEqual((snap["control_state"], snap["health_state"], e.faults("joint-1")), (state, "READY", []))
        # a partial or ambiguous report is not enough
        e = S.engine()
        for args in ((None, 0), ("UNKNOWN", 0), ("BUSY", 0), ("IDLE", "fresh"), ("IDLE", float("nan"))):
            e.status_report("joint-1", args[0], args[1], 3)
        self.assertEqual(e.joint_state("joint-1", 3)["control_state"], "UNKNOWN")
        # separately, by a confirmed STOP: the receipt of the STOP is not enough
        sid = e.submit(S.stop_cmd(), 4).command_id
        self.assertEqual(e.joint_state("joint-1", 4)["control_state"], "UNKNOWN")
        e.termination_request_accepted(sid, "ref-" + sid, 5)
        self.assertEqual(e.joint_state("joint-1", 5)["control_state"], "UNKNOWN")
        confirm(e, sid, 6)
        snap = e.joint_state("joint-1", 6)
        self.assertEqual((snap["control_state"], snap["health_state"], e.faults("joint-1")), ("IDLE", "READY", []))
        self.assertEqual(states(e, sid), [("COMPLETED", "STOP_CONFIRMED")])
        # a report is not used once the state is known
        self.assertEqual([x["reason"] for x in e.status_report("joint-1", "HOLDING", 0, 7).ignored], ["state_already_established"])

    def test_CT_FLT_21(self):
        """A status report on a FAULTED and UNKNOWN joint can establish control state but never clears the fault; only CLEAR_FAULT does."""
        e = S.engine()
        xid = running_move(e, 1)
        e.terminate(xid, "CANCEL_REQUESTED", 2)
        e.tick(2 + BOUND)
        fid = e.faults("joint-1")[0]["fault_id"]
        t = 10 + BOUND
        self.assertEqual(e.joint_state("joint-1", t)["control_state"], "UNKNOWN")
        e.status_report("joint-1", "IDLE", 0, t)
        snap = e.joint_state("joint-1", t)
        self.assertEqual((snap["control_state"], snap["health_state"], snap["fault_ids"]), ("IDLE", "FAULTED", [fid]))
        self.assertEqual([f["state"] for f in e.faults("joint-1")], ["ACTIVE"])
        self.assertEqual(e.submit(S.vel_cmd(0.1), t + 1).admission.code, "TARGET_FAULTED")   # still locked out
        fresh(e, t + 2)
        self.assertEqual(clear(e, fid, t + 2).admission.code, "FAULT_NOT_CLEARABLE")          # the report did not resolve the cause
        # only the stop and then CLEAR_FAULT clear it
        stopped(e, t + 3)
        fresh(e, t + 4)
        ok = clear(e, fid, t + 4)
        self.assertTrue(ok.admission.accepted, ok.admission)
        self.assertEqual([f["state"] for f in e.faults("joint-1")], ["CLEARED"])
        self.assertEqual(e.joint_state("joint-1", t + 4)["health_state"], "READY")
        # a report on a joint that is FAULTED but not UNKNOWN changes nothing at all
        e2 = S.engine()
        S.ready(e2, t=1)
        e2.joint_fault("joint-1", "TRACKING_ERROR", 2)
        r = e2.status_report("joint-1", "HOLDING", 0, 3)
        self.assertEqual([x["reason"] for x in r.ignored], ["state_already_established"])
        self.assertEqual(e2.joint_state("joint-1", 3)["health_state"], "FAULTED")

    def test_CT_FLT_22(self):
        """CLEAR_FAULT race: accepted, then a new fault or termination begins before application; it ends FAILED with the new fault code and neither fault is cleared."""
        def prepared():
            e = S.engine()
            S.ready(e, t=1)
            e.joint_fault("joint-1", "TRACKING_ERROR", 2)
            fa = e.faults("joint-1")[0]["fault_id"]
            stopped(e, 3)
            fresh(e, 5)
            r = clear(e, fa, 5, defer_dispatch=True)                              # accepted, not yet applied
            self.assertTrue(r.admission.accepted, r.admission)
            self.assertEqual((e.command(r.command_id)["state"], e.command(r.command_id)["phase"]), ("ACCEPTED", "NONE"))
            self.assertEqual(e.faults("joint-1")[0]["state"], "ACTIVE")
            return e, fa, r.command_id

        # a new fault in the window
        e, fa, cid = prepared()
        e.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 6)
        fb = e.faults("joint-1")[1]
        self.assertEqual(states(e, cid), [("FAILED", "JOINT_LIMIT_VIOLATION")])
        self.assertEqual([f["state"] for f in e.faults("joint-1")], ["ACTIVE", "ACTIVE"])      # neither fault is cleared
        self.assertEqual(e.joint_state("joint-1", 6)["fault_ids"], [fa, fb["fault_id"]])
        self.assertEqual([x["reason"] for x in e.dispatch(cid, 7).ignored], ["terminal"])      # applying it later changes nothing
        self.assertEqual([f["state"] for f in e.faults("joint-1")], ["ACTIVE", "ACTIVE"])
        # a termination begins in the window: nothing is cleared while it is outstanding
        e, fa, cid = prepared()
        s2 = e.submit(S.stop_cmd(), 6).command_id
        r = e.dispatch(cid, 7)
        self.assertEqual([x["reason"] for x in r.ignored], ["precondition_not_met:FAULT_NOT_CLEARABLE"])
        self.assertEqual((e.command(cid)["state"], e.faults("joint-1")[0]["state"]), ("ACCEPTED", "ACTIVE"))
        e.tick(6 + BOUND)                                                       # the termination is never confirmed
        self.assertEqual(states(e, s2), [("FAILED", "TERMINATION_UNCONFIRMED")])
        self.assertEqual(states(e, cid), [("FAILED", "TERMINATION_UNCONFIRMED")])             # the new fault's code
        self.assertEqual([(f["code"], f["state"]) for f in e.faults("joint-1")],
                         [("TRACKING_ERROR", "ACTIVE"), ("TERMINATION_UNCONFIRMED", "ACTIVE")])
        self.assertEqual(e.joint_state("joint-1", 6 + BOUND)["health_state"], "FAULTED")
        # the same window with a termination that is confirmed: no new fault, so it is applied afterwards
        e, fa, cid = prepared()
        s3 = e.submit(S.stop_cmd(), 6).command_id
        confirm(e, s3, 7)
        fresh(e, 8)
        e.dispatch(cid, 8)
        self.assertEqual(states(e, cid), [("COMPLETED", "FAULT_CLEARED")])
        self.assertEqual([f["state"] for f in e.faults("joint-1")], ["CLEARED"])

    def test_CT_TMO_08(self):
        """A fault during TERMINATING: the bound is not restarted, all causes are recorded, confirmed termination gives FAILED with the fault code, unconfirmed gives FAILED(TERMINATION_UNCONFIRMED)."""
        e = S.engine()
        xid = running_move(e, 1)
        e.terminate(xid, "CANCEL_REQUESTED", 100)
        before = e.command(xid)["termination"]
        res = e.joint_fault("joint-1", "TRACKING_ERROR", 600)
        e.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 700)
        t = e.command(xid)["termination"]
        self.assertEqual([x["cause"] for x in t["causes"]], ["CANCEL_REQUESTED", "FAULT", "FAULT"])
        self.assertEqual([x.get("code") for x in t["causes"]], [None, "TRACKING_ERROR", "JOINT_LIMIT_VIOLATION"])   # all recorded in order
        self.assertEqual((t["requested_ms"], t["bound_ms"], t["outcome"]), (before["requested_ms"], before["bound_ms"], "PENDING"))
        self.assertEqual([q["op"] for q in res.requests if q["op"] == "request_termination"], [])   # no second request
        self.assertEqual((e.command(xid)["state"], e.command(xid)["phase"]), ("RUNNING", "TERMINATING"))
        confirm(e, xid, 800)
        c = e.command(xid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("FAILED", "TRACKING_ERROR", "NONE"))   # the first fault's code
        self.assertEqual(c["termination"]["outcome"], "CONFIRMED")
        self.assertEqual([x["cause"] for x in c["termination"]["causes"]], ["CANCEL_REQUESTED", "FAULT", "FAULT"])   # and stay recorded
        # unconfirmed: the bound that began with the first request expires, not one that a fault would start
        e2 = S.engine()
        x2 = running_move(e2, 1)
        e2.terminate(x2, "CANCEL_REQUESTED", 100)
        e2.joint_fault("joint-1", "TRACKING_ERROR", 600)
        e2.tick(100 + BOUND - 1)
        self.assertEqual(e2.command(x2)["state"], "RUNNING")
        e2.tick(100 + BOUND)
        c2 = e2.command(x2)
        self.assertEqual((c2["state"], c2["reason_code"]), ("FAILED", "TERMINATION_UNCONFIRMED"))
        self.assertEqual(c2["termination"]["outcome"], "UNCONFIRMED")
        self.assertEqual([x["cause"] for x in c2["termination"]["causes"]], ["CANCEL_REQUESTED", "FAULT"])
        self.assertEqual([f["code"] for f in e2.faults("joint-1")], ["TRACKING_ERROR", "TERMINATION_UNCONFIRMED"])
        self.assertEqual(e2.joint_state("joint-1", 100 + BOUND)["control_state"], "UNKNOWN")
        # a timeout that started the termination, then a fault: the fault still decides
        e3 = S.engine()
        S.ready(e3, t=1)
        x3, _ = S.submit_start(e3, S.vel_cmd(0.1, execution_timeout_ms=400), 1, 1)
        for t_ in (100, 200, 300, 400):
            fresh(e3, t_)
        e3.tick(401)
        self.assertEqual([x["cause"] for x in e3.command(x3)["termination"]["causes"]], ["EXECUTION_TIMEOUT"])
        e3.joint_fault("joint-1", "JOINT_LIMIT_VIOLATION", 402)
        confirm(e3, x3, 403)
        self.assertEqual(states(e3, x3), [("FAILED", "JOINT_LIMIT_VIOLATION")])


if __name__ == "__main__":
    unittest.main()
