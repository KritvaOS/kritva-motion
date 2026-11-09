"""Fixed-seed property test of the lifecycle engine (KOS-MOTION-003 PR-06, LIFECYCLE.md section 9).

It draws ITERATIONS random input streams from the generator below with random.Random(SEED), runs each one, and
checks the invariants INV-01 to INV-04, INV-07, INV-10, INV-12 and the joint transition tables after every
stream. Random draws include invalid, duplicate, stale and conflicting inputs, which the engine must ignore and
record, never raise on. The seed, the iteration count and the command are printed on every run so that the CI
evidence records them. It does not replace the tests mapped to conformance IDs. Deterministic and offline:
the same seed gives the same streams on every run. Software evidence only.

Command: python3 -m unittest discover -s tests/lifecycle -p test_lifecycle_property.py
"""
import random
import unittest

import scenario_support as X
from kritva_motion.lifecycle import model

SEED = 20261103
ITERATIONS = 400
STEPS = 45
COMMAND = "python3 -m unittest discover -s tests/lifecycle -p test_lifecycle_property.py"
JOINTS = (X.JOINT, X.JOINT_2)
FAULT_CODES = ("TRACKING_ERROR", "JOINT_LIMIT_VIOLATION")
BACKEND_CODES = ("BACKEND_UNAVAILABLE", "BACKEND_COMMUNICATION_LOSS", "BACKEND_EXECUTION_FAILURE")
TERMINAL = model.TERMINAL_STATES


def draw_stream(rng):
    """One random stream: ready joints, then STEPS random steps with non-decreasing times."""
    steps = X.ready_both()
    t, n_cmd, n_fault = 0, 0, 0
    for _ in range(STEPS):
        t += rng.choice((0, 1, 5, 20, 100, 400, 1200))
        j = rng.choice(JOINTS)
        cid = f"cmd-{rng.randint(1, n_cmd + 1)}"
        fid = f"fault-{rng.randint(1, n_fault + 1)}"
        kind = rng.choices(
            ["pos", "vel", "veld", "stop", "hold", "cancel", "clear", "started", "tick", "feedback", "status",
             "term_accepted", "term_confirmed", "term_refused", "hold_confirmed", "hold_released",
             "hold_release_failed", "joint_fault", "backend_fault", "backend_fault_cleared", "backend_health",
             "dispatch"],
            weights=[6, 4, 2, 3, 3, 3, 3, 8, 5, 8, 2, 4, 8, 1, 3, 2, 1, 4, 2, 2, 1, 3])[0]
        defer = rng.random() < 0.2
        if kind in ("pos", "vel", "veld", "stop", "hold"):
            opts = {"deadline_ms": rng.choice((50, 300, 2000))} if rng.random() < 0.3 else {}
            spec = {"pos": ("pos", j, round(rng.uniform(-1, 1), 2), opts), "vel": ("vel", j, 0.1, opts),
                    "veld": ("veld", j, 0.1, rng.choice((50, 500)), opts), "stop": ("stop", j, opts),
                    "hold": ("hold", j, opts)}[kind]
            step = ("submit", spec, t, {"defer_dispatch": True} if defer else {})
            n_cmd += 1                                     # a rejection makes this id refer to nothing; that is a draw too
        elif kind == "cancel":
            step = ("submit", ("cancel", cid), t)
            n_cmd += 1
        elif kind == "clear":
            step = ("submit", ("clear", j, fid), t, {})   # never deferred here: see the end-of-stream rule below
            n_cmd += 1
        elif kind in ("started", "term_accepted", "term_confirmed", "term_refused", "hold_confirmed", "hold_released",
                      "hold_release_failed", "dispatch"):
            step = (kind, cid, t)
        elif kind == "tick":
            step = ("tick", t)
        elif kind == "feedback":
            step = ("feedback", j, round(rng.uniform(-1, 1), 2), t, rng.choice(("VALID", "VALID", "VALID", "INVALID")))
        elif kind == "status":
            step = ("status", j, rng.choice(("IDLE", "ACTIVE", "HOLDING", "UNKNOWN")), rng.choice((0, 50, 500)), t)
        elif kind == "joint_fault":
            step = ("joint_fault", j, rng.choice(FAULT_CODES), t)
            n_fault += 1
        elif kind == "backend_fault":
            step = ("backend_fault", rng.choice(BACKEND_CODES), t, [j] if rng.random() < 0.5 else None)
            n_fault += 1
        elif kind == "backend_fault_cleared":
            step = ("backend_fault_cleared", t)
        else:
            step = ("backend_health", rng.choice(("AVAILABLE", "DEGRADED", "UNAVAILABLE", "FAULTED")), t)
        steps.append(step)
    return steps, t


def finish(e, t):
    """End of a stream: dispatch every command still accepted and never dispatched (the caller drives that
    point, I-15 and I-34), then let every limit pass."""
    out = []
    for rec in e.commands():
        if rec["state"] == "ACCEPTED" and rec["phase"] == "NONE":
            out.append(X.result_data(e.dispatch(rec["command_id"], t + 1)))
    out += X.settle(e, max(X.FAR, t + 10) )
    return out


class TestFixedSeedProperties(unittest.TestCase):
    def test_properties_with_fixed_seed(self):
        print(f"\nproperty test: seed={SEED} iterations={ITERATIONS} steps_per_stream={STEPS} command={COMMAND}")
        rng = random.Random(SEED)
        accepted_total = terminal_total = faults_total = 0
        for i in range(ITERATIONS):
            steps, t_end = draw_stream(rng)
            with self.subTest(iteration=i):
                e = X.S.engine()
                frozen = {}                                   # INV-01: command id -> record once it is terminal
                outputs = []
                for step in steps:
                    outputs.append(X.result_data(X.apply(e, step)))
                    for rec in e.commands():
                        if rec["command_id"] in frozen:
                            self.assertEqual(rec, frozen[rec["command_id"]], "INV-01: a terminal command never changes")
                        elif rec["state"] in TERMINAL:
                            frozen[rec["command_id"]] = rec
                        self.assertIn(rec["phase"], model.PHASES_OF_STATE[rec["state"]])     # INV-04
                outputs += finish(e, t_end)
                self.check_end(e, outputs, steps, i)
                accepted_total += len(e.commands())
                terminal_total += sum(r["state"] in TERMINAL for r in e.commands())
                faults_total += sum(len(e.faults(j)) for j in JOINTS)
                # INV-12: the same stream on a fresh engine gives the same outputs and records
                e2 = X.S.engine()
                outputs2 = [X.result_data(X.apply(e2, s)) for s in steps] + finish(e2, t_end)
                self.assertEqual(outputs, outputs2, "INV-12: identical outputs")
                self.assertEqual(X.records(e), X.records(e2), "INV-12: identical records")
        self.assertEqual(accepted_total, terminal_total, "INV-02: every accepted command is terminal")
        self.assertGreater(accepted_total, ITERATIONS, "the generator accepts commands")
        self.assertGreater(faults_total, ITERATIONS // 4, "the generator injects faults")
        print(f"property test: accepted_commands={accepted_total} terminal={terminal_total} fault_records={faults_total}")

    def check_end(self, e, outputs, steps, i):
        clear_targets = {}
        for rec in e.commands():
            tr = rec["transitions"]
            self.assertEqual(rec["state"] in TERMINAL, True, f"INV-02: {rec['command_id']} is terminal")       # INV-02
            self.assertEqual(tr[0]["to"], "ACCEPTED")
            for a, b in zip(tr, tr[1:]):
                self.assertEqual(a["to"], b["from"])
            for x in tr:
                self.assertIn((x["from"], x["to"]), model.TRANSITIONS)                                           # INV-03
                if x["to"] in TERMINAL:
                    self.assertIn(x["reason_code"], model.REASON_CODES[x["to"]])
            self.assertEqual(len([x for x in tr if x["to"] in TERMINAL]), 1)
            self.assertEqual(rec["phase"], "NONE")                                                           # INV-04
        # INV-07: at most one backend termination request per command
        requests = [q for out in outputs if out for q in out["requests"] if q["op"] == "request_termination"
                    and q.get("command_id")]
        per = {}
        for q in requests:
            per[q["command_id"]] = per.get(q["command_id"], 0) + 1
        self.assertTrue(all(n == 1 for n in per.values()), f"INV-07 in iteration {i}: {per}")
        # INV-10: a fault record is cleared only by a COMPLETED(FAULT_CLEARED) CLEAR_FAULT, one fault per clear
        cleared = [f["fault_id"] for j in JOINTS for f in e.faults(j) if f["state"] == "CLEARED"]
        done = [r for r in e.commands() if r["operation"] == "CLEAR_FAULT" and r["reason_code"] == "FAULT_CLEARED"]
        self.assertEqual(len(cleared), len(done), f"INV-10 in iteration {i}")
        for j in JOINTS:                                                         # joint tables of contract 13.3
            for x in e.joint_transitions(j):
                self.assertIn((x["from"], x["to"]), {"control": model.CONTROL_TRANSITIONS,
                                                     "health": model.HEALTH_TRANSITIONS}[x["dimension"]])
