"""Conformance tests of the lifecycle engine, mapped one to one to conformance IDs (AC-306).

Each method below is the single executable test named by one IN_SCOPE entry of
tests/manifest/conformance_manifest.json for the IDs that KOS-MOTION-003 PR-02 covers. The method
name is the ID with hyphens replaced by underscores. Deterministic and offline. They show that the
engine follows the contract text for a supplied, ordered input stream; software evidence only,
never physical or safety validation.
"""
import unittest

import lifecycle_support as S
from kritva_motion.lifecycle import IllegalTransition, Result, model


def terminal_reason(to):
    return model.REASON_CODES[to][0] if to in model.TERMINAL_STATES else None


class TestLifecycleConformance(unittest.TestCase):
    def test_CT_LC_02(self):
        """Every pair of states not in 7.5 is refused, table-driven over all 25 ordered pairs."""
        allowed = {("ACCEPTED", "RUNNING"), ("ACCEPTED", "CANCELLED"), ("ACCEPTED", "FAILED"),
                   ("RUNNING", "COMPLETED"), ("RUNNING", "CANCELLED"), ("RUNNING", "FAILED")}
        pairs = [(a, b) for a in model.STATES for b in model.STATES]
        self.assertEqual(len(pairs), 25)
        self.assertEqual({p for p in pairs if model.is_allowed(*p)}, allowed)
        for a, b in pairs:
            with self.subTest(frm=a, to=b):
                e = S.engine()
                S.ready(e)
                r = e.submit(S.pos_cmd(), 1)
                c = e._commands[r.command_id]
                c.state = a   # put the record into the state under test (the only way to reach CANCELLED and FAILED in this pull request)
                before = (c.state, c.reason_code, c.phase, len(c.transitions))
                if (a, b) in allowed:
                    e._move(c, b, terminal_reason(b), 2, None, "TEST", Result())
                    self.assertEqual(c.state, b)
                    self.assertEqual(len(c.transitions), before[3] + 1)
                else:
                    with self.assertRaises(IllegalTransition):
                        e._move(c, b, terminal_reason(b), 2, None, "TEST", Result())
                    self.assertEqual((c.state, c.reason_code, c.phase, len(c.transitions)), before)

    def test_CT_LC_03(self):
        """A terminal state never changes; a late backend input after terminal is ignored and logged."""
        e = S.engine()
        S.ready(e)
        cid, _ = S.submit_start(e, S.vel_cmd(duration=100), 1, 2)
        self.assertEqual(e.tick(102).events[0]["data"]["to"], "COMPLETED")
        before = e.command(cid)
        self.assertEqual((before["state"], before["reason_code"]), ("COMPLETED", "DURATION_ELAPSED"))
        ref = before["backend_reference"]
        r = e.execution_started(cid, ref, 200)
        self.assertEqual([x["reason"] for x in r.ignored], ["terminal"])
        e.feedback("joint-1", S.sample(9.9), 300)
        e.feedback("joint-1", S.sample(0.5, validity="INVALID"), 301)
        e.tick(10**6)
        self.assertEqual(e.command(cid), before)
        self.assertEqual(e.ignored_log[0]["input"], "execution_started")
        self.assertEqual(e.ignored_log[0]["command_id"], cid)
        # a completed SET_POSITION stays completed when a later sample is out of tolerance
        e2 = S.engine()
        S.ready(e2)
        cid2, _ = S.submit_start(e2, S.pos_cmd(0.5), 1, 2)
        e2.feedback("joint-1", S.sample(0.5), 10)
        e2.feedback("joint-1", S.sample(0.5), 110)
        done = e2.command(cid2)
        self.assertEqual(done["state"], "COMPLETED")
        e2.feedback("joint-1", S.sample(-1.0), 120)
        self.assertEqual(e2.command(cid2), done)

    def test_CT_LC_04(self):
        """Acceptance does not imply RUNNING: RUNNING only on the backend start confirmation."""
        e = S.engine()
        S.ready(e)
        r = e.submit(S.pos_cmd(0.5), 1, "2026-11-08T00:00:01Z")
        self.assertTrue(r.admission.accepted)
        cid = r.command_id
        c = e.command(cid)
        self.assertEqual((c["state"], c["phase"], c["reason_code"]), ("ACCEPTED", "DISPATCH_PENDING", None))
        self.assertEqual([q["op"] for q in r.requests], ["dispatch"])
        # nothing but the start confirmation moves it: time, in-tolerance feedback, status reports
        e.tick(1500)
        e.feedback("joint-1", S.sample(0.5), 2000)
        e.status_report("joint-1", "ACTIVE", 0, 2001)
        self.assertEqual(e.command(cid)["state"], "ACCEPTED")
        # a start for another reference is ignored
        self.assertEqual([x["reason"] for x in e.execution_started(cid, "ref-other", 3000).ignored], ["reference_mismatch"])
        self.assertEqual(e.command(cid)["state"], "ACCEPTED")
        ok = e.execution_started(cid, c["backend_reference"], 3001, "2026-11-08T00:00:02Z")
        c = e.command(cid)
        self.assertEqual((c["state"], c["phase"], c["reason_code"]), ("RUNNING", "NONE", None))
        self.assertEqual(ok.events[0]["data"], {"from": "ACCEPTED", "to": "RUNNING", "reason_code": None, "phase": "NONE"})
        self.assertEqual(e.joint_state("joint-1", 3001)["control_state"], "ACTIVE")
        # a second start is ignored as a duplicate
        self.assertEqual([x["reason"] for x in e.execution_started(cid, c["backend_reference"], 3002).ignored], ["duplicate"])

    def test_CT_ARB_02(self):
        """Commands on independent joints run concurrently; a joint holds one movement at a time."""
        e = S.engine()
        for jid in ("joint-1", "joint-c", "joint-p"):
            S.ready(e, jid)
        a, _ = S.submit_start(e, S.pos_cmd(0.5, "joint-1", client_request_id="r1"), 1)
        b, _ = S.submit_start(e, S.vel_cmd(0.1, "joint-c", client_request_id="r2"), 2)
        c, _ = S.submit_start(e, S.pos_cmd(0.2, "joint-p", "m", client_request_id="r3"), 3)
        self.assertEqual([e.command(x)["state"] for x in (a, b, c)], ["RUNNING"] * 3)
        for jid, cid in (("joint-1", a), ("joint-c", b), ("joint-p", c)):
            js = e.joint_state(jid, 4)
            self.assertEqual((js["control_state"], js["active_command_id"]), ("ACTIVE", cid))
        busy = e.submit(S.vel_cmd(0.2, "joint-1", client_request_id="r4"), 5)
        self.assertEqual((busy.admission.accepted, busy.admission.code, busy.admission.step),
                         (False, "TARGET_BUSY", 11))
        self.assertEqual(busy.admission.conflict["command_id"], a)
        self.assertIsNone(busy.command_id)
        self.assertEqual(len(e.commands()), 3)

    def test_CT_CMP_01(self):
        """SET_POSITION completes only after tolerance and settling with valid fresh feedback."""
        def run(samples, until=None):
            e = S.engine()
            S.ready(e)
            cid, _ = S.submit_start(e, S.pos_cmd(0.5), 10)
            done_at = None
            for t, kw in samples:
                e.feedback("joint-1", S.sample(**kw), t)
                if done_at is None and e.command(cid)["state"] == "COMPLETED":
                    done_at = t
            return e, cid, done_at
        inside = {"pos": 0.505}
        # tolerance 0.01 and settling 100 ms: window from t=20, complete at t=120 and not before
        e, cid, at = run([(20, inside), (70, inside), (119, inside), (120, inside)])
        self.assertEqual(at, 120)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"]), ("COMPLETED", "GOAL_REACHED"))
        self.assertEqual(e.joint_state("joint-1", 120)["control_state"], "IDLE")
        # a sample outside the tolerance restarts the window
        e, cid, at = run([(20, inside), (60, {"pos": 0.52}), (70, inside), (169, inside), (170, inside)])
        self.assertEqual(at, 170)
        # an invalid sample restarts the window and is never evidence
        e, cid, at = run([(20, inside), (60, {"pos": 0.5, "validity": "INVALID"}), (70, inside), (169, inside), (170, inside)])
        self.assertEqual(at, 170)
        # a gap longer than max_feedback_age_ms (200) restarts the window: the sample at 300 starts a new one
        e, cid, at = run([(20, inside), (300, inside), (399, inside), (400, inside)])
        self.assertEqual(at, 400)
        # samples before the confirmed start are not evidence
        e = S.engine()
        S.ready(e, pos=0.5)
        r = e.submit(S.pos_cmd(0.5), 10)
        e.feedback("joint-1", S.sample(0.5), 20)
        e.feedback("joint-1", S.sample(0.5), 200)
        self.assertEqual(e.command(r.command_id)["state"], "ACCEPTED")

    def test_CT_CMP_02(self):
        """A command whose condition cannot be established is never COMPLETED."""
        # SET_POSITION: no feedback after the start
        e = S.engine()
        S.ready(e, pos=0.5)   # the joint already measured the target before the start
        cid, _ = S.submit_start(e, S.pos_cmd(0.5), 10)
        e.tick(50)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        # only invalid samples
        for t in range(100, 2000, 100):
            e.feedback("joint-1", S.sample(0.5, validity="INVALID"), t)
        e.tick(10**7)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        # the commanded value and the start confirmation are not evidence; only a valid sample counts
        self.assertEqual(e.command(cid)["reason_code"], None)
        # SET_VELOCITY without duration never completes by itself
        e2 = S.engine()
        S.ready(e2)
        vid, _ = S.submit_start(e2, S.vel_cmd(0.1), 10)
        for t in (10**3, 10**6, 10**9):
            e2.tick(t)
            e2.feedback("joint-1", S.sample(0.0), t)
        self.assertEqual(e2.command(vid)["state"], "RUNNING")
        self.assertEqual(e2.joint_state("joint-1", 10**9)["control_state"], "ACTIVE")

    def test_CT_CMP_03(self):
        """SET_VELOCITY with duration completes at expiry; without duration it remains active."""
        e = S.engine()
        S.ready(e)
        r = e.submit(S.vel_cmd(0.1, duration=1000), 10, "2026-11-08T00:00:00Z")
        cid = r.command_id
        e.execution_started(cid, e.command(cid)["backend_reference"], 500)   # confirmed start at 500
        e.tick(1010, "2030-01-01T00:00:00Z")    # 1000 ms after acceptance: not complete (the clock runs from the start)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e.tick(1499, "1999-01-01T00:00:00Z")    # the supplied UTC strings have no effect on time
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e.tick(1500)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"]), ("COMPLETED", "DURATION_ELAPSED"))
        self.assertEqual(e.joint_state("joint-1", 1500)["control_state"], "IDLE")
        # without duration_ms the command stays active
        e2 = S.engine()
        S.ready(e2)
        vid, _ = S.submit_start(e2, S.vel_cmd(0.1), 10)
        e2.tick(10**8)
        self.assertEqual(e2.command(vid)["state"], "RUNNING")

    def test_CT_TMO_05(self):
        """Effective default deadline and timeout come from configuration and are recorded in the command record."""
        e = S.engine(S.config(default_deadline_ms=1234, default_execution_timeout_ms=4321))
        S.ready(e)
        r = e.submit(S.pos_cmd(0.5, client_request_id="a"), 1, "2026-11-08T00:00:00Z")
        c = e.command(r.command_id)
        self.assertEqual((c["deadline_ms"], c["execution_timeout_ms"]), (1234, 4321))
        self.assertEqual((c["config_version"], c["config_digest"]), ("1", "digest-1"))
        d = r.requests[0]
        self.assertEqual((d["deadline_ms"], d["execution_timeout_ms"], d["config_version"], d["config_digest"]),
                         (1234, 4321, "1", "digest-1"))
        # a command value replaces the default, both in the record and in the dispatch request
        e2 = S.engine(S.config(default_deadline_ms=1234, default_execution_timeout_ms=4321))
        S.ready(e2)
        r2 = e2.submit(S.pos_cmd(0.5, deadline_ms=3000, execution_timeout_ms=2000), 1)
        c2 = e2.command(r2.command_id)
        self.assertEqual((c2["deadline_ms"], c2["execution_timeout_ms"]), (3000, 2000))
        self.assertEqual((r2.requests[0]["deadline_ms"], r2.requests[0]["execution_timeout_ms"]), (3000, 2000))
        # the values are fixed for the life of the command
        e2.execution_started(r2.command_id, c2["backend_reference"], 2)
        e2.tick(500)
        c3 = e2.command(r2.command_id)
        self.assertEqual((c3["deadline_ms"], c3["execution_timeout_ms"], c3["config_version"], c3["config_digest"]),
                         (3000, 2000, "1", "digest-1"))

    def test_CT_FB_02(self):
        """Both timestamps are recorded; an unsynchronized backend clock is flagged."""
        e = S.engine()
        e.feedback("joint-1", S.sample(0.1, synchronized=False, stamp="2026-11-08T10:00:00Z"), 1000, "2026-11-08T09:00:00Z")
        rec = e.feedback_record("joint-1")
        self.assertEqual((rec["backend_timestamp"], rec["received_ms"], rec["received_at"]),
                         ("2026-11-08T10:00:00Z", 1000, "2026-11-08T09:00:00Z"))
        self.assertEqual((rec["clock_domain"], rec["clock_synchronized"], rec["clock_unsynchronized"]),
                         ("backend-clock", False, True))
        snap = e.joint_state("joint-1", 1000)
        self.assertEqual((snap["backend_clock_domain"], snap["backend_clock_synchronized"]), ("backend-clock", False))
        # a synchronized clock is not flagged; an undeclared status is flagged (fail closed)
        e.feedback("joint-1", S.sample(0.1, synchronized=True), 1001)
        self.assertFalse(e.feedback_record("joint-1")["clock_unsynchronized"])
        undeclared = S.sample(0.1)
        del undeclared["clock_synchronized"]
        e.feedback("joint-1", undeclared, 1002)
        self.assertTrue(e.feedback_record("joint-1")["clock_unsynchronized"])
        # freshness is decided by the receipt time only, never by comparing backend timestamps
        for i, stamp in enumerate(("1970-01-01T00:00:00Z", "2999-12-31T23:59:59Z")):
            base = 2000 + i * 1000
            e.feedback("joint-1", S.sample(0.1, stamp=stamp), base)
            self.assertEqual(e.joint_state("joint-1", base + 200)["feedback_status"], "VALID")
            self.assertEqual(e.joint_state("joint-1", base + 201)["feedback_status"], "STALE")
            self.assertFalse(e.joint_state("joint-1", base + 201)["is_current"])

    def test_CT_VAL_11(self):
        """SET_POSITION is absolute, SET_VELOCITY is signed, and a zero velocity is neither STOP nor HOLD."""
        e = S.engine()
        S.ready(e, pos=1.0)    # the joint is at 1.0 rad
        r = e.submit(S.pos_cmd(0.5), 1)
        d = r.requests[0]
        self.assertEqual((d["operation"], d["parameters"]), ("SET_POSITION", {"target_position": 0.5, "unit": "rad"}))
        e.execution_started(r.command_id, d["backend_reference"], 2)    # absolute: not an offset from 1.0
        e2 = S.engine()
        S.ready(e2)
        neg = e2.submit(S.vel_cmd(-0.3), 1)
        self.assertEqual(neg.requests[0]["parameters"]["target_velocity"], -0.3)
        e3 = S.engine()
        S.ready(e3)
        z = e3.submit(S.vel_cmd(0.0), 1)
        self.assertTrue(z.admission.accepted)
        self.assertEqual([q["op"] for q in z.requests], ["dispatch"])
        self.assertEqual((z.requests[0]["operation"], z.requests[0]["parameters"]["target_velocity"]), ("SET_VELOCITY", 0.0))
        e3.execution_started(z.command_id, z.requests[0]["backend_reference"], 2)
        c = e3.command(z.command_id)
        js = e3.joint_state("joint-1", 2)
        self.assertEqual((c["operation"], c["state"]), ("SET_VELOCITY", "RUNNING"))
        self.assertEqual((js["control_state"], js["active_command_id"]), ("ACTIVE", z.command_id))   # not IDLE: it is not STOP, not HOLDING: not HOLD


if __name__ == "__main__":
    unittest.main()
