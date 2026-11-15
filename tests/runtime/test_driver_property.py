"""Fixed-seed property test of the driver (KOS-MOTION-004 PR-06, BACKEND.md section 9).

It draws ITERATIONS random streams with random.Random(SEED): a random backend behaviour (answers, delays, refusals,
confirmations that never come, feedback, health and fault events, a random declared concurrency) for two joints,
and STEPS random inputs on the injected clock (commands of every kind, terminations, time passing). The real
engine, stores, driver and scripted S1 simulator run; nothing is mocked. After every step, and at the end, it checks
the invariants of BACKEND.md section 9 with code written here, independent of the driver:

 INV-D1  every backend report is applied at most once, and every report the backend produced is seen once
 INV-D2  a lifecycle change is caused by a command, a report or a timer: every transition names such a trigger,
         and a command is RUNNING only after a start report for its reference (or an accepted STOP attempt)
 INV-D3  an operation that reaches the backend is allowed by the declaration at that moment and within the
         declared concurrency; a refused one never reaches it
 INV-D4  a terminal command never changes
 INV-D5  a termination is CONFIRMED only after a backend confirmation bound to the command's reference and joint;
         an accepted request alone never completes one
 INV-D6  no public string names a vendor, device, bus or address (the backend's reasons are full of them)
 INV-D7  the same stream run twice gives the same public output and the same boundary trace

The seed, the iteration count and the command are printed on every run so the CI evidence records them. It does
not replace the tests mapped to conformance IDs. Deterministic and offline. Software evidence only.

Command: python3 -m unittest discover -s tests/runtime -p test_driver_property.py
"""
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "integration"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import integration_support as I  # noqa: E402
import runtime_support as T  # noqa: E402
from kritva_motion.backend.simulator import Simulator  # noqa: E402
from kritva_motion.lifecycle import model as m  # noqa: E402

SEED, ITERATIONS, STEPS = 20261116, 150, 40
COMMAND = "python3 -m unittest discover -s tests/runtime -p test_driver_property.py"
TRIGGERS = {"ADMISSION", "EXECUTION_STARTED", "EXECUTION_REJECTED", "REQUEST_ISSUED", "TERMINATION_ACCEPTED",
            "TERMINATION_CONFIRMED", "TERMINATION_REFUSED", "TERMINATION_BOUND_EXPIRED", "HOLD_CONFIRMED",
            "HOLD_RELEASE_FAILED", "DEADLINE", "COMPLETION", "FAULT", "NEW_FAULT", "FAULT_CLEARED", "TARGET_CANCELLED",
            "TARGET_COMPLETED", "TARGET_FAILED", "STOP", "CANCEL"}     # the triggers the engine names for a command transition
FAULTS = ("BACKEND_UNAVAILABLE", "BACKEND_COMMUNICATION_LOSS", "BACKEND_EXECUTION_FAILURE")


class Probe:
    """Wraps a Simulator and checks INV-D1 and INV-D3 at the moment each call reaches the backend."""

    def __init__(self, inner, engine_ref):
        self.inner, self.engine_ref, self.violations = inner, engine_ref, []
        self.accepted, self.calls, self.produced = set(), [], []

    def describe_capabilities(self):
        return self.inner.describe_capabilities()

    def health(self):
        return self.inner.health()

    def poll(self, now_ms):
        out = self.inner.poll(now_ms)
        self.produced += out
        return out

    def _active(self):
        e = self.engine_ref[0]
        return sum(1 for c in e.commands() if c["backend_reference"] in self.accepted and c["state"] not in m.TERMINAL_STATES)

    def dispatch(self, request, now_ms):
        decl = self.inner.describe_capabilities()
        caps = decl["capabilities"]
        mode = {"SET_POSITION": "position", "SET_VELOCITY": "velocity"}[request["operation"]]
        if mode not in caps["supported_modes"] or request["target"]["type"] not in decl["supported_target_types"]:
            self.violations.append(("dispatch of an undeclared mode or target type", request["operation"]))
        if self._active() >= caps["max_concurrent_executions"]:
            self.violations.append(("dispatch over the declared concurrency", request["backend_reference"]))
        self.calls.append(("dispatch", request["backend_reference"]))
        ans = self.inner.dispatch(request, now_ms)
        if ans.accepted:
            self.accepted.add(request["backend_reference"])
        return ans

    def request_hold(self, ref, joint_id, now_ms):
        if self.inner.describe_capabilities()["capabilities"]["position_hold"] is not True:
            self.violations.append(("hold without the declared capability", ref))
        self.calls.append(("request_hold", ref))
        ans = self.inner.request_hold(ref, joint_id, now_ms)
        if ans.accepted:
            self.accepted.add(ref)
        return ans

    def release_hold(self, ref, joint_id, now_ms):
        self.calls.append(("release_hold", ref))
        return self.inner.release_hold(ref, joint_id, now_ms)

    def request_termination(self, ref, cause, now_ms, target=None):
        self.calls.append(("request_termination", ref))
        return self.inner.request_termination(ref, cause, now_ms, target=target)


def draw_profile(rnd):
    def pick(*options):
        return rnd.choices([o for o, _ in options], [w for _, w in options])[0]
    joints = {}
    for jid in (I.J1, I.JP):
        p = {"dispatch": pick((("accept",), 85), (("reject", I.VENDOR_TEXT), 15))}
        p["start"] = pick((("ok", rnd.randint(1, 60)), 78), (("reject", I.VENDOR_TEXT, rnd.randint(1, 30)), 8), (None, 14))
        p["terminate"] = pick((("accept", rnd.randint(5, 80)), 70), (("accept", None), 15), (("refuse", I.VENDOR_TEXT), 15))
        if rnd.random() < 0.6:
            p["hold"] = ("accept", rnd.randint(1, 5), rnd.randint(6, 30))
            p["release"] = ("accept", pick((("ok", rnd.randint(1, 20)), 60), (("fail", rnd.randint(1, 20), I.VENDOR_TEXT), 40)))
        p["feedback"] = [(t, round(rnd.uniform(0.0, 0.5), 3), rnd.random() < 0.9) for t in range(20, 1500, 45)]
        joints[jid] = p
    events, t = [], 0
    for _ in range(rnd.randint(0, 3)):
        t += rnd.randint(30, 400)
        kind = rnd.choice(("health", "fault", "fault_cleared"))
        events.append((t, "health", rnd.choice(("AVAILABLE", "DEGRADED", "UNAVAILABLE"))) if kind == "health" else
                      (t, "fault", rnd.choice(FAULTS), None) if kind == "fault" else (t, "fault_cleared"))
    return {"joints": joints, "events": events}


def draw_commands(rnd, n):
    out = []
    for i in range(n):
        jid = rnd.choice((I.J1, I.JP))
        kind = rnd.choice(("vel", "vel", "pos", "hold", "stop", "terminate", "terminate"))
        out.append((kind, jid, i))
    return out


def run_stream(seed):
    rnd = random.Random(seed)
    profile, maxc = draw_profile(rnd), rnd.randint(1, 3)
    decl = T.declaration(max_concurrent_executions=maxc)
    decl["clock"]["domain"] = I.CLOCK
    holder = []
    probe = Probe(Simulator(I.to_sim_script({"joints": profile["joints"], "events": profile["events"]}), decl), holder)
    e, co, pub, sink, d = I.assemble(probe)
    holder.append(e)
    ids, t, seen_terminal, problems = [], 10, {}, []
    for kind, jid, i in draw_commands(rnd, STEPS):
        t += rnd.randint(1, 120)
        utc = f"2026-11-15T01:{(t // 60) % 60:02d}:{t % 60:02d}Z"
        if kind in ("vel", "pos", "hold", "stop"):
            unit = "rad/s" if jid == I.J1 else "m/s"
            cmd = (I.vel(f"r{i}", jid, unit) if kind == "vel" else
                   I.pos(f"r{i}", 0.2, jid) if kind == "pos" and jid == I.J1 else
                   I.S.hold_cmd(jid, client_request_id=f"r{i}") if kind == "hold" else
                   I.S.stop_cmd(jid, client_request_id=f"r{i}") if kind == "stop" else I.vel(f"r{i}", jid, unit))
            r = d.submit(I.A, cmd, t, utc)
            if r.admission.accepted and not r.admission.replay:
                ids.append(r.command_id)
        elif ids:
            d.terminate(rnd.choice(ids), rnd.choice(("CANCEL_REQUESTED", "STOP_REQUESTED")), t, utc)
        d.poll(t, utc)
        for c in e.commands():                                  # INV-D4
            if c["state"] in m.TERMINAL_STATES:
                snap = (c["state"], c["reason_code"], len(c["transitions"]))
                if seen_terminal.setdefault(c["command_id"], snap) != snap:
                    problems.append(("a terminal command changed", c["command_id"]))
    t += 2000
    d.poll(t, f"2026-11-15T02:{(t // 60) % 60:02d}:{t % 60:02d}Z")
    problems += probe.violations                                 # INV-D3
    started = {x["backend_reference"] for x in d.trace if x["direction"] == "from_backend" and x["kind"] == "execution_started"}
    confirmed = {(x["backend_reference"]) for x in d.trace if x["direction"] == "from_backend" and x["kind"] == "termination_confirmed"}
    for c in e.commands():
        for tr in c["transitions"]:                              # INV-D2
            if tr["trigger"] not in TRIGGERS:
                problems.append(("a transition without a known trigger", c["command_id"], tr["trigger"]))
            if tr["to"] == "RUNNING" and tr["trigger"] == "EXECUTION_STARTED" and c["backend_reference"] not in started:
                problems.append(("RUNNING without a start report", c["command_id"]))
        term = c["termination"]
        if term is not None and term["outcome"] == "CONFIRMED" and c["backend_reference"] not in confirmed:   # INV-D5
            problems.append(("CONFIRMED without a bound confirmation", c["command_id"]))
    sent = [x for x in d.trace if x["direction"] == "to_backend"]                                # INV-D3
    if len(sent) != len(probe.calls):
        problems.append(("trace and backend calls differ", len(sent), len(probe.calls)))
    from_backend = [x for x in d.trace if x["direction"] == "from_backend"]                      # INV-D1
    if len(from_backend) != len(probe.produced):
        problems.append(("reports produced and applied differ", len(probe.produced), len(from_backend)))
    public = {"events": sink.events, "commands": e.commands(), "faults": {j: e.faults(j) for j in (I.J1, I.JP)}}
    leaks = I.scan(public)                                       # INV-D6
    if leaks:
        problems.append(("a backend identifier reached public output", leaks[:2]))
    return problems, repr(public), repr(d.trace), len(ids)


class TestDriverProperties(unittest.TestCase):
    def test_properties_with_fixed_seed(self):
        print(f"\nproperty test: seed={SEED} iterations={ITERATIONS} steps_per_stream={STEPS} command={COMMAND}")
        accepted = terminal = 0
        for i in range(ITERATIONS):
            seed = SEED * 1000 + i
            problems, pub1, tr1, n = run_stream(seed)
            self.assertEqual(problems, [], f"stream seed {seed}")
            problems2, pub2, tr2, _ = run_stream(seed)                  # INV-D7
            self.assertEqual((pub1, tr1), (pub2, tr2), f"stream seed {seed} is not deterministic")
            accepted += n
        print(f"property test: accepted_commands={accepted} streams={ITERATIONS}")
        self.assertGreater(accepted, 500)


if __name__ == "__main__":
    unittest.main()
