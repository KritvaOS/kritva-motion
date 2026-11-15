"""The runtime driver (KOS-MOTION-004 PR-04): capability check before dispatch (CT-BE-02), backend reports that
drive the lifecycle (CT-BE-04) and termination semantics (CT-BE-07), plus the failure paths of the port.

The three CT-BE methods are the single executable tests named by the IN_SCOPE manifest entries. Every test
drives the real engine, stores and driver with the scripted S1 simulator on the injected clock; nothing of ours
is mocked. Software evidence only: a simulated backend says nothing about an actuator (contract 17.7)."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime_support as T  # noqa: E402
from runtime_support import A, J1, JP, S, build, joint_script, kinds, view  # noqa: E402
from kritva_motion.backend import DispatchAnswer, Report  # noqa: E402
from kritva_motion.runtime import Driver, DriverError  # noqa: E402


def submit(d, cmd, t=10, **kw):
    r = d.submit(A, cmd, t, f"2026-11-15T00:00:{t:02d}Z", **kw)
    assert r.admission.accepted, r.admission
    return r.command_id


class TestCapabilityCheckBeforeDispatch(unittest.TestCase):
    def test_CT_BE_02(self):
        """17.3: Motion never dispatches an operation the backend does not declare. The declaration is read again
        at the moment of sending, so a declaration that changed after admission is honoured: nothing reaches the
        backend and the command ends FAILED(BACKEND_REJECTED_DISPATCH) naming the capability (I-41)."""
        cases = {
            "supported_modes": (lambda d: d["capabilities"].update(supported_modes=["position"]),
                                S.vel_cmd(0.1), "capabilities.supported_modes"),
            "supported_joint_types": (lambda d: d["capabilities"].update(supported_joint_types=["prismatic"]),
                                      S.vel_cmd(0.1), "capabilities.supported_joint_types"),
            "supported_target_types": (lambda d: d.update(supported_target_types=["axis"]),
                                       S.vel_cmd(0.1), "supported_target_types"),
            "position_hold": (lambda d: d["capabilities"].update(position_hold=False),
                              S.hold_cmd(), "capabilities.position_hold"),
        }
        for name, (mutate, cmd, capability) in cases.items():
            with self.subTest(capability=name):
                e, co, pub, sink, sim, _ = build()
                drift = T.Drifting(sim, mutate, good=1)
                d = Driver(e, co, drift)
                drift._calls = 0                         # the next describe_capabilities call is the admission read
                cid = submit(d, cmd)
                state, phase, reason = view(e, cid)
                self.assertEqual((state, reason), ("FAILED", "BACKEND_REJECTED_DISPATCH"))
                self.assertIn(capability, e.command(cid)["detail"])
                self.assertEqual(drift.received, [], "the refused operation never reached the backend")
                self.assertEqual(sim.poll(10_000), [], "and the backend produced nothing for it")
                self.assertEqual([x["input"] for x in d.log if "capability" in x["reason"]], ["request_hold" if name == "position_hold" else "dispatch"])
                # the record is public: history and events carry the failure
                self.assertIn(("COMMAND_STATE_CHANGED", cid), kinds(sink, "command"))
                self.assertEqual(co.command_status(cid)["reason_code"], "BACKEND_REJECTED_DISPATCH")

    def test_a_declared_operation_is_sent(self):
        e, co, pub, sink, sim, d = build()
        cid = submit(d, S.vel_cmd(0.1))
        self.assertEqual(view(e, cid), ("ACCEPTED", "DISPATCH_PENDING", None))
        self.assertEqual([t["op"] for t in d.trace if t["direction"] == "to_backend"], ["dispatch"])

    def test_concurrency_is_checked_against_the_declared_limit(self):
        e, co, pub, sink, sim, d = build(decl=T.declaration(max_concurrent_executions=1))
        first = submit(d, S.vel_cmd(0.1), 10)
        second = d.submit(A, S.vel_cmd(0.1, jid=JP, unit="m/s", client_request_id="req-2") if False else
                          S.env("SET_VELOCITY", JP, parameters={"target_velocity": 0.05, "unit": "m/s"}, client_request_id="req-2"),
                          11, "2026-11-15T00:00:11Z")
        self.assertTrue(second.admission.accepted, second.admission)
        self.assertEqual(view(e, first)[0], "ACCEPTED")
        self.assertEqual(view(e, second.command_id)[0::2], ("FAILED", "BACKEND_REJECTED_DISPATCH"))
        self.assertIn("max_concurrent_executions", e.command(second.command_id)["detail"])

    def test_a_cancel_without_the_declared_capability_sends_nothing_and_the_bound_decides(self):
        e, co, pub, sink, sim, _ = build()
        drift = T.Drifting(sim, lambda d: d["capabilities"].update(execution_cancellation=False), good=3)
        d = Driver(e, co, drift)
        cid = submit(d, S.vel_cmd(0.1))
        d.poll(15)
        self.assertEqual(view(e, cid)[0], "RUNNING")
        drift._calls = 3                                  # every later declaration lacks the capability
        d.terminate(cid, "CANCEL_REQUESTED", 20)
        self.assertNotIn("request_termination", drift.received)
        self.assertEqual(view(e, cid)[:2], ("RUNNING", "TERMINATING"))
        d.poll(1020)
        self.assertEqual(view(e, cid)[0::2], ("FAILED", "TERMINATION_UNCONFIRMED"))

    def test_a_stop_without_controlled_stop_is_refused(self):
        e, co, pub, sink, sim, _ = build()
        drift = T.Drifting(sim, lambda d: d["capabilities"].update(controlled_stop=False), good=1)
        d = Driver(e, co, drift)
        drift._calls = 0
        # the STOP is admitted from the first declaration read, and refused at the second (declaration changed)
        stop = d.submit(A, S.stop_cmd(client_request_id="req-s"), 10, "2026-11-15T00:00:10Z")
        self.assertTrue(stop.admission.accepted, stop.admission)
        self.assertEqual(view(e, stop.command_id)[0::2], ("FAILED", "BACKEND_REJECTED_DISPATCH"))
        self.assertNotIn("request_termination", drift.received)


class TestReportsDriveTheLifecycle(unittest.TestCase):
    def test_CT_BE_04(self):
        """17.4 and 17.5: every report kind a backend produces reaches the engine through the driver and drives the
        lifecycle as specified, in the order the backend produced them, each applied once."""
        with self.subTest(report="execution_started"):
            e, co, pub, sink, sim, d = build()
            cid = submit(d, S.vel_cmd(0.1))
            d.poll(14)
            self.assertEqual(view(e, cid)[0], "ACCEPTED")           # request accepted is not a start
            d.poll(15)
            self.assertEqual(view(e, cid), ("RUNNING", "NONE", None))
            d.poll(16)
            self.assertEqual(sum(1 for t in e.command(cid)["transitions"] if t["to"] == "RUNNING"), 1, "applied once")

        with self.subTest(report="execution_rejected after an accepted dispatch"):
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(
                dispatch={"answer": "accept", "start": {"reject": "SERVO_OFF", "after_ms": 3}})}})
            cid = submit(d, S.vel_cmd(0.1))
            d.poll(13)
            self.assertEqual(view(e, cid)[0::2], ("FAILED", "BACKEND_REJECTED_DISPATCH"))
            self.assertEqual(e.command(cid)["detail"], "BACKEND_REFUSED")          # the backend's words stay in the log
            self.assertTrue(any("SERVO_OFF" in x["reason"] for x in d.log))

        with self.subTest(report="execution_rejected as the answer to dispatch"):
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(
                dispatch={"answer": "reject", "reason": "JOINT_BUSY"})}})
            cid = submit(d, S.vel_cmd(0.1))
            self.assertEqual(view(e, cid)[0::2], ("FAILED", "BACKEND_REJECTED_DISPATCH"))
            self.assertEqual(e.command(cid)["detail"], "BACKEND_REFUSED")
            self.assertTrue(any("JOINT_BUSY" in x["reason"] for x in d.log))

        with self.subTest(report="feedback completes a position command from valid fresh samples"):
            fb = [{"at_ms": t, "position": 0.5, "velocity": 0.0, "validity": "VALID"} for t in (20, 60, 100, 140)]
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(feedback=fb)}})
            cid = submit(d, S.pos_cmd(0.5))
            for t in (15, 20, 60, 100, 140, 150):
                d.poll(t)
            self.assertEqual(view(e, cid)[0], "COMPLETED")
            self.assertEqual(e.feedback_record(J1)["measured_position"], 0.5)

        with self.subTest(report="feedback marked invalid does not complete"):
            fb = [{"at_ms": t, "position": None, "validity": "INVALID"} for t in (20, 60, 100, 140)]
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(feedback=fb)}})
            cid = submit(d, S.pos_cmd(0.5))
            for t in (15, 20, 60, 100, 140, 150):
                d.poll(t)
            self.assertEqual(view(e, cid)[0], "RUNNING")
            self.assertEqual(e.joint_state(J1, 150)["feedback_status"], "INVALID")

        with self.subTest(report="health"):
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script()},
                                              "events": [{"at_ms": 20, "kind": "health", "health": "DEGRADED"}]})
            d.poll(20)
            snap = e.joint_state(J1, 20)
            self.assertEqual((snap["backend_status"], snap["health_state"]), ("DEGRADED", "DEGRADED"))
            self.assertIn(("BACKEND_HEALTH_CHANGED", "backend"), kinds(sink, "backend"))

        with self.subTest(report="fault and fault_cleared"):
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script()}, "events": [
                {"at_ms": 20, "kind": "fault", "code": "BACKEND_COMMUNICATION_LOSS", "joints": [J1]},
                {"at_ms": 30, "kind": "fault_cleared", "code": "BACKEND_COMMUNICATION_LOSS"}]})
            cid = submit(d, S.vel_cmd(0.1))
            d.poll(15)
            d.poll(20)
            self.assertEqual([f["code"] for f in e.faults(J1)], ["BACKEND_COMMUNICATION_LOSS"])
            self.assertIn(("BACKEND_FAULT_RAISED", "backend"), kinds(sink, "backend"))
            d.poll(30)
            self.assertIn(("BACKEND_FAULT_CLEARED", "backend"), kinds(sink, "backend"))
            self.assertEqual(e.faults(J1)[0]["state"], "ACTIVE", "a backend report does not clear a joint fault record")

        with self.subTest(report="hold_confirmed"):
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(
                hold={"answer": "accept", "start": {"after_ms": 2}, "confirm": {"after_ms": 5}})}})
            cid = submit(d, S.hold_cmd())
            d.poll(12)
            self.assertEqual(view(e, cid)[0], "RUNNING")
            d.poll(15)
            self.assertEqual(view(e, cid)[0::2], ("COMPLETED", "HOLD_ENGAGED"))
            self.assertEqual(e.joint_state(J1, 15)["control_state"], "HOLDING")

        with self.subTest(report="hold_released and hold_release_failed"):
            for release, expected in (({"answer": "accept", "confirm": {"after_ms": 2}}, ("RUNNING", None)),
                                      ({"answer": "accept", "confirm": {"after_ms": 2, "fail": True, "reason": "STUCK"}},
                                       ("FAILED", "BACKEND_REJECTED_DISPATCH"))):
                e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(
                    hold={"answer": "accept", "start": {"after_ms": 1}, "confirm": {"after_ms": 2}, "release": release})}})
                h = submit(d, S.hold_cmd(), 10)
                d.poll(12)
                self.assertEqual(e.joint_state(J1, 12)["control_state"], "HOLDING")
                mv = d.submit(A, S.vel_cmd(0.1, client_request_id="req-2"), 20, "2026-11-15T00:00:20Z")
                self.assertTrue(mv.admission.accepted, mv.admission)
                d.poll(25)                                  # start -> the engine asks to release the hold
                self.assertEqual([t["op"] for t in d.trace if t["direction"] == "to_backend"][-1], "release_hold")
                d.poll(27)
                self.assertEqual((view(e, mv.command_id)[0], view(e, mv.command_id)[2]), expected)

        with self.subTest(report="termination_confirmed"):
            e, co, pub, sink, sim, d = build()
            cid = submit(d, S.vel_cmd(0.1))
            d.poll(15)
            d.terminate(cid, "CANCEL_REQUESTED", 20)
            d.poll(50)
            self.assertEqual(view(e, cid)[0::2], ("CANCELLED", "CANCEL_REQUESTED"))

        with self.subTest(report="malformed report is ignored and logged"):
            e, co, pub, sink, sim, d = build()
            cid = submit(d, S.vel_cmd(0.1))
            d.poll(15)
            sim_poll = sim.poll
            sim.poll = lambda now: [Report(kind="execution_started")]      # no backend_reference
            d.poll(16)
            sim.poll = sim_poll
            self.assertTrue(any("malformed" in x["reason"] for x in d.log))
            self.assertEqual(view(e, cid)[0], "RUNNING")


class TestTerminationSemantics(unittest.TestCase):
    def running(self, script):
        e, co, pub, sink, sim, d = build({"joints": {J1: script}})
        cid = submit(d, S.vel_cmd(0.1))
        d.poll(15)
        self.assertEqual(view(e, cid)[0], "RUNNING")
        return e, co, pub, sink, sim, d, cid

    def test_CT_BE_07(self):
        """17.5: a termination request that the backend accepted is not a confirmation; a confirmation is bound to the
        backend reference and the target; a partial or unknown outcome is no confirmation and the bound decides:
        TERMINATION_UNCONFIRMED, decided by Motion, with the joint FAULTED and its control state UNKNOWN."""
        with self.subTest(case="accepted is not confirmed"):
            e, co, pub, sink, sim, d, cid = self.running(joint_script(termination={"answer": "accept", "confirm": None}))
            d.terminate(cid, "CANCEL_REQUESTED", 20)
            d.poll(500)
            c = e.command(cid)
            self.assertEqual((c["state"], c["phase"]), ("RUNNING", "TERMINATING"))
            self.assertEqual((c["termination"]["outcome"], c["termination"]["backend_accepted_ms"]), ("PENDING", 20))
            self.assertNotEqual(e.joint_state(J1, 500)["control_state"], "IDLE")

        with self.subTest(case="no confirmation within the bound is unconfirmed, decided by Motion"):
            e, co, pub, sink, sim, d, cid = self.running(joint_script(termination={"answer": "accept", "confirm": None}))
            d.terminate(cid, "CANCEL_REQUESTED", 20)
            d.poll(1019)
            self.assertEqual(view(e, cid)[0], "RUNNING")
            d.poll(1020)
            self.assertEqual(view(e, cid)[0::2], ("FAILED", "TERMINATION_UNCONFIRMED"))
            snap = e.joint_state(J1, 1020)
            self.assertEqual((snap["control_state"], snap["health_state"]), ("UNKNOWN", "FAULTED"))
            self.assertEqual(e.faults(J1)[-1]["code"], "TERMINATION_UNCONFIRMED")

        with self.subTest(case="confirmation for another reference is ignored and recorded"):
            e, co, pub, sink, sim, d, cid = self.running(joint_script(
                termination={"answer": "accept", "confirm": {"after_ms": 5, "reference": "ref-other"}}))
            d.terminate(cid, "CANCEL_REQUESTED", 20)
            d.poll(25)
            self.assertEqual(view(e, cid)[:2], ("RUNNING", "TERMINATING"))
            self.assertIn({"input": "termination_confirmed", "backend_reference": "ref-other",
                           "reason": "unknown_reference", "monotonic_ms": 25}, d.log)
            d.poll(1020)
            self.assertEqual(view(e, cid)[0::2], ("FAILED", "TERMINATION_UNCONFIRMED"))

        with self.subTest(case="confirmation for another target is ignored and recorded"):
            e, co, pub, sink, sim, d, cid = self.running(joint_script(
                termination={"answer": "accept", "confirm": {"after_ms": 5, "target": JP}}))
            d.terminate(cid, "CANCEL_REQUESTED", 20)
            d.poll(25)
            self.assertEqual(view(e, cid)[:2], ("RUNNING", "TERMINATING"))
            self.assertTrue(any(x["reason"] == "target_mismatch" for x in d.log))
            d.poll(1020)
            self.assertEqual(view(e, cid)[0::2], ("FAILED", "TERMINATION_UNCONFIRMED"))

        with self.subTest(case="a confirmation bound to the reference and the target ends the command"):
            e, co, pub, sink, sim, d, cid = self.running(joint_script())
            d.terminate(cid, "CANCEL_REQUESTED", 20)
            d.poll(49)
            self.assertEqual(view(e, cid)[:2], ("RUNNING", "TERMINATING"))
            d.poll(50)
            self.assertEqual(view(e, cid)[0::2], ("CANCELLED", "CANCEL_REQUESTED"))
            self.assertEqual(e.command(cid)["termination"]["outcome"], "CONFIRMED")

        with self.subTest(case="a confirmation that arrives after the bound changes nothing"):
            e, co, pub, sink, sim, d, cid = self.running(joint_script(
                termination={"answer": "accept", "confirm": {"after_ms": 1500}}))
            d.terminate(cid, "CANCEL_REQUESTED", 20)
            d.poll(1020)
            d.poll(1520)
            self.assertEqual(view(e, cid)[0::2], ("FAILED", "TERMINATION_UNCONFIRMED"))
            self.assertTrue(any(x["input"] == "termination_confirmed" and x["reason"] == "terminal" for x in e.ignored_log))

        with self.subTest(case="a start reported after termination was requested does not revive the command"):
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(
                dispatch={"answer": "accept", "start": {"after_ms": 50}},
                termination={"answer": "accept", "confirm": {"after_ms": 60}})}})
            cid = submit(d, S.vel_cmd(0.1), 10)
            d.terminate(cid, "CANCEL_REQUESTED", 20)
            d.poll(60)
            self.assertEqual(view(e, cid)[:2], ("ACCEPTED", "TERMINATING"))
            self.assertTrue(any(x["input"] == "execution_started" and x["reason"] == "terminating" for x in e.ignored_log))
            d.poll(80)
            self.assertEqual(view(e, cid)[0::2], ("CANCELLED", "CANCEL_REQUESTED"))

        with self.subTest(case="a refused STOP ends FAILED(BACKEND_REJECTED_DISPATCH)"):
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(
                termination={"answer": "refuse", "reason": "NOT_NOW"})}})
            stop = d.submit(A, S.stop_cmd(client_request_id="req-s"), 10, "2026-11-15T00:00:10Z")
            self.assertEqual(view(e, stop.command_id)[0::2], ("FAILED", "BACKEND_REJECTED_DISPATCH"))

        with self.subTest(case="a STOP with nothing running is confirmed only by a bound confirmation"):
            e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(termination={"answer": "accept", "confirm": {"after_ms": 10}})}})
            stop = d.submit(A, S.stop_cmd(client_request_id="req-s"), 10, "2026-11-15T00:00:10Z")
            self.assertTrue(stop.admission.accepted, stop.admission)
            d.poll(19)
            self.assertEqual(view(e, stop.command_id)[0], "RUNNING")
            d.poll(20)
            self.assertEqual(view(e, stop.command_id)[0::2], ("COMPLETED", "STOP_CONFIRMED"))


class TestPortFailures(unittest.TestCase):
    def test_an_exception_from_the_port_is_a_loss_of_the_backend(self):
        e, co, pub, sink, sim, _ = build()

        class Broken(T.Drifting):
            def dispatch(self, request, now_ms):
                raise RuntimeError("link down")
        d = Driver(e, co, Broken(sim, lambda x: None, good=10**6))
        cid = submit(d, S.vel_cmd(0.1))
        self.assertIn("BACKEND_COMMUNICATION_LOSS", [f["code"] for f in e.faults(J1)])
        self.assertTrue(any(x["input"] == "backend_error" for x in d.log))
        self.assertIn(("BACKEND_FAULT_RAISED", "backend"), kinds(sink, "backend"))

    def test_an_answer_of_the_wrong_shape_is_a_loss_of_the_backend(self):
        e, co, pub, sink, sim, _ = build()

        class Odd(T.Drifting):
            def dispatch(self, request, now_ms):
                return {"accepted": True}
        d = Driver(e, co, Odd(sim, lambda x: None, good=10**6))
        submit(d, S.vel_cmd(0.1))
        self.assertIn("BACKEND_COMMUNICATION_LOSS", [f["code"] for f in e.faults(J1)])

    def test_an_answer_that_does_not_echo_the_reference_is_a_loss_of_the_backend(self):
        e, co, pub, sink, sim, _ = build()

        class Wrong(T.Drifting):
            def dispatch(self, request, now_ms):
                return DispatchAnswer(True, backend_reference="somebody-else")
        d = Driver(e, co, Wrong(sim, lambda x: None, good=10**6))
        submit(d, S.vel_cmd(0.1))
        self.assertIn("BACKEND_COMMUNICATION_LOSS", [f["code"] for f in e.faults(J1)])

    def test_a_poll_that_raises_is_a_loss_of_the_backend(self):
        e, co, pub, sink, sim, _ = build()

        class Silent(T.Drifting):
            def poll(self, now_ms):
                raise OSError("gone")
        d = Driver(e, co, Silent(sim, lambda x: None, good=10**6))
        d.poll(10)
        self.assertIn("BACKEND_COMMUNICATION_LOSS", [f["code"] for f in e.faults(J1)])

    def test_a_non_conforming_backend_is_refused(self):
        e, co, pub, sink, sim, _ = build()
        with self.assertRaises(DriverError):
            Driver(e, co, object())
        with self.assertRaises(DriverError):
            Driver(e, co, T.Drifting(sim, lambda d: d.pop("clock"), good=0))


class TestAdvisoryStop(unittest.TestCase):
    """A fault on a joint that is not idle and has no command in flight asks for a stop that no command carries (I-29).
    The fixed-seed property test found that the first version of the driver took that request for a command's and
    reported a loss of the backend; this is its regression test."""

    def holding(self):
        e, co, pub, sink, sim, d = build({"joints": {J1: joint_script(
            hold={"answer": "accept", "start": {"after_ms": 1}, "confirm": {"after_ms": 2}})}})
        submit(d, S.hold_cmd(), 10)
        d.poll(12)
        self.assertEqual(e.joint_state(J1, 12)["control_state"], "HOLDING")
        return e, co, pub, sink, sim, d

    def test_the_stop_is_sent_with_a_reference_of_the_drivers_own_and_is_no_backend_loss(self):
        e, co, pub, sink, sim, d = self.holding()
        d.joint_fault(J1, "TRACKING_ERROR", 20, "2026-11-15T00:00:20Z")
        sent = [t for t in d.trace if t["direction"] == "to_backend" and t["command_id"] is None]
        self.assertEqual([(t["op"], t["backend_reference"]) for t in sent], [("request_termination", "advisory-fault-1")])
        self.assertEqual([f["code"] for f in e.faults(J1)], ["TRACKING_ERROR"])
        self.assertNotIn("BACKEND_COMMUNICATION_LOSS", [f["code"] for f in e.faults(J1)])
        self.assertFalse(any(x["input"] == "backend_error" for x in d.log))
        d.poll(60)                                               # the backend's confirmation has no command to apply to
        self.assertTrue(any(x["reason"] == "advisory_stop_report" for x in d.log))
        self.assertEqual(e.joint_state(J1, 60)["health_state"], "FAULTED")

    def test_without_the_declared_capability_nothing_is_sent(self):
        e, co, pub, sink, sim, _ = build({"joints": {J1: joint_script(
            hold={"answer": "accept", "start": {"after_ms": 1}, "confirm": {"after_ms": 2}})}})
        drift = T.Drifting(sim, lambda dd: dd["capabilities"].update(controlled_stop=False), good=10**6)
        d = Driver(e, co, drift)
        submit(d, S.hold_cmd(), 10)
        d.poll(12)
        drift._good = 0                                   # from now on the declaration lacks controlled stop
        d.joint_fault(J1, "TRACKING_ERROR", 20, "2026-11-15T00:00:20Z")
        self.assertNotIn("request_termination", drift.received)
        self.assertTrue(any(x["input"] == "advisory_stop" and "controlled_stop" in x["reason"] for x in d.log))


class TestDriverProperties(unittest.TestCase):
    def run_once(self):
        e, co, pub, sink, sim, d = build()
        cid = submit(d, S.vel_cmd(0.1))
        for t in (15, 20):
            d.poll(t)
        d.terminate(cid, "CANCEL_REQUESTED", 21)
        d.poll(60)
        return [(ev["event_id"], ev["event_type"], ev["data"]) for ev in sink.events], d.trace, d.log

    def test_same_script_and_clock_give_the_same_trace(self):
        self.assertEqual(self.run_once(), self.run_once())

    def test_the_driver_changes_nothing_without_a_report_a_command_or_a_timer(self):
        e, co, pub, sink, sim, d = build()
        cid = submit(d, S.vel_cmd(0.1))
        before = copy.deepcopy(e.command(cid))
        d.poll(11)
        d.poll(12)
        self.assertEqual(e.command(cid), before)

    def test_every_result_reaches_the_history_and_the_events(self):
        e, co, pub, sink, sim, d = build()
        cid = submit(d, S.vel_cmd(0.1))
        d.poll(15)
        d.terminate(cid, "CANCEL_REQUESTED", 20)
        d.poll(50)
        states = [ev["data"]["to"] for ev in sink.events if ev["event_type"] == "COMMAND_STATE_CHANGED"
                  and ev["stream"]["id"] == cid]
        self.assertEqual(states, ["ACCEPTED", "RUNNING", "CANCELLED"])
        self.assertEqual([x["state"] for x in co._history.get(cid)["lifecycle_history"]][-1], "CANCELLED")

    def test_the_simulated_marker_reaches_the_trace(self):
        e, co, pub, sink, sim, d = build()
        submit(d, S.vel_cmd(0.1))
        d.poll(15)
        self.assertTrue(all(t["simulated"] for t in d.trace if t["direction"] == "from_backend"))


if __name__ == "__main__":
    unittest.main()
