"""Behaviour tests of timers and termination beyond the conformance mapping (KOS-MOTION-003, PR-03).

Deterministic and offline. Software evidence only, never physical or safety validation."""
import unittest

import lifecycle_support as S
from kritva_motion.lifecycle import model

BOUND = 1000


def running(e, t=1, **over):
    S.ready(e, t=t)
    cid, _ = S.submit_start(e, S.vel_cmd(0.1, **over), t, t)
    return cid


def ops(res, op):
    return [r for r in res.requests if r["op"] == op]


class TestOrderAtOneReading(unittest.TestCase):
    def test_start_applied_before_a_tick_at_the_deadline_starts_the_command(self):
        e = S.engine()
        S.ready(e, t=0)
        cid = e.submit(S.pos_cmd(0.5, deadline_ms=300), 1).command_id
        e.execution_started(cid, "ref-" + cid, 301)      # input first, at the very reading of the deadline
        e.tick(301)
        self.assertEqual(e.command(cid)["state"], "RUNNING")

    def test_tick_first_at_the_deadline_fails_the_command(self):
        e = S.engine()
        S.ready(e, t=0)
        cid = e.submit(S.pos_cmd(0.5, deadline_ms=300), 1).command_id
        e.tick(301)
        self.assertEqual(e.command(cid)["phase"], "TERMINATING")
        e.execution_started(cid, "ref-" + cid, 301)
        self.assertEqual(e.command(cid)["state"], "ACCEPTED")

    def test_confirmation_at_the_bound_reading_wins_when_applied_before_the_tick(self):
        e = S.engine()
        cid = running(e, execution_timeout_ms=400)
        e.tick(401)
        e.termination_confirmed(cid, "ref-" + cid, 401 + BOUND)
        e.tick(401 + BOUND)
        self.assertEqual(e.command(cid)["reason_code"], "EXECUTION_TIMEOUT")
        self.assertEqual(e.joint_state("joint-1", 401 + BOUND)["health_state"], "READY")

    def test_timer_passes_visit_commands_in_acceptance_order(self):
        e = S.engine()
        S.ready(e, t=0)
        e.status_report("joint-p", "IDLE", 0, 0)
        e.feedback("joint-p", S.sample(0.1), 0)
        a = e.submit(S.pos_cmd(0.5, deadline_ms=300), 1).command_id
        b = e.submit(S.env("SET_POSITION", "joint-p", parameters={"target_position": 0.2, "unit": "m"},
                           deadline_ms=300), 1).command_id
        res = e.tick(301)
        self.assertEqual([q["command_id"] for q in ops(res, "request_termination")], [a, b])


class TestTerminationRecord(unittest.TestCase):
    def test_second_cause_joins_without_a_second_request_or_a_new_bound(self):
        e = S.engine()
        cid = running(e)
        first = e.terminate(cid, "CANCEL_REQUESTED", 100)
        second = e.terminate(cid, "STOP_REQUESTED", 600)
        self.assertEqual(len(ops(first, "request_termination")), 1)
        self.assertEqual(ops(second, "request_termination"), [])
        t = e.command(cid)["termination"]
        self.assertEqual((t["requested_ms"], t["bound_ms"]), (100, BOUND))
        e.tick(100 + BOUND - 1)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e.tick(100 + BOUND)                                # the first request's bound, not the second's
        self.assertEqual(e.command(cid)["reason_code"], "TERMINATION_UNCONFIRMED")

    def test_timer_cause_joins_an_outstanding_attempt_once(self):
        e = S.engine()
        cid = running(e, execution_timeout_ms=400)
        e.terminate(cid, "CANCEL_REQUESTED", 100)
        for t in (401, 500, 700):
            e.tick(t)
        causes = [x["cause"] for x in e.command(cid)["termination"]["causes"]]
        self.assertEqual(causes, ["CANCEL_REQUESTED", "EXECUTION_TIMEOUT"])

    def test_request_accepted_is_recorded_once_and_never_confirms(self):
        e = S.engine()
        cid = running(e)
        e.terminate(cid, "CANCEL_REQUESTED", 100)
        e.termination_request_accepted(cid, "ref-" + cid, 120)
        dup = e.termination_request_accepted(cid, "ref-" + cid, 130)
        self.assertEqual([x["reason"] for x in dup.ignored], ["duplicate"])
        c = e.command(cid)
        self.assertEqual((c["state"], c["phase"], c["termination"]["outcome"], c["termination"]["backend_accepted_ms"]),
                         ("RUNNING", "TERMINATING", "PENDING", 120))

    def test_termination_inputs_that_are_ignored_leave_everything_unchanged(self):
        e = S.engine()
        cid = running(e)
        before = e.command(cid)
        for fn, reason in ((lambda: e.termination_confirmed(cid, "ref-" + cid, 5), "no_termination_outstanding"),
                           (lambda: e.termination_request_accepted(cid, "ref-" + cid, 6), "no_termination_outstanding"),
                           (lambda: e.termination_confirmed("nope", "ref-x", 7), "unknown_command"),
                           (lambda: e.termination_confirmed(cid, "wrong", 8), "reference_mismatch")):
            self.assertEqual([x["reason"] for x in fn().ignored], [reason])
        self.assertEqual(e.command(cid), before)
        e.terminate(cid, "CANCEL_REQUESTED", 9)
        self.assertEqual([x["reason"] for x in e.termination_confirmed(cid, "wrong", 10).ignored], ["reference_mismatch"])
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e.termination_confirmed(cid, "ref-" + cid, 11)
        self.assertEqual([x["reason"] for x in e.termination_confirmed(cid, "ref-" + cid, 12).ignored], ["terminal"])

    def test_terminate_input_rules(self):
        e = S.engine()
        cid = running(e)
        self.assertEqual([x["reason"] for x in e.terminate("nope", "CANCEL_REQUESTED", 2).ignored], ["unknown_command"])
        for bad in ("EXECUTION_TIMEOUT", "DEADLINE_EXPIRED", "FAULT", "", None):
            with self.assertRaises(ValueError):
                e.terminate(cid, bad, 3)
        self.assertEqual(e.command(cid)["phase"], "NONE")
        e.terminate(cid, "CANCEL_REQUESTED", 4)
        e.termination_confirmed(cid, "ref-" + cid, 5)
        self.assertEqual([x["reason"] for x in e.terminate(cid, "STOP_REQUESTED", 6).ignored], ["terminal"])
        self.assertEqual(e.command(cid)["reason_code"], "CANCEL_REQUESTED")


class TestEffectsOnTheJoint(unittest.TestCase):
    def test_slot_stays_busy_while_terminating_and_frees_on_confirmation(self):
        e = S.engine()
        cid = running(e)
        e.terminate(cid, "CANCEL_REQUESTED", 10)
        busy = e.submit(S.pos_cmd(0.2), 11)
        self.assertEqual(busy.admission.code, "TARGET_BUSY")
        e.termination_confirmed(cid, "ref-" + cid, 12)
        e.feedback("joint-1", S.sample(0.0), 13)
        self.assertTrue(e.submit(S.pos_cmd(0.2), 14).admission.accepted)

    def test_nothing_completes_a_command_with_an_outstanding_termination(self):
        cfg = S.config(settling_duration_ms=0, position_tolerance=0.01)
        e = S.engine(cfg)
        S.ready(e, t=1)
        cid, _ = S.submit_start(e, S.pos_cmd(0.5), 1, 1)
        e.terminate(cid, "CANCEL_REQUESTED", 2)
        e.feedback("joint-1", S.sample(0.5), 3)            # on target, but the attempt decides
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e2 = S.engine()
        vid = running(e2, duration=100)
        e2.terminate(vid, "STOP_REQUESTED", 10)
        e2.tick(500)
        self.assertEqual(e2.command(vid)["state"], "RUNNING")

    def test_unconfirmed_termination_keeps_the_fault_until_something_clears_it(self):
        e = S.engine()
        cid = running(e, execution_timeout_ms=400)
        e.tick(401)
        e.tick(401 + BOUND)
        for t in (5000, 10**6):
            e.tick(t)
            s = e.joint_state("joint-1", t)
            self.assertEqual((s["health_state"], s["control_state"]), ("FAULTED", "UNKNOWN"))
        e.status_report("joint-1", "IDLE", 0, 10**6 + 1)    # a report alone never clears a fault
        s = e.joint_state("joint-1", 10**6 + 1)
        self.assertEqual(s["health_state"], "FAULTED")
        self.assertEqual(len(e.faults("joint-1")), 1)

    def test_confirmed_termination_of_an_unstarted_command_leaves_the_joint_idle(self):
        e = S.engine()
        S.ready(e, t=0)
        cid = e.submit(S.pos_cmd(0.5), 1).command_id
        e.terminate(cid, "CANCEL_REQUESTED", 2)
        e.termination_confirmed(cid, "ref-" + cid, 3)
        s = e.joint_state("joint-1", 3)
        self.assertEqual((s["control_state"], s["health_state"]), ("IDLE", "READY"))

    def test_other_joints_are_unaffected(self):
        e = S.engine()
        S.ready(e, t=1)
        e.status_report("joint-p", "IDLE", 0, 1)
        e.feedback("joint-p", S.sample(0.1), 1)
        a = e.submit(S.pos_cmd(0.5), 1).command_id
        b = e.submit(S.env("SET_POSITION", "joint-p", parameters={"target_position": 0.2, "unit": "m"}), 1).command_id
        e.terminate(a, "CANCEL_REQUESTED", 2)
        e.tick(2 + BOUND)
        self.assertEqual(e.command(a)["reason_code"], "TERMINATION_UNCONFIRMED")
        self.assertEqual((e.command(b)["state"], e.command(b)["phase"]), ("ACCEPTED", "DISPATCH_PENDING"))
        self.assertEqual(e.joint_state("joint-p", 2 + BOUND)["health_state"], "READY")


class TestDispatchInput(unittest.TestCase):
    def test_dispatch_after_deferral_issues_one_request_and_sets_the_phase(self):
        e = S.engine()
        S.ready(e, t=0)
        cid = e.submit(S.pos_cmd(0.5), 1, defer_dispatch=True).command_id
        self.assertEqual(e.execution_started(cid, "ref-" + cid, 2).ignored[0]["reason"], "not_dispatched")
        res = e.dispatch(cid, 3)
        self.assertEqual([r["op"] for r in res.requests], ["dispatch"])
        self.assertEqual(e.command(cid)["phase"], "DISPATCH_PENDING")
        self.assertEqual([x["reason"] for x in e.dispatch(cid, 4).ignored], ["already_dispatched"])
        e.execution_started(cid, "ref-" + cid, 5)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        self.assertEqual([x["reason"] for x in e.dispatch("nope", 6).ignored], ["unknown_command"])

    def test_default_submit_is_unchanged(self):
        e = S.engine()
        S.ready(e, t=0)
        r = e.submit(S.pos_cmd(0.5), 1)
        self.assertEqual((e.command(r.command_id)["phase"], [q["op"] for q in r.requests]), ("DISPATCH_PENDING", ["dispatch"]))


class TestModelOutcome(unittest.TestCase):
    def test_bad_cause_lists(self):
        with self.assertRaises(model.IllegalTransition):
            model.outcome_of_causes([])
        with self.assertRaises(model.IllegalTransition):
            model.outcome_of_causes(["SOMETHING_ELSE"])
        with self.assertRaises(model.IllegalTransition):                  # a FAULT cause needs its fault's code (PR-05)
            model.outcome_of_causes(["CANCEL_REQUESTED", "FAULT"])
        with self.assertRaises(model.IllegalTransition):
            model.outcome_of_causes(["FAULT"], ["NOT_A_REASON"])
        self.assertEqual(model.outcome_of_causes(["CANCEL_REQUESTED", "FAULT"], ["FEEDBACK_LOST"]), ("FAILED", "FEEDBACK_LOST"))


class TestDeterminism(unittest.TestCase):
    def _run(self):
        e = S.engine()
        out = []
        S.ready(e, t=0)
        r = e.submit(S.pos_cmd(0.5, execution_timeout_ms=300), 1, utc="u1")
        cid = r.command_id
        out.append(r)
        out.append(e.execution_started(cid, "ref-" + cid, 2, "u2"))
        out.append(e.terminate(cid, "CANCEL_REQUESTED", 50, "u50"))
        out.append(e.tick(302, "u302"))
        out.append(e.tick(50 + BOUND, "u1050"))
        return [(x.admission, x.command_id, x.requests, x.events, x.ignored) for x in out], e.commands(), e.faults("joint-1")

    def test_same_inputs_give_identical_outputs(self):
        self.assertEqual(self._run(), self._run())


if __name__ == "__main__":
    unittest.main()
