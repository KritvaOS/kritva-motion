"""Fixed-seed property test of the stores (KOS-MOTION-005 PR-06, STORES.md section 4).

It draws ITERATIONS random input streams with random.Random(SEED): submissions from two clients (identical,
conflicting and invalid content), time passing (including past the idempotency retention), configuration
updates and rollbacks (valid, invalid, incompatible, unauthorized), engine inputs, faults, and event sinks that
fail, lose or duplicate. After every step it checks the invariants of STORES.md section 4 against a small
model written here, independent of the stores' code:

 INV-S1  one command per (client, request id) inside the retention period
 INV-S2  a replay returns the stored decision, with the replay flag, and changes nothing
 INV-S3  sequence numbers per stream are exactly 1, 2, 3, ... whatever the sinks do
 INV-S4  event delivery failure changes no command, joint, history entry or returned result
 INV-S5  an accepted command's version and digest equal the active ones at admission and never change
 INV-S6  an activation never changes the version a command already holds
 INV-S7  history is append-only: earlier fields and earlier lifecycle entries never change
 INV-S8  a rejected submission has a history record and no command_id
 INV-S10 replay of the input journal reproduces every command outcome (CT-DET-02)
 (INV-S9, no clock read, is a static check in test_events.py.)

The seed, the iteration count and the command are printed on every run so the CI evidence records them. It
does not replace the tests mapped to conformance IDs. Deterministic and offline. Software evidence only.

Command: python3 -m unittest discover -s tests/stores -p test_stores_property.py
"""
import copy
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "lifecycle"))
import lifecycle_support as S  # noqa: E402
from kritva_motion.lifecycle import LifecycleEngine  # noqa: E402
from kritva_motion.stores import (CommandHistory, ConfigurationRegistry, Coordinator, EventPublisher,  # noqa: E402
                                  IdempotencyStore, InputJournal, RecordingEngine, replay)

SEED = 20261115
ITERATIONS = 150
STEPS = 40
RETENTION = 20000
COMMAND = "python3 -m unittest discover -s tests/stores -p test_stores_property.py"
CLIENTS = ("client-A", "client-B")
TERMINAL = ("COMPLETED", "CANCELLED", "FAILED")


class Sink:
    def __init__(self, mode):
        self.mode, self.n, self.got = mode, 0, []

    def deliver(self, ev):
        self.n += 1
        if self.mode == "raise" or (self.mode == "flaky" and self.n % 3 == 0):
            raise RuntimeError("down")
        if self.mode == "lossy" and self.n % 2 == 0:
            return
        self.got.append(ev)
        if self.mode == "twice":
            self.got.append(copy.deepcopy(ev))


def cfg(version, variant):
    c = copy.deepcopy(S.base.CONFIG)
    c["config_version"] = version
    if variant == "wide":
        c["joints"][0] = S.base.joint(settling_duration_ms=300)
    elif variant == "narrow":
        c["joints"][0] = S.base.joint(position_max=0.3)        # incompatible with an open move to 0.5
    elif variant == "invalid":
        c["joints"][0] = S.base.joint(position_min=9.0)
    return c


def draw(rng):
    ops, n_ver = [], 0
    for _ in range(STEPS):
        kind = rng.choices(["submit", "advance", "ready", "cmd_input", "fault", "activate", "rollback", "tick"],
                           weights=[14, 5, 8, 12, 2, 4, 2, 3])[0]
        if kind == "submit":
            ops.append(("submit", rng.choice(CLIENTS), rng.choice(("r1", "r2", "r3", "r4")),
                        rng.choice(("pos_a", "pos_a", "pos_b", "bad", "vel", "stop", "prism")), rng.random() < 0.05))
        elif kind == "advance":
            ops.append(("advance", rng.choice((1, 20, 150, 12000, 25000))))
        elif kind == "cmd_input":
            ops.append(("cmd_input", rng.choice(("started", "terminate", "term_accepted", "term_confirmed", "dispatch")),
                        rng.randint(0, 9)))
        elif kind == "fault":
            ops.append(("fault", rng.choice(("joint-1", "joint-p"))))
        elif kind == "activate":
            n_ver += 1
            ops.append(("activate", f"v{n_ver}", rng.choice(("same", "wide", "narrow", "invalid")), rng.random() < 0.9))
        elif kind == "rollback":
            ops.append(("rollback", rng.randint(0, 5), rng.random() < 0.7))
        else:
            ops.append((kind,))
    return ops


def make_command(kind, req):
    if kind == "pos_a":
        return S.pos_cmd(0.5, client_request_id=req)
    if kind == "pos_b":
        return S.pos_cmd(0.4, client_request_id=req)
    if kind == "bad":
        return S.pos_cmd(5.0, client_request_id=req)
    if kind == "vel":
        return S.vel_cmd(0.1, client_request_id=req)
    if kind == "stop":
        return S.env("STOP", "joint-1", client_request_id=req)
    return S.pos_cmd(0.2, "joint-p", unit="m", client_request_id=req)


def content(cmd):
    return {k: cmd[k] for k in ("command_type", "target", "parameters") if k in cmd}


def sig(res):
    a = res.admission
    return (a.accepted, a.code, a.step, a.replay, res.command_id)


class World:
    def __init__(self, sink_modes):
        self.journal = InputJournal(S.base.BACKEND)
        raw = LifecycleEngine(None, copy.deepcopy(S.base.BACKEND), None)
        self.e = RecordingEngine(raw, self.journal)
        self.raw = raw
        self.store, self.hist = IdempotencyStore(RETENTION), CommandHistory(10 ** 9)
        self.sinks = [Sink(m) for m in sink_modes]
        self.pub = EventPublisher(self.sinks)
        self.reg = ConfigurationRegistry(self.e, S.base.CAPS, self.store)
        self.co = Coordinator(self.e, self.store, self.hist, self.pub)
        self.t = 0
        self.versions = []
        self.trace = []                      # every returned result signature, for the INV-S4 comparison


def run(ops, sink_modes, check):
    w = World(sink_modes)
    model = {}                               # (client, req) -> {"content", "decision", "expires"}
    frozen = {}                              # command id -> (version, digest)
    prev_hist = []
    w.reg.activate(cfg("v0", "same"), 0)
    w.versions.append("v0")
    for op in ops:
        n_before = len(w.raw.commands())
        w.t += 0
        kind = op[0]
        if kind == "advance":
            w.t += op[1]
        elif kind == "ready":
            for jid in ("joint-1", "joint-p"):
                w.co.observe(w.e.status_report(jid, "IDLE", 0, w.t, f"u{w.t}"))
                w.co.observe(w.e.feedback(jid, S.sample(0.0), w.t, f"u{w.t}"))
        elif kind == "tick":
            w.co.observe(w.e.tick(w.t, f"u{w.t}"))
        elif kind == "fault":
            w.co.observe(w.e.joint_fault(op[1], "TRACKING_ERROR", w.t, f"u{w.t}"))
        elif kind == "activate":
            rec = w.reg.activate(cfg(op[1], op[2]), w.t, permission_granted=op[3])
            if rec["outcome"] == "ACTIVATED":
                w.versions.append(op[1])
            w.trace.append(("activate", rec["outcome"], rec["refusal"]))
        elif kind == "rollback":
            target = w.versions[op[1] % len(w.versions)]
            rec = w.reg.rollback(target, w.t, permission_granted=op[2])
            w.trace.append(("rollback", rec["outcome"], rec["refusal"]))
        elif kind == "cmd_input":
            cmds = w.raw.commands()
            if cmds:
                cid = cmds[op[2] % len(cmds)]["command_id"]
                ref = "ref-" + cid
                res = {"started": lambda: w.e.execution_started(cid, ref, w.t, f"u{w.t}"),
                       "terminate": lambda: w.e.terminate(cid, "CANCEL_REQUESTED", w.t, f"u{w.t}"),
                       "term_accepted": lambda: w.e.termination_request_accepted(cid, ref, w.t, f"u{w.t}"),
                       "term_confirmed": lambda: w.e.termination_confirmed(cid, ref, w.t, f"u{w.t}"),
                       "dispatch": lambda: w.e.dispatch(cid, w.t, f"u{w.t}")}[op[1]]()
                w.co.observe(res)
        else:
            _, client, req, ckind, defer = op
            cmd = make_command(ckind, req)
            key = (client, req)
            live = model.get(key)
            if live is not None and w.t >= live["expires"]:
                live = None
            hist_n, cmd_n = len(w.hist.read()), len(w.raw.commands())
            res = w.co.submit(client, cmd, w.t, f"u{w.t}", defer_dispatch=defer)
            w.trace.append(sig(res))
            check_submit(w, model, key, live, cmd, res, hist_n, cmd_n, check)
        w.trace.append(("state", copy.deepcopy(w.raw.commands())))
        if check:
            check_after_step(w, frozen, prev_hist)
            prev_hist = w.hist.read()
    return w


def check_submit(w, model, key, live, cmd, res, hist_n, cmd_n, check):
    if not check:
        return
    a = res.admission
    if live is not None:
        if content(cmd) == live["content"]:                         # INV-S1, INV-S2
            assert a.replay and (a.accepted, a.code) == live["decision"][:2], ("S2", sig(res), live)
            assert res.command_id == live["decision"][2]
            assert len(w.raw.commands()) == cmd_n and len(w.hist.read()) == hist_n, "S2: a replay changes nothing"
        else:
            assert (not a.replay) and a.code == "REQUEST_ID_CONFLICT" and res.command_id is None, ("S1", sig(res))
            assert len(w.raw.commands()) == cmd_n
        return
    assert not a.replay, ("a new request is never a replay", sig(res))
    assert len(w.hist.read()) == hist_n + 1                          # one record per non-replay submission
    rec = w.hist.read()[-1]
    if a.accepted:
        assert len(w.raw.commands()) == cmd_n + 1
        assert rec["command_id"] == res.command_id and rec["submission_result"] == "ACCEPTED"
        c = w.raw.command(res.command_id)                            # INV-S5
        assert c["config_version"] == w.reg.active_version and c["config_digest"] == w.reg.digest_of(w.reg.active_version)
    else:
        assert rec["submission_result"] == "REJECTED" and rec["command_id"] is None and rec["lifecycle_history"] is None  # INV-S8
        assert res.command_id is None and len(w.raw.commands()) == cmd_n
    if a.accepted or a.step >= 4:
        model[key] = {"content": content(cmd), "decision": (a.accepted, a.code, res.command_id),
                      "expires": w.t + RETENTION}


def check_after_step(w, frozen, prev_hist):
    for c in w.raw.commands():                                       # INV-S5 / INV-S6: version and digest never change
        pair = (c["config_version"], c["config_digest"])
        assert frozen.setdefault(c["command_id"], pair) == pair, "S6: the binding of a command changed"
    for key, seqs in per_stream(w.pub.published()).items():          # INV-S3
        assert seqs == list(range(1, len(seqs) + 1)), ("S3", key, seqs)
    now = w.hist.read()                                              # INV-S7
    assert len(now) >= len(prev_hist)
    for old, new in zip(prev_hist, now):
        for f in old:
            if f in ("lifecycle_history", "replays", "fault_references"):
                if old[f] is None:
                    assert new[f] is None, ("S7", f)
                else:
                    assert new[f][:len(old[f])] == old[f], ("S7 prefix", f)
            elif f in ("execution_started_at", "completed_at", "result"):
                if old[f] not in (None, {"state": "PENDING"}):
                    assert new[f] == old[f], ("S7 derived field changed", f)
            else:
                assert new[f] == old[f], ("S7", f)


def per_stream(events):
    out = {}
    for ev in events:
        out.setdefault((ev["stream"]["kind"], ev["stream"]["id"]), []).append(ev["sequence_number"])
    return out


class TestStoresFixedSeedProperties(unittest.TestCase):
    def test_properties_with_fixed_seed(self):
        print(f"\nproperty test: seed={SEED} iterations={ITERATIONS} steps_per_stream={STEPS} command={COMMAND}")
        rng = random.Random(SEED)
        accepted = rejected = replays = conflicts = activations = refusals = events = 0
        for i in range(ITERATIONS):
            ops = draw(rng)
            modes = rng.choice(((), ("raise",), ("lossy", "twice"), ("flaky", "raise", "lossy")))
            with self.subTest(iteration=i, sinks=modes):
                clean = run(ops, (), True)                           # invariants S1 to S3, S5 to S8
                noisy = run(ops, modes, False)                       # INV-S4: the same stream with failing sinks
                self.assertEqual(clean.trace, noisy.trace, "INV-S4: results and states do not depend on the sinks")
                self.assertEqual(clean.hist.read(), noisy.hist.read(), "INV-S4: history does not depend on the sinks")
                self.assertEqual(clean.pub.published(), noisy.pub.published(), "INV-S3/S4: numbering does not depend on the sinks")
                again = replay(clean.journal, lambda b: LifecycleEngine(None, b, None))       # INV-S10
                self.assertEqual(again.commands(), clean.raw.commands(), "INV-S10: replay reproduces command outcomes")
                recs = clean.hist.read()
                accepted += sum(r["submission_result"] == "ACCEPTED" for r in recs)
                rejected += sum(r["submission_result"] == "REJECTED" for r in recs)
                replays += sum(len(r["replays"]) for r in recs)
                conflicts += sum(r["validation_result"]["code"] == "REQUEST_ID_CONFLICT" for r in recs)
                activations += sum(t[0] == "activate" and t[1] == "ACTIVATED" for t in clean.trace if t[0] == "activate")
                refusals += sum(t[1] == "REFUSED" for t in clean.trace if t[0] in ("activate", "rollback"))
                events += len(clean.pub.published())
        self.assertGreater(accepted, ITERATIONS, "the generator accepts commands")
        self.assertGreater(rejected, ITERATIONS // 2, "the generator makes rejections")
        self.assertGreater(replays, ITERATIONS // 4, "the generator makes replays")
        self.assertGreater(conflicts, ITERATIONS // 8, "the generator makes conflicts")
        self.assertGreater(activations, ITERATIONS // 2, "the generator activates configurations")
        self.assertGreater(refusals, ITERATIONS // 4, "the generator provokes refusals")
        print(f"property test: accepted={accepted} rejected={rejected} replays={replays} conflicts={conflicts} "
              f"activations={activations} refusals={refusals} events={events}")


if __name__ == "__main__":
    unittest.main()
