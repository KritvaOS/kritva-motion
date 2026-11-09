"""Conformance tests that close KOS-MOTION-003 (PR-06): CT-LC-01, CT-TMO-07 and CT-DET-01.

Each method is the single executable test named by one IN_SCOPE entry of
tests/manifest/conformance_manifest.json. The method name is the ID with hyphens replaced by underscores.
The streams are the plain-data scripts of scenario_support.py: the fault-injection scenario set of CT-TMO-07 is
SCENARIOS there ("every fault-injection scenario" means exactly that listed set, interpretation I-9).
Deterministic and offline. Software evidence only: every input is supplied, so these tests never show that
anything stopped, completed or failed physically (contract 2.2, 17.5).
"""
import copy
import unittest

import scenario_support as X
from kritva_motion.lifecycle import model

TERMINAL = model.TERMINAL_STATES

# One stream per transition of contract 7.5 (T1 is the first step of every stream).
REACH = {
    "T2": [("submit", ("vel", X.JOINT, 0.1), 1), ("started", "cmd-1", 1)],
    "T3": [("submit", ("pos", X.JOINT, 0.5), 1, {"defer_dispatch": True}), ("submit", ("cancel", "cmd-1"), 2)],
    "T4": [("submit", ("pos", X.JOINT, 0.5, {"deadline_ms": 100}), 1), ("tick", 101), ("tick", 101 + X.BOUND)],
    "T5": [("submit", ("veld", X.JOINT, 0.1, 100), 1), ("started", "cmd-1", 1), ("feedback", X.JOINT, 0.0, 100),
           ("tick", 101)],
    "T6": [("submit", ("vel", X.JOINT, 0.1), 1), ("started", "cmd-1", 1), ("submit", ("cancel", "cmd-1"), 5),
           ("term_confirmed", "cmd-1", 8)],
    "T7": [("submit", ("pos", X.JOINT, 0.5), 1), ("started", "cmd-1", 1),
           ("joint_fault", X.JOINT, "TRACKING_ERROR", 5), ("term_confirmed", "cmd-1", 8)],
}


def state_events(outputs, command_id):
    return [ev["data"] for out in outputs if out for ev in out["events"]
            if ev["event_type"] == "COMMAND_STATE_CHANGED" and ev["stream"]["id"] == command_id]


def check_record(case, rec, events):
    """The record of one command: a chain from admission to at most one terminal state, each transition
    once, a reason code on every terminal transition and none on the others, one event per transition."""
    tr = rec["transitions"]
    case.assertEqual(tr[0]["from"], None)
    for a, b in zip(tr, tr[1:]):
        case.assertEqual(a["to"], b["from"], "the chain is continuous")
    pairs = [(t["from"], t["to"]) for t in tr]
    case.assertEqual(len(pairs), len(set(pairs)), "no transition is recorded twice")
    for t in tr:
        case.assertIn((t["from"], t["to"]), model.TRANSITIONS)
        if t["to"] in TERMINAL:
            case.assertIn(t["reason_code"], model.REASON_CODES[t["to"]])
        else:
            case.assertIsNone(t["reason_code"])
    terminal = [t for t in tr if t["to"] in TERMINAL]
    case.assertLessEqual(len(terminal), 1)
    if terminal:
        case.assertIs(tr[-1], terminal[0], "nothing follows the terminal transition")
        case.assertEqual((rec["state"], rec["reason_code"], rec["phase"]), (tr[-1]["to"], tr[-1]["reason_code"], "NONE"))
    case.assertEqual(len(events), len(tr), "every transition is published once")
    case.assertEqual([(ev["from"], ev["to"], ev["reason_code"]) for ev in events],
                     [(t["from"], t["to"], t["reason_code"]) for t in tr])


class TestFinalConformance(unittest.TestCase):
    def test_CT_LC_01(self):
        """Every transition in 7.5 is reachable and recorded once with a reason code."""
        reached = set()
        for label, steps in REACH.items():
            with self.subTest(path=label):
                e, out = X.run(X.ready_both() + steps)
                rec = e.command("cmd-1")
                check_record(self, rec, state_events(out, "cmd-1"))
                reached |= {model.TRANSITIONS[(t["from"], t["to"])] for t in rec["transitions"]}
                self.assertIn(label, {model.TRANSITIONS[(t["from"], t["to"])] for t in rec["transitions"]})
                self.assertTrue(rec["transitions"][-1]["to"] in TERMINAL or label == "T2")
        self.assertEqual(reached, set(model.TRANSITIONS.values()), "all of T1 to T7")
        self.assertEqual(len(model.TRANSITIONS), 7)

    def test_CT_TMO_07(self):
        """Every accepted command reaches exactly one terminal state in every fault-injection scenario."""
        names = [sc["name"] for sc in X.SCENARIOS]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 20)
        for sc in X.SCENARIOS:
            with self.subTest(scenario=sc["name"]):
                e, out = X.run(sc["steps"])
                out += X.settle(e)
                self.assertTrue(any(e.faults(j) for j in ("joint-1", "joint-c")), "the scenario injects a fault")
                commands = e.commands()
                self.assertGreaterEqual(len(commands), 1)
                for rec in commands:
                    self.assertIn(rec["state"], TERMINAL, f"{rec['command_id']} reached a terminal state")
                    check_record(self, rec, state_events(out, rec["command_id"]))
                    self.assertEqual(len([t for t in rec["transitions"] if t["to"] in TERMINAL]), 1)
                before = X.records(e)
                late_t = X.FAR + 20000
                for late in [("started", c["command_id"], late_t) for c in commands] + \
                            [("term_confirmed", c["command_id"], late_t + 1) for c in commands] + \
                            [("hold_confirmed", c["command_id"], late_t + 2) for c in commands]:
                    X.apply(e, late)
                self.assertEqual(X.records(e), before, "a late input never changes a terminal command")

    def test_CT_DET_01(self):
        """The same ordered inputs under a simulated monotonic clock produce identical state, events and history."""
        for sc in X.SCENARIOS:
            with self.subTest(scenario=sc["name"]):
                runs = []
                for steps in (sc["steps"], copy.deepcopy(sc["steps"]), list(sc["steps"])):
                    e, out = X.run(steps)
                    out += X.settle(e)
                    runs.append((out, X.snapshot(e, X.FAR + 10000)))
                self.assertEqual(runs[0], runs[1])
                self.assertEqual(runs[0], runs[2])
                self.assertTrue(any(o["events"] for o in runs[0][0] if o), "events were produced and compared")
                self.assertTrue(runs[0][1]["joint_transitions"]["joint-1"], "history was produced and compared")
