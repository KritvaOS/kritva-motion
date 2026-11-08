"""Behaviour tests of CANCEL, HOLD and STOP beyond the conformance mapping (KOS-MOTION-003, PR-04).

Deterministic and offline. Software evidence only, never physical or safety validation."""
import unittest

import lifecycle_support as S
from kritva_motion.lifecycle import model

BOUND = 1000


def move(e, t=1, **over):
    S.ready(e, t=t)
    cid, _ = S.submit_start(e, S.vel_cmd(0.1, **over), t, t)
    return cid


def st(e, *ids):
    return [(e.command(i)["state"], e.command(i)["reason_code"]) for i in ids]


def invariants(test, e):
    for c in e.commands():
        test.assertIn(c["phase"], model.PHASES)
        if c["state"] in model.TERMINAL_STATES:
            test.assertEqual(c["phase"], "NONE")
        if c["phase"] == "TERMINATING":
            test.assertEqual(c["termination"]["outcome"], "PENDING")
        if c["phase"] == "DISPATCH_PENDING":
            test.assertEqual(c["state"], "ACCEPTED")


class TestCancelCommand(unittest.TestCase):
    def test_cancel_before_dispatch_completes_in_one_call_through_running(self):
        e = S.engine()
        S.ready(e, t=1)
        xid = e.submit(S.pos_cmd(0.5), 1, defer_dispatch=True).command_id
        r = e.submit(S.cancel_cmd(xid), 2)
        self.assertTrue(r.admission.accepted, r.admission)
        cid = r.command_id
        self.assertEqual(st(e, xid, cid), [("CANCELLED", "CANCEL_REQUESTED"), ("COMPLETED", "CANCEL_EFFECTIVE")])
        self.assertEqual([t["to"] for t in e.command(cid)["transitions"]], ["ACCEPTED", "RUNNING", "COMPLETED"])
        self.assertEqual(r.requests, [])
        self.assertEqual(e.command(cid)["references"], xid)
        invariants(self, e)

    def test_cancel_of_a_dispatched_command_waits_for_the_backend(self):
        e = S.engine()
        xid = move(e)
        r = e.submit(S.cancel_cmd(xid), 2)
        cid = r.command_id
        self.assertEqual([(q["command_id"], q["cause"]) for q in r.requests if q["op"] == "request_termination"],
                         [(xid, "CANCEL_REQUESTED")])
        self.assertEqual(e.command(cid)["state"], "ACCEPTED")            # acceptance is not evidence of success
        e.termination_request_accepted(xid, "ref-" + xid, 3)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e.termination_confirmed(xid, "ref-" + xid, 4)
        self.assertEqual(st(e, xid, cid), [("CANCELLED", "CANCEL_REQUESTED"), ("COMPLETED", "CANCEL_EFFECTIVE")])
        invariants(self, e)

    def test_cancel_follows_the_target_when_it_fails(self):
        # execution timeout recorded after the cancellation: the target FAILED, so the CANCEL FAILED with the same reason
        e = S.engine()
        S.ready(e, t=1)
        xid, _ = S.submit_start(e, S.vel_cmd(0.1, execution_timeout_ms=400), 1, 1)
        cid = e.submit(S.cancel_cmd(xid), 100).command_id
        e.tick(401)
        e.termination_confirmed(xid, "ref-" + xid, 402)
        self.assertEqual(st(e, xid, cid), [("FAILED", "EXECUTION_TIMEOUT"), ("FAILED", "EXECUTION_TIMEOUT")])
        # unconfirmed: the CANCEL fails TERMINATION_UNCONFIRMED and is never COMPLETED
        e2 = S.engine()
        x2 = move(e2)
        c2 = e2.submit(S.cancel_cmd(x2), 2).command_id
        e2.tick(2 + BOUND)
        self.assertEqual(st(e2, x2, c2), [("FAILED", "TERMINATION_UNCONFIRMED")] * 2)
        self.assertEqual(e2.joint_state("joint-1", 2 + BOUND)["health_state"], "FAULTED")

    def test_cancel_of_a_pending_hold(self):
        e = S.engine()
        S.ready(e, t=1)
        h = e.submit(S.hold_cmd(), 1).command_id
        e.execution_started(h, "ref-" + h, 2)
        c = e.submit(S.cancel_cmd(h), 3).command_id
        e.termination_confirmed(h, "ref-" + h, 4)
        self.assertEqual(st(e, h, c), [("CANCELLED", "CANCEL_REQUESTED"), ("COMPLETED", "CANCEL_EFFECTIVE")])
        self.assertEqual(e.joint_state("joint-1", 4)["control_state"], "IDLE")

    def test_admission_refusals_create_no_command(self):
        e = S.engine()
        xid = move(e)
        c1 = e.submit(S.cancel_cmd(xid), 2)
        n = len(e.commands())
        self.assertEqual(e.submit(S.cancel_cmd(c1.command_id), 3).admission.code, "COMMAND_NOT_CANCELLABLE")
        sid = e.submit(S.stop_cmd(), 4).command_id
        self.assertEqual(e.submit(S.cancel_cmd(sid), 5).admission.code, "COMMAND_NOT_CANCELLABLE")
        self.assertEqual(e.submit(S.cancel_cmd("nope"), 6).admission.code, "COMMAND_NOT_FOUND")
        self.assertEqual(len(e.commands()), n + 1)       # only the STOP was added
        e.termination_confirmed(xid, "ref-" + xid, 7)
        self.assertEqual(e.submit(S.cancel_cmd(xid), 8).admission.code, "COMMAND_ALREADY_TERMINAL")

    def test_terminate_refuses_control_commands(self):
        e = S.engine()
        xid = move(e)
        c = e.submit(S.cancel_cmd(xid), 2).command_id
        self.assertEqual([x["reason"] for x in e.terminate(c, "CANCEL_REQUESTED", 3).ignored], ["not_cancellable"])
        self.assertEqual(e.command(c)["termination"], None)

    def test_control_commands_never_hold_the_slot_or_have_timers(self):
        e = S.engine()
        S.ready(e, t=1)
        s1 = e.submit(S.stop_cmd(), 1).command_id
        self.assertEqual(e.command(s1)["deadline_ms"], None)
        self.assertEqual(e.command(s1)["execution_timeout_ms"], None)
        # a STOP does not make the joint busy for itself; a second STOP is never TARGET_BUSY
        s2 = e.submit(S.stop_cmd(), 2)
        self.assertTrue(s2.admission.accepted)
        self.assertEqual(e.command(s2.command_id)["references"], s1)
        e.tick(10_000_000)    # no timer other than the termination bound applies to control commands
        self.assertEqual(st(e, s1, s2.command_id), [("FAILED", "TERMINATION_UNCONFIRMED")] * 2)


class TestHoldCommand(unittest.TestCase):
    def test_hold_does_not_make_the_joint_active(self):
        e = S.engine()
        S.ready(e, t=1)
        h = e.submit(S.hold_cmd(), 1).command_id
        e.execution_started(h, "ref-" + h, 2)
        s = e.joint_state("joint-1", 2)
        self.assertEqual((s["control_state"], s["active_command_id"]), ("IDLE", h))
        e.hold_confirmed(h, "ref-" + h, 3)
        s = e.joint_state("joint-1", 3)
        self.assertEqual(s["control_state"], "HOLDING")
        self.assertNotIn("active_command_id", s)

    def test_hold_inputs_that_are_ignored(self):
        e = S.engine()
        S.ready(e, t=1)
        x = e.submit(S.pos_cmd(0.5), 1).command_id
        h = e.submit(S.hold_cmd(), 1)           # TARGET_BUSY: no command created
        self.assertEqual(h.admission.code, "TARGET_BUSY")
        self.assertEqual([r["reason"] for r in e.hold_confirmed("nope", "r", 2).ignored], ["unknown_hold"])
        self.assertEqual([r["reason"] for r in e.hold_confirmed(x, "ref-" + x, 2).ignored], ["not_a_hold"])
        e2 = S.engine()
        S.ready(e2, t=1)
        h2 = e2.submit(S.hold_cmd(), 1).command_id
        e2.execution_started(h2, "ref-" + h2, 2)
        self.assertEqual([r["reason"] for r in e2.hold_confirmed(h2, "wrong", 3).ignored], ["reference_mismatch"])
        e2.hold_confirmed(h2, "ref-" + h2, 4)
        self.assertEqual([r["reason"] for r in e2.hold_confirmed(h2, "ref-" + h2, 5).ignored], ["terminal"])

    def test_hold_obeys_deadline_and_timeout_like_a_movement(self):
        e = S.engine()
        S.ready(e, t=1)
        h = e.submit(S.hold_cmd(deadline_ms=300), 1).command_id
        e.tick(301)
        self.assertEqual(e.command(h)["phase"], "TERMINATING")
        e.termination_confirmed(h, "ref-" + h, 302)
        self.assertEqual(st(e, h), [("FAILED", "DEADLINE_EXPIRED")])


class TestStopCases(unittest.TestCase):
    def test_two_stops_share_one_attempt_and_one_request(self):
        e = S.engine()
        S.ready(e, t=1)
        a = e.submit(S.stop_cmd(), 2)
        b = e.submit(S.stop_cmd(), 3)
        self.assertEqual(len([q for q in a.requests if q["op"] == "request_termination"]), 1)
        self.assertEqual([q for q in b.requests if q["op"] == "request_termination"], [])
        e.termination_confirmed(a.command_id, "ref-" + a.command_id, 4)
        self.assertEqual(st(e, a.command_id, b.command_id), [("COMPLETED", "STOP_CONFIRMED")] * 2)
        self.assertEqual(e.joint_state("joint-1", 4)["control_state"], "IDLE")

    def test_stop_on_another_joint_is_independent(self):
        e = S.engine()
        x = move(e)
        e.status_report("joint-p", "IDLE", 0, 1)
        e.feedback("joint-p", S.sample(0.1), 1)
        s = e.submit(S.stop_cmd("joint-p"), 2).command_id
        self.assertEqual(e.command(s)["references"], s)
        self.assertEqual(e.command(x)["phase"], "NONE")
        self.assertEqual(e.joint_state("joint-1", 2)["control_state"], "ACTIVE")

    def test_confirmed_stop_after_hold_pending_cancels_the_hold(self):
        e = S.engine()
        S.ready(e, t=1)
        h = e.submit(S.hold_cmd(), 1).command_id
        e.execution_started(h, "ref-" + h, 2)
        s = e.submit(S.stop_cmd(), 3).command_id
        e.termination_confirmed(h, "ref-" + h, 4)
        self.assertEqual(st(e, h, s), [("CANCELLED", "STOPPED"), ("COMPLETED", "STOP_CONFIRMED")])

    def test_invariants_hold_across_a_mixed_run(self):
        e = S.engine()
        S.ready(e, t=1)
        x = e.submit(S.pos_cmd(0.5), 1).command_id; invariants(self, e)
        c = e.submit(S.cancel_cmd(x), 2).command_id; invariants(self, e)
        s = e.submit(S.stop_cmd(), 3).command_id; invariants(self, e)
        e.termination_request_accepted(x, "ref-" + x, 4); invariants(self, e)
        e.execution_started(x, "ref-" + x, 5); invariants(self, e)
        e.termination_confirmed(x, "ref-" + x, 6); invariants(self, e)
        self.assertEqual(st(e, x, c, s), [("CANCELLED", "STOPPED"), ("COMPLETED", "CANCEL_EFFECTIVE"),
                                          ("COMPLETED", "STOP_CONFIRMED")])


class TestBackendHealth(unittest.TestCase):
    def test_input_rules(self):
        e = S.engine()
        with self.assertRaises(ValueError):
            e.backend_health("WORKING", 1)
        self.assertEqual([r["reason"] for r in e.backend_health("AVAILABLE", 2).ignored], ["unchanged"])
        e.backend_health("DEGRADED", 3)            # degraded alone changes no control state
        S.ready(e, t=4)
        self.assertEqual(e.joint_state("joint-1", 4)["control_state"], "IDLE")

    def test_terminating_joint_becomes_unknown_when_backend_is_lost(self):
        e = S.engine()
        x = move(e)
        e.terminate(x, "CANCEL_REQUESTED", 2)
        r = e.backend_health("UNAVAILABLE", 3)
        self.assertEqual(e.joint_state("joint-1", 3)["control_state"], "UNKNOWN")
        self.assertEqual(r.events[0]["event_type"], "JOINT_STATE_CHANGED")
        self.assertEqual(e.command(x)["state"], "RUNNING")     # failing in-flight commands is PR-05


class TestDeterminism(unittest.TestCase):
    def _run(self):
        e = S.engine()
        out = []
        S.ready(e, t=1)
        r = e.submit(S.pos_cmd(0.5), 1, utc="u1"); out.append(r); x = r.command_id
        out.append(e.execution_started(x, "ref-" + x, 2, "u2"))
        out.append(e.submit(S.cancel_cmd(x), 3, "u3"))
        s = e.submit(S.stop_cmd(), 4, "u4"); out.append(s)
        out.append(e.termination_request_accepted(x, "ref-" + x, 5, "u5"))
        out.append(e.termination_confirmed(x, "ref-" + x, 6, "u6"))
        return [(r.admission, r.command_id, r.requests, r.events, r.ignored) for r in out], e.commands()

    def test_same_inputs_give_identical_outputs(self):
        self.assertEqual(self._run(), self._run())


if __name__ == "__main__":
    unittest.main()
