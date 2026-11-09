"""Conformance tests of deadline, execution timeout, cancellation and termination (AC-306).

Each method is the single executable test named by one IN_SCOPE entry of
tests/manifest/conformance_manifest.json for the IDs that KOS-MOTION-003 PR-03 covers. The method
name is the ID with hyphens replaced by underscores. Deterministic and offline. Software evidence
only: a confirmed termination here is a supplied input, never proof that anything stopped
physically (contract 17.5).

Configuration used throughout (tests/validator/test_admission.py): termination_confirm_timeout_ms
1000, default deadline 10000, default execution timeout 5000. Commands set their own values where a
test needs short ones.
"""
import unittest

import lifecycle_support as S
from kritva_motion.lifecycle import model

BOUND = 1000


def invariants(test, e):
    """Contract 7.6 and CT-SCH-08 on every command record the engine holds."""
    for c in e.commands():
        test.assertIn(c["phase"], model.PHASES)
        test.assertNotIn(c["phase"], model.STATES)
        if c["state"] in model.TERMINAL_STATES:
            test.assertEqual(c["phase"], "NONE", c)
        if c["phase"] == "DISPATCH_PENDING":
            test.assertEqual(c["state"], "ACCEPTED")
        if c["phase"] == "TERMINATING":
            test.assertIsNotNone(c["termination"])
            test.assertEqual(c["termination"]["outcome"], "PENDING")


def requests(res, op):
    return [r for r in res.requests if r["op"] == op]


def running(e, t=1, **over):
    """A SET_VELOCITY command, accepted at t and started at t (the joint is ready at t)."""
    S.ready(e, t=t)
    cid, _ = S.submit_start(e, S.vel_cmd(0.1, **over), t, t)
    return cid


class TestTerminationConformance(unittest.TestCase):
    def test_CT_LC_06(self):
        """Phases appear only on non-terminal commands and never as states; a terminal command has phase NONE."""
        # one pass through every route a command can take in this pull request, checking after every input
        e = S.engine()
        S.ready(e, t=0)
        r = e.submit(S.pos_cmd(0.5, execution_timeout_ms=300), 1)
        invariants(self, e)
        a = r.command_id
        self.assertEqual(e.command(a)["phase"], "DISPATCH_PENDING")
        e.execution_started(a, "ref-" + a, 2); invariants(self, e)
        self.assertEqual(e.command(a)["phase"], "NONE")
        e.tick(302); invariants(self, e)                      # timeout detected: TERMINATING
        self.assertEqual(e.command(a)["phase"], "TERMINATING")
        e.termination_request_accepted(a, "ref-" + a, 303); invariants(self, e)
        e.termination_confirmed(a, "ref-" + a, 304); invariants(self, e)
        self.assertEqual((e.command(a)["state"], e.command(a)["phase"]), ("FAILED", "NONE"))
        # cancelled before dispatch, cancelled while pending, unconfirmed
        S.ready(e, t=305)
        b = e.submit(S.vel_cmd(0.1), 305, defer_dispatch=True).command_id
        self.assertEqual(e.command(b)["phase"], "NONE")
        e.terminate(b, "CANCEL_REQUESTED", 306); invariants(self, e)
        S.ready(e, t=307)
        c = e.submit(S.vel_cmd(0.1), 307).command_id
        e.terminate(c, "STOP_REQUESTED", 308); invariants(self, e)
        e.tick(308 + BOUND); invariants(self, e)
        self.assertEqual(e.command(c)["reason_code"], "TERMINATION_UNCONFIRMED")
        # a state name is never a phase and a phase never a state
        self.assertEqual(set(model.PHASES) & set(model.STATES), set())
        for st, phases in model.PHASES_OF_STATE.items():
            if st in model.TERMINAL_STATES:
                self.assertEqual(phases, ("NONE",))

    def test_CT_LC_07(self):
        """Cancel or STOP of a DISPATCH_PENDING command enters TERMINATING and needs backend confirmation; a late start does not revive it."""
        for cause, reason in (("CANCEL_REQUESTED", "CANCEL_REQUESTED"), ("STOP_REQUESTED", "STOPPED")):
            with self.subTest(cause=cause):
                e = S.engine()
                S.ready(e, t=0)
                cid = e.submit(S.pos_cmd(0.5), 1).command_id
                self.assertEqual(e.command(cid)["phase"], "DISPATCH_PENDING")
                res = e.terminate(cid, cause, 2)
                c = e.command(cid)
                self.assertEqual((c["state"], c["phase"]), ("ACCEPTED", "TERMINATING"))   # not CANCELLED on receipt
                self.assertEqual([(q["op"], q["cause"], q["backend_reference"]) for q in res.requests],
                                 [("request_termination", cause, "ref-" + cid)])
                # a late start confirmation is ignored and recorded; the phase does not change
                late = e.execution_started(cid, "ref-" + cid, 3)
                self.assertEqual([x["reason"] for x in late.ignored], ["terminating"])
                self.assertEqual((e.command(cid)["state"], e.command(cid)["phase"]), ("ACCEPTED", "TERMINATING"))
                self.assertEqual(e.joint_state("joint-1", 3)["control_state"], "IDLE")
                # the backend accepting the request is not confirmation
                e.termination_request_accepted(cid, "ref-" + cid, 4)
                self.assertEqual(e.command(cid)["state"], "ACCEPTED")
                # only confirmation ends it
                done = e.termination_confirmed(cid, "ref-" + cid, 5)
                self.assertEqual((e.command(cid)["state"], e.command(cid)["reason_code"], e.command(cid)["phase"]),
                                 ("CANCELLED", reason, "NONE"))
                self.assertEqual(requests(done, "request_termination"), [])
                after = e.execution_started(cid, "ref-" + cid, 6)
                self.assertEqual([x["reason"] for x in after.ignored], ["terminal"])
                self.assertEqual(e.command(cid)["state"], "CANCELLED")
                invariants(self, e)

    def test_CT_LC_08(self):
        """Cancel before dispatch completes without backend termination only when Motion confirms no dispatch occurred."""
        for cause, reason in (("CANCEL_REQUESTED", "CANCEL_REQUESTED"), ("STOP_REQUESTED", "STOPPED")):
            with self.subTest(cause=cause):
                e = S.engine()
                S.ready(e, t=0)
                sub = e.submit(S.pos_cmd(0.5), 1, defer_dispatch=True)
                cid = sub.command_id
                self.assertEqual(sub.requests, [])                      # no dispatch was issued
                self.assertEqual((e.command(cid)["state"], e.command(cid)["phase"]), ("ACCEPTED", "NONE"))
                res = e.terminate(cid, cause, 2)
                c = e.command(cid)
                self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("CANCELLED", reason, "NONE"))
                self.assertEqual(res.requests, [])                      # no backend termination, no termination record
                self.assertIsNone(c["termination"])
                self.assertEqual([t["to"] for t in c["transitions"]], ["ACCEPTED", "CANCELLED"])
                # the dispatch can no longer be issued
                self.assertEqual([x["reason"] for x in e.dispatch(cid, 3).ignored], ["terminal"])
                self.assertEqual(e.joint_state("joint-1", 3)["control_state"], "IDLE")
        # once the dispatch was issued the command is not cancelled without confirmation
        e = S.engine()
        S.ready(e, t=0)
        cid = e.submit(S.pos_cmd(0.5), 1, defer_dispatch=True).command_id
        self.assertEqual(len(requests(e.dispatch(cid, 2), "dispatch")), 1)
        e.terminate(cid, "CANCEL_REQUESTED", 3)
        self.assertEqual((e.command(cid)["state"], e.command(cid)["phase"]), ("ACCEPTED", "TERMINATING"))
        self.assertEqual([x["reason"] for x in e.dispatch(cid, 4).ignored], ["terminating"])

    def test_CT_TMO_01(self):
        """Deadline expiry before start gives FAILED(DEADLINE_EXPIRED)."""
        e = S.engine()
        S.ready(e, t=0)
        cid = e.submit(S.pos_cmd(0.5, deadline_ms=300), 1, defer_dispatch=True).command_id
        e.tick(300)                                                     # 299 ms after acceptance
        self.assertEqual(e.command(cid)["state"], "ACCEPTED")
        res = e.tick(301)                                               # 300 ms after acceptance
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("FAILED", "DEADLINE_EXPIRED", "NONE"))
        self.assertEqual(res.requests, [])                              # never dispatched: nothing to terminate
        self.assertEqual(c["deadline_ms"], 300)
        self.assertEqual(e.joint_state("joint-1", 301)["health_state"], "READY")   # FAILED is not FAULTED
        # a command that started in time is not affected by its deadline
        e2 = S.engine()
        S.ready(e2, t=0)
        started, _ = S.submit_start(e2, S.pos_cmd(0.5, deadline_ms=300), 1, 200)
        e2.tick(10_000)
        self.assertEqual(e2.command(started)["state"], "RUNNING")
        # the effective default comes from configuration when the command gives none
        e3 = S.engine(S.config(default_deadline_ms=400))
        S.ready(e3, t=0)
        d = e3.submit(S.pos_cmd(0.5), 1, defer_dispatch=True).command_id
        e3.tick(400)
        self.assertEqual(e3.command(d)["state"], "ACCEPTED")
        e3.tick(401)
        self.assertEqual(e3.command(d)["reason_code"], "DEADLINE_EXPIRED")

    def test_CT_TMO_02(self):
        """Execution timeout starts termination; confirmed termination gives FAILED(EXECUTION_TIMEOUT)."""
        e = S.engine_optional_feedback()
        cid = running(e, execution_timeout_ms=400)                      # started at 1
        e.tick(400)
        self.assertEqual(e.command(cid)["phase"], "NONE")               # 399 ms after the start: nothing yet
        res = e.tick(401)                                               # 400 ms after the start
        c = e.command(cid)
        # detecting the timeout is not termination: still RUNNING, TERMINATING, joint still ACTIVE
        self.assertEqual((c["state"], c["phase"], c["reason_code"]), ("RUNNING", "TERMINATING", None))
        self.assertEqual([(q["op"], q["cause"]) for q in res.requests], [("request_termination", "EXECUTION_TIMEOUT")])
        self.assertEqual(e.joint_state("joint-1", 401)["control_state"], "ACTIVE")
        t = c["termination"]
        self.assertEqual(([x["cause"] for x in t["causes"]], t["outcome"], t["bound_ms"], t["requested_ms"]),
                         (["EXECUTION_TIMEOUT"], "PENDING", BOUND, 401))
        e.tick(900)                                                     # still inside the bound
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        done = e.termination_confirmed(cid, "ref-" + cid, 902)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("FAILED", "EXECUTION_TIMEOUT", "NONE"))
        self.assertEqual(c["termination"]["outcome"], "CONFIRMED")
        self.assertEqual(requests(done, "request_termination"), [])     # one request only
        snap = e.joint_state("joint-1", 902)
        # DEGRADED only because this engine has optional feedback and none arrived (PR-05); never FAULTED
        self.assertEqual((snap["control_state"], snap["health_state"]), ("IDLE", "DEGRADED"))
        self.assertNotIn("active_command_id", snap)
        self.assertEqual(e.faults("joint-1"), [])                       # FAILED does not fault the joint
        # the effective timeout is recorded, and a longer one is not cut short
        self.assertEqual(c["execution_timeout_ms"], 400)
        e2 = S.engine_optional_feedback()
        long_one = running(e2, execution_timeout_ms=900)
        e2.tick(800)
        self.assertEqual(e2.command(long_one)["phase"], "NONE")

    def test_CT_TMO_03(self):
        """Unconfirmed termination within the bound gives FAILED(TERMINATION_UNCONFIRMED), a faulted joint, never a stopped report."""
        e = S.engine()
        cid = running(e, execution_timeout_ms=400)
        e.tick(401)                                                     # termination requested at 401
        e.termination_request_accepted(cid, "ref-" + cid, 450)          # accepted, never confirmed
        e.tick(401 + BOUND - 1)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        self.assertEqual(e.joint_state("joint-1", 401 + BOUND - 1)["health_state"], "READY")
        res = e.tick(401 + BOUND)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("FAILED", "TERMINATION_UNCONFIRMED", "NONE"))
        self.assertEqual(c["termination"]["outcome"], "UNCONFIRMED")
        snap = e.joint_state("joint-1", 401 + BOUND)
        self.assertEqual((snap["health_state"], snap["control_state"]), ("FAULTED", "UNKNOWN"))
        self.assertNotIn("active_command_id", snap)
        faults = e.faults("joint-1")
        self.assertEqual([(f["code"], f["command_id"]) for f in faults], [("TERMINATION_UNCONFIRMED", cid)])
        self.assertEqual(snap["fault_ids"], [faults[0]["fault_id"]])
        self.assertIn("JOINT_FAULT_RAISED", [ev["event_type"] for ev in res.events])
        # the engine never reports the joint stopped: no confirmation exists, so no IDLE ever appears
        self.assertNotEqual(snap["control_state"], "IDLE")
        # a confirmation after the bound is ignored and recorded; the command and the joint do not change
        late = e.termination_confirmed(cid, "ref-" + cid, 401 + BOUND + 5)
        self.assertEqual([x["reason"] for x in late.ignored], ["terminal"])
        self.assertEqual(e.command(cid)["reason_code"], "TERMINATION_UNCONFIRMED")
        self.assertEqual(e.joint_state("joint-1", 401 + BOUND + 5)["control_state"], "UNKNOWN")
        # a faulted joint admits no ordinary motion
        self.assertFalse(e.submit(S.pos_cmd(0.5), 401 + BOUND + 6).admission.accepted)

    def test_CT_TMO_04(self):
        """Cancel with unconfirmed termination follows the same path."""
        outcomes = {}
        for label, kind in (("timeout", None), ("cancel", "CANCEL_REQUESTED"), ("stop", "STOP_REQUESTED")):
            e = S.engine()
            cid = running(e, execution_timeout_ms=400)
            if kind is None:
                e.tick(401)
                start = 401
            else:
                e.terminate(cid, kind, 50)
                start = 50
            self.assertEqual(e.command(cid)["phase"], "TERMINATING")
            e.tick(start + BOUND - 1)
            self.assertEqual(e.command(cid)["state"], "RUNNING")
            e.tick(start + BOUND)
            c, snap = e.command(cid), e.joint_state("joint-1", start + BOUND)
            outcomes[label] = (c["state"], c["reason_code"], c["phase"], c["termination"]["outcome"],
                               snap["health_state"], snap["control_state"], [f["code"] for f in e.faults("joint-1")])
        self.assertEqual(outcomes["cancel"], ("FAILED", "TERMINATION_UNCONFIRMED", "NONE", "UNCONFIRMED",
                                              "FAULTED", "UNKNOWN", ["TERMINATION_UNCONFIRMED"]))
        self.assertEqual(outcomes["cancel"], outcomes["timeout"])
        self.assertEqual(outcomes["cancel"], outcomes["stop"])
        # a cancellation request that is never confirmed is never reported CANCELLED
        self.assertNotEqual(outcomes["cancel"][0], "CANCELLED")

    def test_CT_TMO_06(self):
        """Durations use the monotonic clock: wall-clock steps do not alter timeouts."""
        def run(utc_of):
            e = S.engine_optional_feedback()
            S.ready(e, t=0)
            r = e.submit(S.vel_cmd(0.1, execution_timeout_ms=400, deadline_ms=700), 1, utc_of(1))
            cid = r.command_id
            e.execution_started(cid, "ref-" + cid, 2, utc_of(2))
            log = []
            for t in (100, 401, 402, 1402):
                res = e.tick(t, utc_of(t))
                c = e.command(cid)
                log.append((t, c["state"], c["phase"], c["reason_code"], [ev["event_type"] for ev in res.events],
                            [q["op"] for q in res.requests]))
            return log, [(x["to"], x["reason_code"], x["monotonic_ms"]) for x in e.command(cid)["transitions"]]
        steady = run(lambda t: "2026-11-08T00:00:%02dZ" % (t % 60))
        # the wall clock jumps backwards, forwards by years, and is absent
        wild = {1: "2999-01-01T00:00:00Z", 2: "1970-01-01T00:00:00Z", 100: "2026-11-08T00:00:00Z",
                401: "1999-12-31T23:59:59Z", 402: None, 1402: "not even a timestamp"}
        self.assertEqual(run(lambda t: wild[t]), steady)
        # the timeout fired at exactly 400 ms of monotonic time after the start (started at 2: due at 402)
        log, transitions = steady
        self.assertEqual([row[1:4] for row in log],
                         [("RUNNING", "NONE", None), ("RUNNING", "NONE", None), ("RUNNING", "TERMINATING", None),
                          ("FAILED", "NONE", "TERMINATION_UNCONFIRMED")])
        self.assertEqual(transitions[-1], ("FAILED", "TERMINATION_UNCONFIRMED", 1402))

    def test_CT_TMO_09(self):
        """Deadline expiry on a DISPATCH_PENDING command terminates it first, then FAILED(DEADLINE_EXPIRED)."""
        e = S.engine()
        S.ready(e, t=0)
        cid = e.submit(S.pos_cmd(0.5, deadline_ms=300), 1).command_id   # dispatched, no start confirmation
        self.assertEqual(e.command(cid)["phase"], "DISPATCH_PENDING")
        res = e.tick(301)
        c = e.command(cid)
        self.assertEqual((c["state"], c["phase"], c["reason_code"]), ("ACCEPTED", "TERMINATING", None))   # not FAILED yet
        self.assertEqual([(q["op"], q["cause"]) for q in res.requests], [("request_termination", "DEADLINE_EXPIRED")])
        # a start that arrives now is ignored and never revives the command
        self.assertEqual([x["reason"] for x in e.execution_started(cid, "ref-" + cid, 302).ignored], ["terminating"])
        self.assertEqual(e.command(cid)["state"], "ACCEPTED")
        done = e.termination_confirmed(cid, "ref-" + cid, 303)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("FAILED", "DEADLINE_EXPIRED", "NONE"))
        self.assertEqual(requests(done, "request_termination"), [])
        self.assertEqual(e.joint_state("joint-1", 303)["control_state"], "IDLE")
        self.assertEqual(e.faults("joint-1"), [])
        # without confirmation the same command ends FAILED(TERMINATION_UNCONFIRMED) and faults the joint
        e2 = S.engine()
        S.ready(e2, t=0)
        d = e2.submit(S.pos_cmd(0.5, deadline_ms=300), 1).command_id
        e2.tick(301)
        e2.tick(301 + BOUND)
        self.assertEqual(e2.command(d)["reason_code"], "TERMINATION_UNCONFIRMED")
        self.assertEqual(e2.joint_state("joint-1", 301 + BOUND)["health_state"], "FAULTED")

    def test_CT_TMO_11(self):
        """Reason selection: any STOP_REQUESTED gives STOPPED, otherwise CANCEL_REQUESTED; the first recorded of timeout and deadline wins."""
        # the selection rule over every ordered combination of one to three of the four causes
        import itertools
        causes = ["CANCEL_REQUESTED", "STOP_REQUESTED", "EXECUTION_TIMEOUT", "DEADLINE_EXPIRED"]
        seen = 0
        for n in (1, 2, 3):
            for seq in itertools.product(causes, repeat=n):
                with self.subTest(seq=seq):
                    timers = [c for c in seq if c in model.TIMER_CAUSES]
                    if timers:
                        expect = ("FAILED", timers[0])
                    else:
                        expect = ("CANCELLED", "STOPPED" if "STOP_REQUESTED" in seq else "CANCEL_REQUESTED")
                    self.assertEqual(model.outcome_of_causes(seq), expect)
                    seen += 1
        self.assertEqual(seen, 4 + 16 + 64)
        # the same through the engine, for the causes the engine can record in this pull request
        table = [(["CANCEL_REQUESTED"], "CANCELLED", "CANCEL_REQUESTED"),
                 (["STOP_REQUESTED"], "CANCELLED", "STOPPED"),
                 (["CANCEL_REQUESTED", "STOP_REQUESTED"], "CANCELLED", "STOPPED"),
                 (["STOP_REQUESTED", "CANCEL_REQUESTED"], "CANCELLED", "STOPPED"),
                 (["CANCEL_REQUESTED", "CANCEL_REQUESTED"], "CANCELLED", "CANCEL_REQUESTED")]
        for seq, state, reason in table:
            with self.subTest(engine=seq):
                e = S.engine()
                cid = running(e)
                for i, cause in enumerate(seq):
                    res = e.terminate(cid, cause, 10 + i)
                    self.assertEqual(len(requests(res, "request_termination")), 1 if i == 0 else 0)
                e.termination_confirmed(cid, "ref-" + cid, 20)
                c = e.command(cid)
                self.assertEqual((c["state"], c["reason_code"]), (state, reason))
                self.assertEqual([x["cause"] for x in c["termination"]["causes"]], seq)
        # a cancellation recorded first stays in the record when the timeout follows; the timeout decides
        e = S.engine()
        cid = running(e, execution_timeout_ms=400)
        e.terminate(cid, "CANCEL_REQUESTED", 100)
        e.tick(401)
        e.termination_confirmed(cid, "ref-" + cid, 402)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"]), ("FAILED", "EXECUTION_TIMEOUT"))
        self.assertEqual([x["cause"] for x in c["termination"]["causes"]], ["CANCEL_REQUESTED", "EXECUTION_TIMEOUT"])
        # and the same for a deadline that expires while a cancellation is outstanding
        e = S.engine()
        S.ready(e, t=0)
        cid = e.submit(S.pos_cmd(0.5, deadline_ms=300), 1).command_id
        e.terminate(cid, "STOP_REQUESTED", 100)
        e.tick(301)
        e.termination_confirmed(cid, "ref-" + cid, 302)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"]), ("FAILED", "DEADLINE_EXPIRED"))
        self.assertEqual([x["cause"] for x in c["termination"]["causes"]], ["STOP_REQUESTED", "DEADLINE_EXPIRED"])


if __name__ == "__main__":
    unittest.main()
