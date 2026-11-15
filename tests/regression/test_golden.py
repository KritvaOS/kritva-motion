"""Regression gate (KOS-MOTION-004 PR-06, AC-406): the committed golden traces are compared byte for byte.

A change in any public output or in what crosses the backend boundary fails here. A golden trace changes only
through `python3 scripts/regression_update.py`, whose diff is reviewed in the pull request. Deterministic and
offline. Software evidence only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import golden_support as G  # noqa: E402


class TestGoldenTraces(unittest.TestCase):
    def test_each_scenario_matches_its_golden_trace_byte_for_byte(self):
        for name in G.names():
            with self.subTest(scenario=name):
                path = G.GOLDEN / f"{name}.json"
                self.assertTrue(path.is_file(), f"{path.name} is missing: run python3 scripts/regression_update.py and review the diff")
                self.assertEqual(path.read_bytes(), G.render(name).encode("ascii"),
                                 f"{name}: the output changed; if intended run python3 scripts/regression_update.py and review the diff")

    def test_there_is_no_stale_golden_file(self):
        on_disk = sorted(p.stem for p in G.GOLDEN.glob("*.json"))
        self.assertEqual(on_disk, G.names())

    def test_rendering_is_deterministic(self):
        for name in G.names():
            self.assertEqual(G.render(name), G.render(name))

    def test_a_changed_behaviour_is_detected(self):
        """The comparison has teeth: a scenario whose backend starts one millisecond later no longer matches."""
        import copy
        scenarios = G.I.scenarios()
        sc = copy.deepcopy(scenarios["move_and_cancel"])
        sc["profile"]["joints"][G.I.J1]["start"] = ("ok", 6)
        sc["steps"] = [("submit", "a", G.I.vel("r1"), 10), ("poll", 15), ("poll", 16), ("terminate", "a", "CANCEL_REQUESTED", 20),
                       ("poll", 49), ("poll", 50)]
        changed = G.render("move_and_cancel", {"move_and_cancel": sc})
        self.assertNotEqual(changed.encode("ascii"), (G.GOLDEN / "move_and_cancel.json").read_bytes())

    def test_the_traces_are_canonical_ascii_json_with_one_trailing_newline(self):
        for p in G.GOLDEN.glob("*.json"):
            raw = p.read_bytes()
            self.assertTrue(raw.endswith(b"\n") and not raw.endswith(b"\n\n"), p.name)
            raw.decode("ascii")


if __name__ == "__main__":
    unittest.main()
