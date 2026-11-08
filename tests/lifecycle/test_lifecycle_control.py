"""Conformance tests of STOP, HOLD, CANCEL and arbitration (AC-306).

Each method is the single executable test named by one IN_SCOPE entry of
tests/manifest/conformance_manifest.json for the IDs that KOS-MOTION-003 PR-04 covers. The method
name is the ID with hyphens replaced by underscores. Deterministic and offline. Software evidence
only: every confirmation here is a supplied input, never proof that anything stopped, held or
released physically (contract 2.4, 17.5).

Configuration (tests/validator/test_admission.py): termination_confirm_timeout_ms 1000, default
execution timeout 5000, max_feedback_age_ms 200. A joint is made ready at the time of use, so its
feedback is fresh at admission.
"""
import unittest

import lifecycle_support as S
from kritva_motion.lifecycle import model

BOUND = 1000


def requests(res, op=None):
    return [r for r in res.requests if op is None or r["op"] == op]


def running_move(e, t=1):
    """A SET_VELOCITY command, accepted and started at t on a joint made ready at t."""
    S.ready(e, t=t)
    cid, _ = S.submit_start(e, S.vel_cmd(0.1), t, t)
    return cid


def hold_engaged(e, t=1):
    """Make the joint HOLDING through the real path: HOLD accepted, started, confirmed."""
    S.ready(e, t=t)
    r = e.submit(S.hold_cmd(), t)
    assert r.admission.accepted, r.admission
    hid = r.command_id
    e.execution_started(hid, "ref-" + hid, t)
    e.hold_confirmed(hid, "ref-" + hid, t)
    assert e.joint_state("joint-1", t)["control_state"] == "HOLDING"
    return hid


def states(e, *ids):
    return [(e.command(i)["state"], e.command(i)["reason_code"]) for i in ids]


class TestControlConformance(unittest.TestCase):
    def test_CT_ARB_03(self):
        """STOP is accepted on a busy joint; the active command ends CANCELLED(STOPPED) after confirmation."""
        for how in ("running", "dispatch_pending", "not_dispatched"):
            with self.subTest(active=how):
                e = S.engine()
                S.ready(e, t=1)
                if how == "running":
                    xid, _ = S.submit_start(e, S.vel_cmd(0.1), 1, 1)
                else:
                    xid = e.submit(S.vel_cmd(0.1), 1, defer_dispatch=(how == "not_dispatched")).command_id
                # an ordinary movement is TARGET_BUSY; the STOP never is
                busy = e.submit(S.pos_cmd(0.2), 2)
                self.assertEqual((busy.admission.code, busy.admission.conflict["command_id"]), ("TARGET_BUSY", xid))
                r = e.submit(S.stop_cmd(), 3)
                self.assertTrue(r.admission.accepted, r.admission)
                sid = r.command_id
                self.assertEqual(e.command(sid)["operation"], "STOP")
                if how == "not_dispatched":
                    # never dispatched: the command ends at once, and the STOP still needs its own confirmation
                    self.assertEqual(states(e, xid), [("CANCELLED", "STOPPED")])
                    self.assertEqual(e.command(sid)["references"], sid)
                    owner = sid
                else:
                    x = e.command(xid)
                    self.assertEqual((x["state"], x["phase"]), (("RUNNING" if how == "running" else "ACCEPTED"), "TERMINATING"))
                    self.assertEqual([(q["command_id"], q["cause"]) for q in requests(r, "request_termination")],
                                     [(xid, "STOP_REQUESTED")])
                    self.assertEqual(e.command(sid)["references"], xid)
                    owner = xid
                self.assertEqual(e.command(sid)["state"], "ACCEPTED")   # receipt is not success
                e.termination_request_accepted(owner, "ref-" + owner, 4)
                self.assertEqual(e.command(sid)["state"], "RUNNING")
                e.termination_confirmed(owner, "ref-" + owner, 5)
                self.assertEqual(states(e, sid), [("COMPLETED", "STOP_CONFIRMED")])
                if how != "not_dispatched":
                    self.assertEqual(states(e, xid), [("CANCELLED", "STOPPED")])
                self.assertEqual(e.joint_state("joint-1", 5)["control_state"], "IDLE")
                self.assertTrue(all(c["phase"] == "NONE" for c in e.commands() if c["state"] in model.TERMINAL_STATES))

    def test_CT_ARB_04(self):
        """STOP is not reported COMPLETED on receipt, only on backend confirmation."""
        e = S.engine()
        S.ready(e, t=1)
        r = e.submit(S.stop_cmd(), 2)
        sid = r.command_id
        self.assertEqual((e.command(sid)["state"], e.command(sid)["phase"]), ("ACCEPTED", "TERMINATING"))
        # an idle joint with no active command is not evidence of a stop: nothing completes it but the confirmation
        for t in (3, 100, 500, 900):
            e.tick(t)
            self.assertEqual(e.command(sid)["state"] in model.TERMINAL_STATES, False)
        e.termination_request_accepted(sid, "ref-" + sid, 910)           # acceptance is not confirmation
        self.assertEqual(e.command(sid)["state"], "RUNNING")
        self.assertNotEqual(e.command(sid)["state"], "COMPLETED")
        self.assertEqual(e.joint_state("joint-1", 910)["control_state"], "IDLE")
        e.termination_confirmed(sid, "ref-" + sid, 950)
        c = e.command(sid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("COMPLETED", "STOP_CONFIRMED", "NONE"))
        self.assertEqual([t["to"] for t in c["transitions"]], ["ACCEPTED", "RUNNING", "COMPLETED"])
        # a confirmation for another reference is ignored and the STOP is not completed by it
        e2 = S.engine()
        S.ready(e2, t=1)
        s2 = e2.submit(S.stop_cmd(), 2).command_id
        self.assertEqual([x["reason"] for x in e2.termination_confirmed(s2, "wrong", 3).ignored], ["reference_mismatch"])
        self.assertEqual(e2.command(s2)["state"], "ACCEPTED")

    def test_CT_ARB_07(self):
        """HOLD completes on engagement, the joint enters HOLDING; a later movement ends the hold; STOP ends it."""
        e = S.engine()
        S.ready(e, t=1)
        r = e.submit(S.hold_cmd(), 1)
        hid = r.command_id
        self.assertEqual([q["op"] for q in r.requests], ["request_hold"])
        self.assertEqual((e.command(hid)["state"], e.command(hid)["phase"]), ("ACCEPTED", "DISPATCH_PENDING"))
        self.assertEqual(e.submit(S.pos_cmd(0.2), 2).admission.code, "TARGET_BUSY")   # a pending HOLD holds the slot
        self.assertEqual([x["reason"] for x in e.hold_confirmed(hid, "ref-" + hid, 3).ignored], ["not_started"])
        e.execution_started(hid, "ref-" + hid, 4)
        self.assertEqual(e.command(hid)["state"], "RUNNING")
        self.assertEqual(e.joint_state("joint-1", 4)["control_state"], "IDLE")        # not engaged yet
        e.hold_confirmed(hid, "ref-" + hid, 5)
        c = e.command(hid)
        self.assertEqual((c["state"], c["reason_code"]), ("COMPLETED", "HOLD_ENGAGED"))
        snap = e.joint_state("joint-1", 5)
        self.assertEqual(snap["control_state"], "HOLDING")
        self.assertNotIn("active_command_id", snap)
        # a later movement ends the hold: it is accepted, and its start releases the hold
        e.feedback("joint-1", S.sample(0.0), 6)
        m = e.submit(S.pos_cmd(0.2), 6)
        self.assertTrue(m.admission.accepted, m.admission)
        started = e.execution_started(m.command_id, "ref-" + m.command_id, 7)
        self.assertEqual([q["op"] for q in started.requests], ["release_hold"])
        self.assertEqual(e.joint_state("joint-1", 7)["control_state"], "ACTIVE")
        # and a STOP ends it
        e2 = S.engine()
        hold_engaged(e2, t=1)
        sid = e2.submit(S.stop_cmd(), 2).command_id
        e2.termination_confirmed(sid, "ref-" + sid, 3)
        self.assertEqual(e2.joint_state("joint-1", 3)["control_state"], "IDLE")

    def test_CT_ARB_09(self):
        """STOP on a FAULTED joint is accepted best effort; completion does not clear or hide the fault."""
        e = S.engine()
        xid = running_move(e, 1)
        e.terminate(xid, "CANCEL_REQUESTED", 2)
        e.tick(2 + BOUND)                                    # unconfirmed: the joint is FAULTED and UNKNOWN
        before = e.joint_state("joint-1", 2 + BOUND)
        self.assertEqual((before["health_state"], before["control_state"]), ("FAULTED", "UNKNOWN"))
        fault = e.faults("joint-1")
        t0 = 2 + BOUND + 10
        r = e.submit(S.stop_cmd(), t0)
        self.assertTrue(r.admission.accepted, r.admission)    # best effort: accepted on a FAULTED joint
        sid = r.command_id
        self.assertEqual(e.submit(S.pos_cmd(0.2), t0 + 1).admission.accepted, False)   # ordinary motion still refused
        e.termination_request_accepted(sid, "ref-" + sid, t0 + 2)
        e.termination_confirmed(sid, "ref-" + sid, t0 + 3)
        self.assertEqual(states(e, sid), [("COMPLETED", "STOP_CONFIRMED")])
        after = e.joint_state("joint-1", t0 + 3)
        self.assertEqual(after["control_state"], "IDLE")                         # a confirmed STOP establishes IDLE
        self.assertEqual(after["health_state"], "FAULTED")                       # and does not clear or hide the fault
        self.assertEqual(after["fault_ids"], before["fault_ids"])
        self.assertEqual(e.faults("joint-1"), fault)
        # the earlier command keeps its own outcome
        self.assertEqual(states(e, xid), [("FAILED", "TERMINATION_UNCONFIRMED")])

    def test_CT_ARB_10(self):
        """STOP on an idle joint completes only on backend confirmation; no confirmation within the bound gives FAILED(TERMINATION_UNCONFIRMED) and UNKNOWN."""
        e = S.engine()
        S.ready(e, t=1)
        r = e.submit(S.stop_cmd(), 2)
        sid = r.command_id
        self.assertEqual([(q["op"], q["cause"]) for q in r.requests], [("request_termination", "STOP_REQUESTED")])
        self.assertEqual(e.command(sid)["termination"]["bound_ms"], BOUND)
        e.termination_request_accepted(sid, "ref-" + sid, 3)
        e.tick(2 + BOUND - 1)
        self.assertEqual(e.command(sid)["state"], "RUNNING")
        self.assertEqual(e.joint_state("joint-1", 2 + BOUND - 1)["control_state"], "IDLE")
        e.tick(2 + BOUND)
        c = e.command(sid)
        self.assertEqual((c["state"], c["reason_code"]), ("FAILED", "TERMINATION_UNCONFIRMED"))
        self.assertEqual(c["termination"]["outcome"], "UNCONFIRMED")
        snap = e.joint_state("joint-1", 2 + BOUND)
        self.assertEqual(snap["control_state"], "UNKNOWN")
        self.assertEqual(snap["health_state"], "FAULTED")
        self.assertEqual([f["code"] for f in e.faults("joint-1")], ["TERMINATION_UNCONFIRMED"])
        # on a joint whose state was never established, a confirmed STOP establishes IDLE and no fault is involved
        e2 = S.engine()
        self.assertEqual(e2.joint_state("joint-1", 1)["control_state"], "UNKNOWN")
        s2 = e2.submit(S.stop_cmd(), 2).command_id
        self.assertTrue(e2.command(s2))
        e2.termination_confirmed(s2, "ref-" + s2, 3)
        snap = e2.joint_state("joint-1", 3)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("IDLE", "READY"))
        self.assertEqual(e2.faults("joint-1"), [])

    def test_CT_ARB_11(self):
        """STOP on a HOLDING joint releases the hold and completes on confirmation."""
        e = S.engine()
        hold_engaged(e, t=1)
        r = e.submit(S.stop_cmd(), 2)
        sid = r.command_id
        self.assertEqual([q["op"] for q in r.requests], ["release_hold", "request_termination"])
        self.assertEqual(e.joint_state("joint-1", 2)["control_state"], "HOLDING")     # until the backend confirms
        self.assertEqual(e.command(sid)["state"], "ACCEPTED")
        e.termination_request_accepted(sid, "ref-" + sid, 3)
        self.assertEqual(e.joint_state("joint-1", 3)["control_state"], "HOLDING")
        e.termination_confirmed(sid, "ref-" + sid, 4)
        self.assertEqual(states(e, sid), [("COMPLETED", "STOP_CONFIRMED")])
        self.assertEqual(e.joint_state("joint-1", 4)["control_state"], "IDLE")
        # without confirmation the hold is not reported released
        e2 = S.engine()
        hold_engaged(e2, t=1)
        s2 = e2.submit(S.stop_cmd(), 2).command_id
        e2.tick(2 + BOUND)
        self.assertEqual(states(e2, s2), [("FAILED", "TERMINATION_UNCONFIRMED")])
        self.assertEqual(e2.joint_state("joint-1", 2 + BOUND)["control_state"], "UNKNOWN")

    def test_CT_ARB_13(self):
        """Repeated HOLD on a HOLDING joint is accepted and completes on confirmation; a second HOLD while engagement is pending gives TARGET_BUSY."""
        e = S.engine()
        first = hold_engaged(e, t=1)
        e.feedback("joint-1", S.sample(0.0), 2)
        r = e.submit(S.hold_cmd(), 2)
        self.assertTrue(r.admission.accepted, r.admission)
        again = r.command_id
        self.assertNotEqual(again, first)                                 # a new, traceable operation
        self.assertEqual([q["op"] for q in r.requests], ["request_hold"])
        self.assertEqual(e.joint_state("joint-1", 2)["control_state"], "HOLDING")
        busy = e.submit(S.hold_cmd(), 3)                                  # a second HOLD while engagement is pending
        self.assertEqual((busy.admission.code, busy.admission.conflict["command_id"]), ("TARGET_BUSY", again))
        self.assertEqual(len(e.commands()), 2)
        e.execution_started(again, "ref-" + again, 4)
        self.assertEqual(e.command(again)["state"], "RUNNING")            # not completed by the request or the start
        e.hold_confirmed(again, "ref-" + again, 5)
        self.assertEqual(states(e, again), [("COMPLETED", "HOLD_ENGAGED")])
        self.assertEqual(e.joint_state("joint-1", 5)["control_state"], "HOLDING")
        # a cancelled pending HOLD is not completed by a late engagement report
        e.feedback("joint-1", S.sample(0.0), 6)
        c = e.submit(S.hold_cmd(), 6).command_id
        e.execution_started(c, "ref-" + c, 7)
        e.terminate(c, "CANCEL_REQUESTED", 8)
        self.assertEqual([x["reason"] for x in e.hold_confirmed(c, "ref-" + c, 9).ignored], ["terminating"])
        self.assertEqual(e.command(c)["state"], "RUNNING")

    def test_CT_ARB_15(self):
        """A movement command on a HOLDING joint releases the hold at start; a failed release ends it FAILED(BACKEND_REJECTED_DISPATCH)."""
        # release succeeds
        e = S.engine()
        hold_engaged(e, t=1)
        e.feedback("joint-1", S.sample(0.0), 2)
        m = e.submit(S.vel_cmd(0.1), 2)
        mid = m.command_id
        self.assertTrue(m.admission.accepted, m.admission)
        self.assertNotIn("release_hold", [q["op"] for q in m.requests])   # the release happens at the start
        self.assertEqual(e.joint_state("joint-1", 2)["control_state"], "HOLDING")
        st = e.execution_started(mid, "ref-" + mid, 3)
        self.assertEqual([q["op"] for q in st.requests], ["release_hold"])
        self.assertEqual(e.joint_state("joint-1", 3)["control_state"], "ACTIVE")
        e.hold_released(mid, "ref-" + mid, 4)
        self.assertEqual([x["reason"] for x in e.hold_release_failed(mid, "ref-" + mid, 5).ignored], ["no_release_pending"])
        self.assertEqual(e.command(mid)["state"], "RUNNING")
        # release fails
        e2 = S.engine()
        hold_engaged(e2, t=1)
        e2.feedback("joint-1", S.sample(0.0), 2)
        mid = e2.submit(S.vel_cmd(0.1), 2).command_id
        e2.execution_started(mid, "ref-" + mid, 3)
        e2.hold_release_failed(mid, "ref-" + mid, 4)
        c = e2.command(mid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("FAILED", "BACKEND_REJECTED_DISPATCH", "NONE"))
        snap = e2.joint_state("joint-1", 4)
        self.assertEqual(snap["control_state"], "UNKNOWN")              # neither HOLDING nor IDLE is assumed
        self.assertNotIn("active_command_id", snap)
        self.assertEqual((snap["health_state"], e2.faults("joint-1")), ("READY", []))   # FAILED is not FAULTED
        self.assertEqual(e2.submit(S.pos_cmd(0.2), 5).admission.code, "TARGET_STATE_UNKNOWN")
        # the state is re-established only from a fresh authoritative report
        e2.status_report("joint-1", "HOLDING", 0, 6)
        self.assertEqual(e2.joint_state("joint-1", 6)["control_state"], "HOLDING")

    def test_CT_TMO_10(self):
        """STOP during an outstanding termination joins it; a STOP after a terminal outcome starts a new attempt and leaves the old record unchanged."""
        e = S.engine()
        xid = running_move(e, 1)
        e.terminate(xid, "CANCEL_REQUESTED", 100)
        e.termination_request_accepted(xid, "ref-" + xid, 120)
        r = e.submit(S.stop_cmd(), 600)
        sid = r.command_id
        self.assertNotEqual(sid, xid)                                       # its own command id
        self.assertEqual(requests(r, "request_termination"), [])            # no second backend request
        t = e.command(xid)["termination"]
        self.assertEqual([c["cause"] for c in t["causes"]], ["CANCEL_REQUESTED", "STOP_REQUESTED"])
        self.assertEqual((t["requested_ms"], t["bound_ms"]), (100, BOUND))  # the bound is not restarted
        self.assertEqual(e.command(sid)["state"], "RUNNING")                # the attempt was already accepted
        e.tick(100 + BOUND - 1)
        self.assertEqual(states(e, xid, sid), [("RUNNING", None), ("RUNNING", None)])
        e.tick(100 + BOUND)                                                 # the first request's bound
        self.assertEqual(states(e, xid, sid), [("FAILED", "TERMINATION_UNCONFIRMED")] * 2)
        # joined and confirmed: the target ends by the most consequential cause, the STOP is COMPLETED
        e2 = S.engine()
        x2 = running_move(e2, 1)
        e2.terminate(x2, "CANCEL_REQUESTED", 100)
        s2 = e2.submit(S.stop_cmd(), 200).command_id
        e2.termination_confirmed(x2, "ref-" + x2, 300)
        self.assertEqual(states(e2, x2, s2), [("CANCELLED", "STOPPED"), ("COMPLETED", "STOP_CONFIRMED")])
        # a STOP joined to a timeout attempt is COMPLETED even though its target FAILED
        e3 = S.engine()
        S.ready(e3, t=1)
        x3, _ = S.submit_start(e3, S.vel_cmd(0.1, execution_timeout_ms=400), 1, 1)
        e3.tick(401)
        s3 = e3.submit(S.stop_cmd(), 402).command_id
        e3.termination_confirmed(x3, "ref-" + x3, 403)
        self.assertEqual(states(e3, x3, s3), [("FAILED", "EXECUTION_TIMEOUT"), ("COMPLETED", "STOP_CONFIRMED")])
        # after a terminal outcome a new STOP is a new operation with its own attempt; the old record is untouched
        old = e2.command(x2)["termination"]
        e2.feedback("joint-1", S.sample(0.0), 400)
        n = e2.submit(S.stop_cmd(), 401)
        nid = n.command_id
        self.assertEqual([(q["command_id"], q["op"]) for q in n.requests], [(nid, "request_termination")])
        self.assertEqual(e2.command(x2)["termination"], old)
        self.assertEqual(e2.command(nid)["termination"]["requested_ms"], 401)
        self.assertEqual(e2.command(nid)["references"], nid)

    def test_CT_ARB_16(self):
        """Backend refusal of STOP before any attempt gives FAILED(BACKEND_REJECTED_DISPATCH) and not TERMINATION_UNCONFIRMED; backend loss on an active joint sets UNKNOWN."""
        e = S.engine()
        S.ready(e, t=1)
        sid = e.submit(S.stop_cmd(), 2).command_id
        joined = e.submit(S.stop_cmd(), 3).command_id                      # a second STOP joins the first
        self.assertEqual(e.command(joined)["references"], sid)
        e.termination_refused(sid, "ref-" + sid, 4)
        self.assertEqual(states(e, sid, joined), [("FAILED", "BACKEND_REJECTED_DISPATCH")] * 2)
        snap = e.joint_state("joint-1", 4)
        self.assertEqual((snap["control_state"], snap["health_state"]), ("IDLE", "READY"))   # 2.4 (a): unchanged, no fault
        self.assertEqual(e.faults("joint-1"), [])
        e.tick(2 + BOUND + 5)                                               # the bound never turns it into UNCONFIRMED
        self.assertEqual(e.command(sid)["reason_code"], "BACKEND_REJECTED_DISPATCH")
        self.assertEqual(e.joint_state("joint-1", 2 + BOUND + 5)["health_state"], "READY")
        # a refusal after the backend accepted the request, or for a movement command, is not a refusal
        e2 = S.engine()
        S.ready(e2, t=1)
        s2 = e2.submit(S.stop_cmd(), 2).command_id
        e2.termination_request_accepted(s2, "ref-" + s2, 3)
        self.assertEqual([x["reason"] for x in e2.termination_refused(s2, "ref-" + s2, 4).ignored], ["already_accepted"])
        e3 = S.engine()
        x3 = running_move(e3, 1)
        e3.terminate(x3, "STOP_REQUESTED", 2)
        self.assertEqual([x["reason"] for x in e3.termination_refused(x3, "ref-" + x3, 3).ignored], ["not_a_stop_attempt"])
        # backend loss on an active, holding or terminating joint sets UNKNOWN (2.4 c); an idle joint stays IDLE
        e4 = S.engine()
        running_move(e4, 1)
        e4.backend_health("UNAVAILABLE", 2)
        self.assertEqual(e4.joint_state("joint-1", 2)["control_state"], "UNKNOWN")
        e4.backend_health("AVAILABLE", 3)                                   # the backend returning never leaves UNKNOWN
        self.assertEqual(e4.joint_state("joint-1", 3)["control_state"], "UNKNOWN")
        e5 = S.engine()
        hold_engaged(e5, 1)
        e5.backend_health("FAULTED", 2)
        self.assertEqual(e5.joint_state("joint-1", 2)["control_state"], "UNKNOWN")
        e6 = S.engine()
        S.ready(e6, t=1)
        e6.backend_health("UNAVAILABLE", 2)
        self.assertEqual(e6.joint_state("joint-1", 2)["control_state"], "IDLE")
        # a STOP is then rejected at admission: a rejection, not an unconfirmed termination
        rej = e6.submit(S.stop_cmd(), 3)
        self.assertEqual((rej.admission.accepted, rej.admission.code), (False, "BACKEND_UNAVAILABLE"))
        self.assertEqual(e6.commands(), [])


if __name__ == "__main__":
    unittest.main()
