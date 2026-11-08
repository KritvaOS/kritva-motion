"""Behaviour tests of the lifecycle engine beyond the conformance mapping (KOS-MOTION-003, PR-02).

Deterministic and offline. Software evidence only, never physical or safety validation."""
import ast
import unittest
from pathlib import Path

import lifecycle_support as S
from kritva_motion.lifecycle import ClockError, IllegalTransition, LifecycleEngine, model

ENGINE_DIR = Path(__file__).resolve().parents[2] / "src" / "kritva_motion" / "lifecycle"


class TestAdmissionReuse(unittest.TestCase):
    def test_unknown_joint_state_is_rejected_without_a_command(self):
        e = S.engine()
        r = e.submit(S.pos_cmd(), 0)
        self.assertFalse(r.admission.accepted)
        self.assertEqual(r.admission.code, "TARGET_STATE_UNKNOWN")
        self.assertIsNone(r.command_id)
        self.assertEqual(e.commands(), [])
        self.assertEqual(r.requests, [])

    def test_second_command_on_busy_joint_is_rejected(self):
        e = S.engine()
        S.ready(e)
        first = e.submit(S.pos_cmd(0.5), 1)
        self.assertTrue(first.admission.accepted)
        second = e.submit(S.pos_cmd(0.6), 2)
        self.assertEqual(second.admission.code, "TARGET_BUSY")
        self.assertEqual(second.admission.conflict["command_id"], first.command_id)
        self.assertEqual(len(e.commands()), 1)

    def test_accepted_command_shape(self):
        e = S.engine()
        S.ready(e)
        r = e.submit(S.pos_cmd(0.5), 1, utc="2026-11-08T00:00:01Z")
        c = e.command(r.command_id)
        self.assertEqual((c["state"], c["phase"], c["reason_code"]), ("ACCEPTED", "DISPATCH_PENDING", None))
        self.assertEqual(len(r.requests), 1)
        req = r.requests[0]
        self.assertEqual(req["op"], "dispatch")
        self.assertEqual(req["config_digest"], "digest-1")
        self.assertEqual(req["config_version"], c["config_version"])
        self.assertEqual(req["backend_reference"], c["backend_reference"])
        self.assertEqual(c["transitions"][0]["to"], "ACCEPTED")

    def test_effective_deadline_and_timeout_come_from_defaults(self):
        cfg = S.config(default_deadline_ms=700, default_execution_timeout_ms=900)
        e = S.engine(cfg)
        S.ready(e)
        r = e.submit(S.pos_cmd(), 1)
        c = e.command(r.command_id)
        self.assertEqual((c["deadline_ms"], c["execution_timeout_ms"]), (700, 900))


class TestClock(unittest.TestCase):
    def test_bad_readings_raise(self):
        e = S.engine()
        for bad in (float("nan"), float("inf"), True, "1", None):
            with self.subTest(bad=bad):
                with self.assertRaises(ClockError):
                    e.tick(bad)

    def test_backwards_reading_raises_and_changes_nothing(self):
        e = S.engine()
        S.ready(e, t=100)
        with self.assertRaises(ClockError):
            e.tick(99)
        with self.assertRaises(ClockError):
            e.joint_state("joint-1", 50)
        self.assertEqual(e.joint_state("joint-1", 100)["control_state"], "IDLE")

    def test_equal_reading_is_allowed(self):
        e = S.engine()
        e.tick(5)
        e.tick(5)


class TestLaterOperations(unittest.TestCase):
    def test_later_operations_raise_before_any_change(self):
        for op in ("STOP", "HOLD", "CANCEL", "CLEAR_FAULT"):
            with self.subTest(op=op):
                e = S.engine()
                S.ready(e)
                before = (e.commands(), e.joint_state("joint-1", 1), list(e.ignored_log))
                with self.assertRaises(NotImplementedError):
                    e.submit(S.env(op, "joint-1"), 1)
                self.assertEqual(before, (e.commands(), e.joint_state("joint-1", 1), list(e.ignored_log)))


class TestPhasesAndStart(unittest.TestCase):
    def test_start_moves_to_running_with_phase_none(self):
        e = S.engine()
        S.ready(e)
        cid, _ = S.submit_start(e, S.pos_cmd(), 1, 2)
        c = e.command(cid)
        self.assertEqual((c["state"], c["phase"]), ("RUNNING", "NONE"))
        self.assertEqual(e.joint_state("joint-1", 2)["control_state"], "ACTIVE")
        self.assertEqual(e.joint_state("joint-1", 2)["active_command_id"], cid)

    def test_start_inputs_that_are_ignored(self):
        e = S.engine()
        S.ready(e)
        r = e.submit(S.pos_cmd(), 1)
        cid, ref = r.command_id, e.command(r.command_id)["backend_reference"]
        self.assertEqual(e.execution_started("nope", ref, 2).ignored[0]["reason"], "unknown_command")
        self.assertEqual(e.execution_started(cid, "wrong", 2).ignored[0]["reason"], "reference_mismatch")
        self.assertEqual(e.command(cid)["state"], "ACCEPTED")
        e.execution_started(cid, ref, 3)
        self.assertEqual(e.execution_started(cid, ref, 4).ignored[0]["reason"], "duplicate")
        self.assertEqual(len(e.ignored_log), 3)

    def test_state_changes_emit_events(self):
        e = S.engine()
        S.ready(e)
        r = e.submit(S.pos_cmd(), 1)
        kinds = [ev["event_type"] if "event_type" in ev else ev.get("type") for ev in r.events]
        self.assertTrue(r.events)
        self.assertEqual(len(kinds), len(r.events))


class TestCompletion(unittest.TestCase):
    def _running(self, cfg=None, target=0.5, t=1):
        e = S.engine(cfg)
        S.ready(e, t=t)
        cid, _ = S.submit_start(e, S.pos_cmd(target), t, t)
        return e, cid

    def test_samples_before_start_do_not_count(self):
        e = S.engine()
        S.ready(e)
        r = e.submit(S.pos_cmd(0.5), 1)
        for t in range(1, 6):
            e.feedback("joint-1", S.sample(0.5), t * 50)
        self.assertEqual(e.command(r.command_id)["state"], "ACCEPTED")

    def test_completion_after_settling_window(self):
        cfg = S.config(settling_duration_ms=100, max_feedback_age_ms=200, position_tolerance=0.01)
        e, cid = self._running(cfg, t=1000)
        e.feedback("joint-1", S.sample(0.5), 1000)
        e.feedback("joint-1", S.sample(0.5), 1050)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        res = e.feedback("joint-1", S.sample(0.5), 1100)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"], c["phase"]), ("COMPLETED", "GOAL_REACHED", "NONE"))
        self.assertTrue(res.events)
        self.assertEqual(e.joint_state("joint-1", 1100)["control_state"], "IDLE")

    def test_out_of_tolerance_or_invalid_sample_restarts_the_window(self):
        cfg = S.config(settling_duration_ms=100, max_feedback_age_ms=200, position_tolerance=0.01)
        e, cid = self._running(cfg, t=1000)
        e.feedback("joint-1", S.sample(0.5), 1000)
        e.feedback("joint-1", S.sample(0.9), 1050)
        e.feedback("joint-1", S.sample(0.5), 1100)
        e.feedback("joint-1", S.sample(0.5, validity="INVALID"), 1150)
        e.feedback("joint-1", S.sample(0.5), 1200)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e.feedback("joint-1", S.sample(0.5), 1300)
        self.assertEqual(e.command(cid)["state"], "COMPLETED")

    def test_gap_larger_than_max_age_restarts_the_window(self):
        cfg = S.config(settling_duration_ms=100, max_feedback_age_ms=60, position_tolerance=0.01)
        e, cid = self._running(cfg, t=1000)
        e.feedback("joint-1", S.sample(0.5), 1000)
        e.feedback("joint-1", S.sample(0.5), 1200)   # gap 200 > 60: window restarts at 1200
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e.feedback("joint-1", S.sample(0.5), 1250)
        e.feedback("joint-1", S.sample(0.5), 1300)
        self.assertEqual(e.command(cid)["state"], "COMPLETED")

    def test_velocity_with_duration_completes_on_tick_only(self):
        e = S.engine()
        S.ready(e)
        cid, _ = S.submit_start(e, S.vel_cmd(0.1, duration=500), 1, 10)
        e.tick(509)
        self.assertEqual(e.command(cid)["state"], "RUNNING")
        e.tick(510)
        c = e.command(cid)
        self.assertEqual((c["state"], c["reason_code"]), ("COMPLETED", "DURATION_ELAPSED"))

    def test_velocity_without_duration_never_completes(self):
        e = S.engine()
        S.ready(e)
        cid, _ = S.submit_start(e, S.vel_cmd(0.1), 1, 1)
        e.tick(10_000_000)
        self.assertEqual(e.command(cid)["state"], "RUNNING")

    def test_completed_command_ignores_late_start(self):
        cfg = S.config(settling_duration_ms=0, position_tolerance=0.01)
        e, cid = self._running(cfg, t=10)
        e.feedback("joint-1", S.sample(0.5), 10)
        self.assertEqual(e.command(cid)["state"], "COMPLETED")
        before = e.command(cid)
        r = e.execution_started(cid, before["backend_reference"], 11)
        self.assertEqual(r.ignored[0]["reason"], "terminal")
        self.assertEqual(e.command(cid), before)


class TestDeterminismAndPurity(unittest.TestCase):
    def _run(self):
        e = S.engine(S.config(settling_duration_ms=50, position_tolerance=0.01))
        out = []
        S.ready(e)
        r = e.submit(S.pos_cmd(0.5), 1, utc="u1")
        out.append(r)
        out.append(e.execution_started(r.command_id, "ref-" + r.command_id, 2, "u2"))
        for t in (10, 40, 70):
            out.append(e.feedback("joint-1", S.sample(0.5), t, "u%d" % t))
        out.append(e.tick(100))
        return [(x.admission, x.command_id, x.requests, x.events, x.ignored) for x in out], e.commands()

    def test_same_inputs_give_identical_outputs(self):
        self.assertEqual(self._run(), self._run())

    def test_results_are_copies(self):
        e = S.engine()
        S.ready(e)
        r = e.submit(S.pos_cmd(), 1)
        e.command(r.command_id)["state"] = "FAILED"
        r.requests[0]["parameters"]["target_position"] = 99
        self.assertEqual(e.command(r.command_id)["state"], "ACCEPTED")
        self.assertEqual(e.command(r.command_id)["transitions"][0]["to"], "ACCEPTED")

    def test_engine_imports_no_clock_random_or_backend(self):
        banned = {"time", "datetime", "random", "secrets", "os", "socket", "threading", "asyncio", "subprocess"}
        for path in ENGINE_DIR.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module.split(".")[0]]
                for n in names:
                    with self.subTest(file=path.name, module=n):
                        self.assertNotIn(n, banned)
                        self.assertNotIn("backend", n)


class TestStatusReport(unittest.TestCase):
    def test_report_establishes_state_only_from_unknown_and_when_fresh(self):
        e = S.engine()
        e.status_report("joint-1", "IDLE", 10_000, 0)   # too old: ignored
        self.assertEqual(e.joint_state("joint-1", 0)["control_state"], "UNKNOWN")
        e.status_report("joint-1", "IDLE", 0, 1)
        self.assertEqual(e.joint_state("joint-1", 1)["control_state"], "IDLE")
        e.status_report("joint-1", "HOLDING", 0, 2)     # not UNKNOWN any more: ignored
        self.assertEqual(e.joint_state("joint-1", 2)["control_state"], "IDLE")


class TestModel(unittest.TestCase):
    def test_terminal_needs_valid_reason_and_nonterminal_none(self):
        model.check_transition("RUNNING", "COMPLETED", "GOAL_REACHED")
        with self.assertRaises(IllegalTransition):
            model.check_transition("RUNNING", "COMPLETED", None)
        with self.assertRaises(IllegalTransition):
            model.check_transition("RUNNING", "COMPLETED", "NOT_A_CODE")
        with self.assertRaises(IllegalTransition):
            model.check_transition("ACCEPTED", "RUNNING", "GOAL_REACHED")
        model.check_transition("ACCEPTED", "RUNNING", None)

    def test_terminal_states_have_no_exits(self):
        for t in model.TERMINAL_STATES:
            for to in model.STATES:
                self.assertFalse(model.is_allowed(t, to))

    def test_engine_class_exported(self):
        self.assertTrue(callable(LifecycleEngine))


if __name__ == "__main__":
    unittest.main()
