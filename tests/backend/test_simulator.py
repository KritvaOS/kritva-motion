"""The scripted S1 simulator (KOS-MOTION-004 PR-03): script validation, determinism, every scripted outcome of
contract 17.4/17.5, the simulated marker (17.7) and CT-BE-01 (17.2 capability declaration)."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from kritva_motion.backend import is_backend, validate_declaration            # noqa: E402
from kritva_motion.backend.reports import BACKEND_FAULT_CODES  # noqa: E402
from kritva_motion.backend.simulator import ClockError, ScriptError, Simulator, default_declaration  # noqa: E402

CAPS = ("supported_target_types", "health", "capabilities", "joint_limits", "clock")


def req(ref="r1", joint="j1", op="SET_POSITION"):
    return {"backend_reference": ref, "operation": op, "target": {"type": "joint", "id": joint}}


def script(**joint):
    return {"joints": {"j1": joint}}


FULL = dict(dispatch={"answer": "accept", "start": {"after_ms": 20}},
            termination={"answer": "accept", "confirm": {"after_ms": 30}},
            hold={"answer": "accept", "confirm": {"after_ms": 5},
                  "release": {"answer": "accept", "confirm": {"after_ms": 7}}},
            feedback=[{"at_ms": 10, "position": 0.1, "velocity": 0.0, "validity": "VALID"},
                      {"at_ms": 30, "position": None, "validity": "INVALID"}])


class TestScriptValidation(unittest.TestCase):
    def bad(self, s, decl=None, text=""):
        with self.assertRaises(ScriptError) as cm:
            Simulator(s, decl)
        self.assertIn(text, str(cm.exception))

    def test_a_full_script_is_accepted(self):
        self.assertTrue(is_backend(Simulator({"joints": {"j1": FULL}, "events": [{"at_ms": 1, "kind": "health", "health": "DEGRADED"}]})))

    def test_unknown_keys_and_types(self):
        self.bad({"joints": {"j1": {}}, "x": 1}, text="only `joints` and `events`")
        self.bad({"joints": {"j1": {"bogus": 1}}}, text="only")
        self.bad({"joints": {"j1": {"dispatch": {"answer": "maybe"}}}}, text="answer")
        self.bad({"joints": []}, default_declaration(["j1"]), "must be an object")

    def test_reasons_and_delays(self):
        self.bad(script(dispatch={"answer": "reject"}), text="reason")
        self.bad(script(dispatch={"answer": "accept", "start": {"after_ms": -1}}), text="after_ms")
        self.bad(script(dispatch={"answer": "accept", "start": {"after_ms": float("nan")}}), text="after_ms")
        self.bad(script(dispatch={"answer": "reject", "reason": "X", "start": {"after_ms": 1}}), text="rejected dispatch")

    def test_unknown_joint(self):
        decl = default_declaration(["j1"])
        self.bad({"joints": {"j9": {}}}, decl, "not a joint")

    def test_unordered_samples_and_events(self):
        smp = [{"at_ms": 5, "position": 0, "validity": "VALID"}, {"at_ms": 4, "position": 0, "validity": "VALID"}]
        self.bad(script(feedback=smp), text="before the previous sample")
        ev = [{"at_ms": 5, "kind": "health", "health": "AVAILABLE"}, {"at_ms": 4, "kind": "health", "health": "AVAILABLE"}]
        self.bad({"joints": {"j1": {}}, "events": ev}, text="before the previous event")

    def test_script_inconsistent_with_the_declaration(self):
        d = default_declaration(["j1"])
        d["capabilities"]["position_hold"] = False
        self.bad(script(hold={"answer": "accept"}), d, "no position hold")
        d = default_declaration(["j1"])
        d["capabilities"]["controlled_stop"] = False
        self.bad(script(termination={"answer": "accept"}), d, "no controlled stop")
        d = default_declaration(["j1"])
        d["capabilities"]["feedback"]["velocity"] = False
        self.bad(script(feedback=[{"at_ms": 1, "position": 0, "velocity": 1, "validity": "VALID"}]), d, "no velocity feedback")

    def test_a_valid_sample_needs_a_position(self):
        self.bad(script(feedback=[{"at_ms": 1, "validity": "VALID"}]), text="position")

    def test_a_non_conforming_declaration_is_refused(self):
        d = default_declaration(["j1"])
        del d["clock"]
        self.bad(script(), d, "declaration.")

    def test_the_script_is_copied(self):
        s = script(dispatch={"answer": "accept"})
        sim = Simulator(s)
        s["joints"]["j1"]["dispatch"] = {"answer": "reject", "reason": "X"}
        self.assertTrue(sim.dispatch(req(), 0).accepted)


class TestOutcomes(unittest.TestCase):
    def sim(self, **joint):
        return Simulator(script(**joint))

    def test_dispatch_accept_start_and_reference_echo(self):
        s = self.sim(**FULL)
        a = s.dispatch(req("ref-9"), 100)
        self.assertEqual((a.accepted, a.backend_reference, a.simulated), (True, "ref-9", True))
        r = s.poll(120)
        self.assertEqual([(x.kind, x.backend_reference, x.simulated) for x in r if x.kind == "execution_started"],
                         [("execution_started", "ref-9", True)])

    def test_request_accepted_is_not_a_start(self):
        s = self.sim(dispatch={"answer": "accept", "start": None})
        self.assertTrue(s.dispatch(req(), 0).accepted)
        self.assertEqual(s.poll(10_000), [])

    def test_dispatch_rejected_answer(self):
        s = self.sim(dispatch={"answer": "reject", "reason": "JOINT_FAULT"})
        a = s.dispatch(req(), 0)
        self.assertEqual((a.accepted, a.reason, a.simulated), (False, "JOINT_FAULT", True))
        self.assertEqual(s.poll(100), [])

    def test_rejected_after_accept(self):
        s = self.sim(dispatch={"answer": "accept", "start": {"reject": "LATE_REFUSAL", "after_ms": 3}})
        s.dispatch(req(), 0)
        (r,) = s.poll(3)
        self.assertEqual((r.kind, r.reason), ("execution_rejected", "LATE_REFUSAL"))

    def test_not_scripted_and_unknown_operation(self):
        s = self.sim(dispatch={"answer": "accept"})
        self.assertEqual(s.dispatch(req(joint="j2"), 0).reason, "NOT_SCRIPTED")
        self.assertEqual(s.dispatch(req(op="TELEPORT"), 0).reason, "UNSUPPORTED_OPERATION")
        self.assertEqual(s.request_termination("nope", "x", 0).reason, "UNKNOWN_REFERENCE")

    def test_malformed_and_duplicate(self):
        s = self.sim(dispatch={"answer": "accept"})
        self.assertEqual(s.dispatch({}, 0).reason, "MALFORMED_REQUEST")
        self.assertTrue(s.dispatch(req("a"), 0).accepted)
        self.assertEqual(s.dispatch(req("a"), 0).reason, "DUPLICATE_REFERENCE")

    def test_busy_at_the_declared_concurrency(self):
        d = default_declaration(["j1"])
        d["capabilities"]["max_concurrent_executions"] = 1
        s = Simulator(script(dispatch={"answer": "accept"}), d)
        self.assertTrue(s.dispatch(req("a"), 0).accepted)
        self.assertEqual(s.dispatch(req("b"), 0).reason, "BACKEND_BUSY")

    def test_unavailable_backend_rejects(self):
        s = Simulator({"joints": {"j1": {"dispatch": {"answer": "accept"}}},
                       "events": [{"at_ms": 5, "kind": "health", "health": "UNAVAILABLE"}]})
        s.poll(5)
        self.assertEqual(s.dispatch(req(), 6).reason, "BACKEND_UNAVAILABLE")

    def test_termination_confirmation_is_a_separate_report(self):
        s = self.sim(**FULL)
        s.dispatch(req(), 0)
        ans = s.request_termination("r1", "STOP", 50)
        self.assertEqual((ans.accepted, ans.simulated), (True, True))
        self.assertEqual([r.kind for r in s.poll(79)], ["feedback", "execution_started", "feedback"])
        (c,) = s.poll(80)
        self.assertEqual((c.kind, c.backend_reference, c.target), ("termination_confirmed", "r1", {"type": "joint", "id": "j1"}))

    def test_termination_never_confirmed_and_refused(self):
        s = self.sim(dispatch={"answer": "accept"}, termination={"answer": "accept", "confirm": None})
        s.dispatch(req(), 0)
        self.assertTrue(s.request_termination("r1", "x", 1).accepted)
        self.assertEqual(s.poll(10_000), [])
        s = self.sim(dispatch={"answer": "accept"}, termination={"answer": "refuse", "reason": "CANNOT_STOP"})
        s.dispatch(req(), 0)
        a = s.request_termination("r1", "x", 1)
        self.assertEqual((a.accepted, a.reason), (False, "CANNOT_STOP"))

    def test_confirmation_for_another_reference_or_target(self):
        s = self.sim(dispatch={"answer": "accept"},
                     termination={"answer": "accept", "confirm": {"after_ms": 1, "reference": "other"}})
        s.dispatch(req(), 0)
        s.request_termination("r1", "x", 0)
        (c,) = s.poll(1)
        self.assertEqual(c.backend_reference, "other")
        s = self.sim(dispatch={"answer": "accept"},
                     termination={"answer": "accept", "confirm": {"after_ms": 1, "target": "j2"}})
        s.dispatch(req(), 0)
        s.request_termination("r1", "x", 0)
        (c,) = s.poll(1)
        self.assertEqual(c.target, {"type": "joint", "id": "j2"})

    def test_hold_and_release(self):
        s = self.sim(**FULL)
        a = s.request_hold("h1", "j1", 0)
        self.assertEqual((a.accepted, a.simulated), (True, True))
        self.assertIn("hold_confirmed", [r.kind for r in s.poll(5)])
        self.assertTrue(s.release_hold("h1", "j1", 10).accepted)
        self.assertEqual([r.kind for r in s.poll(17) if r.kind.startswith("hold")], ["hold_released"])

    def test_release_failure_and_unknown_release(self):
        s = self.sim(hold={"answer": "accept", "release": {"answer": "accept", "confirm": {"after_ms": 1, "fail": True, "reason": "STUCK"}}})
        s.request_hold("h1", "j1", 0)
        s.release_hold("h1", "j1", 0)
        (r,) = s.poll(1)
        self.assertEqual((r.kind, r.reason), ("hold_release_failed", "STUCK"))
        self.assertEqual(s.release_hold("zzz", "j1", 2).reason, "UNKNOWN_REFERENCE")

    def test_feedback_samples_are_reported_once_in_order(self):
        s = self.sim(**FULL)
        rs = s.poll(30)
        fb = [r for r in rs if r.kind == "feedback"]
        self.assertEqual([r.record["backend_timestamp"] for r in fb], [10, 30])
        self.assertEqual(fb[0].record["measured_position"], 0.1)
        self.assertEqual(fb[0].record["clock_domain"], "simulated-monotonic")
        self.assertIsNone(fb[1].record["measured_position"])
        self.assertEqual(s.poll(30), [])

    def test_events_health_fault_cleared(self):
        code = sorted(BACKEND_FAULT_CODES)[0]
        s = Simulator({"joints": {"j1": {}}, "events": [
            {"at_ms": 1, "kind": "health", "health": "DEGRADED"},
            {"at_ms": 2, "kind": "fault", "code": code, "joints": ["j1"]},
            {"at_ms": 3, "kind": "fault_cleared"}]})
        self.assertEqual(s.health()["health"], "AVAILABLE")
        self.assertEqual([r.kind for r in s.poll(3)], ["health", "fault", "fault_cleared"])
        h = s.health()
        self.assertEqual((h["health"], h["faults"], h["simulated"]), ("DEGRADED", [], True))

    def test_time_must_not_go_backwards_and_must_be_finite(self):
        s = self.sim(dispatch={"answer": "accept"})
        s.poll(10)
        with self.assertRaises(ClockError):
            s.poll(9)
        with self.assertRaises(ClockError):
            s.dispatch(req(), 5)
        with self.assertRaises(ClockError):
            s.poll(float("inf"))
        with self.assertRaises(ClockError):
            s.poll(True)


class TestDeterminismAndSimulatedMarker(unittest.TestCase):
    def run_once(self):
        s = Simulator({"joints": {"j1": FULL}, "events": [{"at_ms": 40, "kind": "health", "health": "DEGRADED"}]})
        out = [s.dispatch(req(), 0), s.poll(25), s.request_hold("h", "j1", 26), s.poll(40),
               s.request_termination("r1", "STOP", 41), s.poll(100), s.health(), s.describe_capabilities()]
        return repr(out)

    def test_same_script_same_calls_same_output(self):
        self.assertEqual(self.run_once(), self.run_once())

    def test_every_output_is_marked_simulated(self):
        s = Simulator({"joints": {"j1": FULL}})
        outs = [s.dispatch(req(), 0), s.request_termination("r1", "x", 1), s.request_hold("h", "j1", 2),
                s.release_hold("h", "j1", 3), s.dispatch(req("z", "j2"), 4)]
        outs += s.poll(1000)
        self.assertTrue(outs and all(o.simulated is True for o in outs))
        self.assertIs(s.describe_capabilities()["simulated"], True)
        self.assertIs(s.health()["simulated"], True)

    def test_the_declaration_is_not_shared(self):
        s = Simulator({"joints": {"j1": {}}})
        d = s.describe_capabilities()
        d["capabilities"]["controlled_stop"] = False
        self.assertTrue(s.describe_capabilities()["capabilities"]["controlled_stop"])


class TestConformanceIds(unittest.TestCase):
    def test_CT_BE_01(self):
        """17.2: a backend declares its target types, joint types, modes, controlled stop, position hold,
        execution cancellation, feedback, feedback rate, joint limits, concurrency, health and clock. Leaving
        any one out makes the declaration non-conforming."""
        d = Simulator({"joints": {"j1": {}, "j2": {}}}).describe_capabilities()
        self.assertEqual(validate_declaration(d), [])
        c = d["capabilities"]
        declared = [d["supported_target_types"], c["supported_joint_types"], c["supported_modes"], c["controlled_stop"],
                    c["position_hold"], c["execution_cancellation"], c["feedback"], c["feedback_rate_hz"],
                    d["joint_limits"], c["max_concurrent_executions"], d["health"], d["clock"]]
        self.assertEqual(len(declared), 12)
        self.assertTrue(all(x is not None for x in declared))
        self.assertEqual(set(d["joint_limits"]), {"j1", "j2"})
        omissions = [("supported_target_types",), ("health",), ("joint_limits",), ("clock",),
                     ("capabilities", "supported_joint_types"), ("capabilities", "supported_modes"),
                     ("capabilities", "controlled_stop"), ("capabilities", "position_hold"),
                     ("capabilities", "execution_cancellation"), ("capabilities", "feedback"),
                     ("capabilities", "feedback_rate_hz"), ("capabilities", "max_concurrent_executions")]
        for path in omissions:
            bad = copy.deepcopy(d)
            node = bad
            for k in path[:-1]:
                node = node[k]
            del node[path[-1]]
            self.assertNotEqual(validate_declaration(bad), [], f"omitting {'.'.join(path)} must fail")
        self.assertTrue(is_backend(Simulator({"joints": {"j1": {}}})))


if __name__ == "__main__":
    unittest.main()
