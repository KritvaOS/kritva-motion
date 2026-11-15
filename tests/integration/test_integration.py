"""Integration tests (KOS-MOTION-004 PR-05): scenarios through the real driver, stores, engine and a backend.

CT-BE-03 (no actuator-specific identifier in public output) and CT-BE-06 (swapping the backend changes no public
behaviour) are the single executable tests named by the IN_SCOPE manifest entries. Nothing of ours is mocked: the
scenarios run on the scripted S1 simulator and on the LoopbackBackend, a second conforming backend whose own
diagnostics are full of vendor, bus and device names. Software evidence only (contract 17.7)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integration_support as I  # noqa: E402
import jsonschema  # noqa: E402

SCHEMA = json.loads((I.ROOT / "contract" / "motion-event.schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
EXPECTED = {   # scenario -> (command key -> (state, reason_code))
    "move_and_cancel": {"a": ("CANCELLED", "CANCEL_REQUESTED")},
    "position_completes_from_feedback": {"a": ("COMPLETED", "GOAL_REACHED")},
    "rejected_at_dispatch": {"a": ("FAILED", "BACKEND_REJECTED_DISPATCH")},
    "rejected_after_acceptance": {"a": ("FAILED", "BACKEND_REJECTED_DISPATCH")},
    "termination_never_confirmed": {"a": ("FAILED", "TERMINATION_UNCONFIRMED")},
    "stop_with_nothing_running": {"s": ("COMPLETED", "STOP_CONFIRMED")},
    "refused_stop": {"s": ("FAILED", "BACKEND_REJECTED_DISPATCH")},
    "hold_then_movement_releases_it": {"h": ("COMPLETED", "HOLD_ENGAGED"), "m": ("RUNNING", None)},
    "hold_release_fails": {"h": ("COMPLETED", "HOLD_ENGAGED"), "m": ("FAILED", "BACKEND_REJECTED_DISPATCH")},
    "backend_health_and_faults": {"a": ("RUNNING", None)},
    "admission_rejection": {},
    "concurrency_limit": {"a": ("RUNNING", None), "b": ("FAILED", "BACKEND_REJECTED_DISPATCH")},
}
BACKENDS = ("simulator", "loopback")


class TestScenarios(unittest.TestCase):
    def test_every_scenario_reaches_its_outcome_on_both_backends(self):
        self.assertEqual(set(EXPECTED), set(I.scenarios()))
        for name, sc in I.scenarios().items():
            for kind in BACKENDS:
                with self.subTest(scenario=name, backend=kind):
                    public, _, _ = I.run_scenario(kind, sc)
                    got = {k: (v["state"], v["reason_code"]) for k, v in public["commands"].items()}
                    self.assertEqual(got, EXPECTED[name])

    def test_every_published_event_validates_against_the_event_schema(self):
        for name, sc in I.scenarios().items():
            for kind in BACKENDS:
                public, _, _ = I.run_scenario(kind, sc)
                for ev in public["events"]:
                    with self.subTest(scenario=name, backend=kind, event=ev["event_id"]):
                        VALIDATOR.validate(ev)

    def test_backend_events_are_published_in_their_own_stream(self):
        public, _, _ = I.run_scenario("loopback", I.scenarios()["backend_health_and_faults"])
        backend = [(e["event_type"], e["data"]) for e in public["events"] if e["stream"]["kind"] == "backend"]
        self.assertEqual([t for t, _ in backend], ["BACKEND_HEALTH_CHANGED", "BACKEND_FAULT_RAISED",
                                                   "BACKEND_FAULT_CLEARED", "BACKEND_HEALTH_CHANGED"])
        self.assertEqual([e["sequence_number"] for e in public["events"] if e["stream"]["kind"] == "backend"], [1, 2, 3, 4])

    def test_the_run_is_deterministic(self):
        for kind in BACKENDS:
            sc = I.scenarios()["hold_then_movement_releases_it"]
            self.assertEqual(I.run_scenario(kind, sc)[0], I.run_scenario(kind, sc)[0])

    def test_the_driver_never_advances_a_lifecycle_by_itself(self):
        public, d, _ = I.run_scenario("simulator", I.scenarios()["move_and_cancel"])
        transitions = public["commands"]["a"]["transitions"]
        self.assertEqual([t["trigger"] for t in transitions],
                         ["ADMISSION", "EXECUTION_STARTED", "TERMINATION_CONFIRMED"])


class TestSwapInvariance(unittest.TestCase):
    def test_CT_BE_06(self):
        """17.1: swapping the simulator for another conforming backend with an equivalent behaviour changes no public
        output: the same events with the same sequence numbers, command records, status view, history, joint
        snapshots, faults and admission answers."""
        for name, sc in I.scenarios().items():
            with self.subTest(scenario=name):
                sim, _, _ = I.run_scenario("simulator", sc)
                loop, _, _ = I.run_scenario("loopback", sc)
                self.assertEqual(sim.keys(), loop.keys())
                for part in sim:
                    self.assertEqual(sim[part], loop[part], f"{name}: public part {part!r} differs between the backends")
                self.assertTrue(sim["events"] or sim["admissions"], "the scenario produced public output")

    def test_the_two_backends_really_differ(self):
        sc = I.scenarios()["rejected_at_dispatch"]
        sim, dsim, bsim = I.run_scenario("simulator", sc)
        loop, dloop, bloop = I.run_scenario("loopback", sc)
        self.assertNotEqual(type(bsim), type(bloop))
        self.assertTrue(any("ttyUSB" in x for x in bloop.diagnostics), "the loopback keeps vendor-flavoured diagnostics")
        self.assertTrue(hasattr(bloop, "diagnostics") and not hasattr(bsim, "diagnostics"))
        self.assertTrue(all(t["simulated"] for t in dsim.trace if t["direction"] == "from_backend"))
        self.assertTrue(not any(t["simulated"] for t in dloop.trace if t["direction"] == "from_backend"))


class TestNoBackendIdentifierInPublicOutput(unittest.TestCase):
    def test_CT_BE_03(self):
        """4.1 and 17: no actuator-specific identifier appears in any public message or error. Every public string of
        every scenario, on both backends, is scanned for the vendor, device, bus and address spellings listed in
        `integration_support.FORBIDDEN`; the backends' own words (their rejection reasons and diagnostics are full of
        those spellings) stay in the driver log, which is a diagnostic and not public output."""
        total = 0
        for name, sc in I.scenarios().items():
            for kind in BACKENDS:
                with self.subTest(scenario=name, backend=kind):
                    public, d, _ = I.run_scenario(kind, sc)
                    total += sum(1 for _ in I.strings(public))
                    self.assertEqual(I.scan(public), [])
        self.assertGreater(total, 1000)

    def test_the_scan_finds_what_it_looks_for(self):
        for leak in ("ACME-DRV-3000", "can0/node7", "/dev/ttyUSB0", "overcurrent", "0x1f", "10.0.0.7", "aa:bb:cc:dd:ee:ff"):
            with self.subTest(leak=leak):
                self.assertTrue(I.scan({"events": [{"data": {"detail": f"failed on {leak}"}}]}))
        self.assertEqual(I.scan({"detail": "BACKEND_REFUSED", "reason_code": "BACKEND_REJECTED_DISPATCH"}), [])

    def test_the_backend_words_are_kept_in_the_driver_log_only(self):
        for kind in BACKENDS:
            public, d, _ = I.run_scenario(kind, I.scenarios()["rejected_at_dispatch"])
            self.assertTrue(any("ttyUSB0" in x["reason"] for x in d.log), "the diagnostic keeps the backend's words")
            self.assertEqual(public["commands"]["a"]["detail"], "BACKEND_REFUSED")
            self.assertEqual(I.scan(public), [])

    def test_a_driver_that_passed_the_backend_text_on_would_be_caught(self):
        from kritva_motion.runtime.driver import Driver

        class Leaky(Driver):
            def _rejected(self, cid, ref, backend_text, now_ms, utc):
                return self._engine.execution_rejected(cid, ref, backend_text, now_ms, utc)
        original = I.Driver
        I.Driver = Leaky
        try:
            public, _, _ = I.run_scenario("loopback", I.scenarios()["rejected_at_dispatch"])
        finally:
            I.Driver = original
        self.assertTrue(I.scan(public))


if __name__ == "__main__":
    unittest.main()
