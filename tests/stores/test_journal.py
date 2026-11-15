"""CT-DET-02 (contract 3.3 and 15), KOS-MOTION-005 PR-06: replay from the recorded inputs and the recorded
configuration reproduces command outcomes. The input journal is an implementation aid (question Q-4), not a
contract field. Deterministic and offline. Software evidence only, never physical or safety validation."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "lifecycle"))
import lifecycle_support as S  # noqa: E402
from kritva_motion.lifecycle import LifecycleEngine  # noqa: E402
from kritva_motion.stores import (CommandHistory, ConfigurationRegistry, Coordinator, EventPublisher,  # noqa: E402
                                  IdempotencyStore, InputJournal, RecordingEngine, ReplayMismatch, replay)

A, B = "client-A", "client-B"


def cfg(version, **over):
    c = copy.deepcopy(S.base.CONFIG)
    c["config_version"] = version
    c["joints"][0] = S.base.joint(**over)
    return c


def fresh_engine(backend):
    return LifecycleEngine(None, backend, None)


def build():
    journal = InputJournal(S.base.BACKEND)
    e = RecordingEngine(fresh_engine(copy.deepcopy(S.base.BACKEND)), journal)
    store, hist = IdempotencyStore(20000), CommandHistory(100000)
    reg = ConfigurationRegistry(e, S.base.CAPS, store)
    co = Coordinator(e, store, hist, EventPublisher())
    return e, reg, co, hist, journal


def scenario(e, reg, co):
    """Two configuration versions, a completed move, a cancelled move, a fault and a rejection."""
    assert reg.activate(cfg("1", settling_duration_ms=100), 0)["outcome"] == "ACTIVATED"
    co.observe(e.status_report("joint-1", "IDLE", 0, 0, "u0"))
    co.observe(e.feedback("joint-1", S.sample(0.0), 0, "u0"))
    co.observe(e.status_report("joint-p", "IDLE", 0, 0, "u0"))
    co.observe(e.feedback("joint-p", S.sample(0.0), 0, "u0"))
    c1 = co.submit(A, S.pos_cmd(0.5), 10, "u10").command_id
    co.observe(e.execution_started(c1, "ref-" + c1, 20, "u20"))
    assert reg.activate(cfg("2", settling_duration_ms=300), 25)["outcome"] == "ACTIVATED"   # applies to later commands only
    co.observe(e.feedback("joint-1", S.sample(0.5), 30, "u30"))
    co.observe(e.feedback("joint-1", S.sample(0.5), 130, "u130"))                              # version 1 command completes
    co.submit(A, S.pos_cmd(5.0, client_request_id="bad"), 140, "u140")                          # rejected
    co.observe(e.feedback("joint-p", S.sample(0.0), 150, "u150"))
    c2 = co.submit(B, S.pos_cmd(0.2, "joint-p", unit="m"), 150, "u150").command_id
    co.observe(e.execution_started(c2, "ref-" + c2, 151, "u151"))
    co.observe(e.terminate(c2, "CANCEL_REQUESTED", 160, "u160"))
    co.observe(e.termination_request_accepted(c2, "ref-" + c2, 161, "u161"))
    co.observe(e.termination_confirmed(c2, "ref-" + c2, 170, "u170"))
    co.observe(e.joint_fault("joint-1", "TRACKING_ERROR", 180, "u180"))
    co.observe(e.tick(200, "u200"))
    return c1, c2


class TestReplay(unittest.TestCase):
    def test_CT_DET_02(self):
        """Replay from the recorded inputs and configuration reproduces the command outcomes (3.3, 15)."""
        e, reg, co, hist, journal = build()
        c1, c2 = scenario(e, reg, co)
        original = e._engine
        self.assertEqual((original.command(c1)["state"], original.command(c1)["reason_code"]), ("COMPLETED", "GOAL_REACHED"))
        self.assertEqual((original.command(c1)["config_version"], original.command(c2)["config_version"]), ("1", "2"))
        again = replay(journal, fresh_engine)
        self.assertEqual(again.commands(), original.commands())                  # states, reasons, transitions, version, digest
        for jid in ("joint-1", "joint-p"):
            self.assertEqual(again.faults(jid), original.faults(jid))
            self.assertEqual(again.joint_state(jid, 200), original.joint_state(jid, 200))
            self.assertEqual(again.joint_transitions(jid), original.joint_transitions(jid))
        # the replayed outcomes are the ones the history recorded
        for rec in hist.accepted():
            c = again.command(rec["command_id"])
            self.assertEqual(rec["result"], {"state": c["state"], "reason_code": c["reason_code"]})
            self.assertEqual((rec["config_version"], rec["config_digest"]), (c["config_version"], c["config_digest"]))
        # and the replay itself is repeatable
        self.assertEqual(replay(journal, fresh_engine).commands(), again.commands())


class TestJournalNegativeCases(unittest.TestCase):
    def test_the_recorded_configuration_matters(self):
        e, reg, co, hist, journal = build()
        scenario(e, reg, co)
        entries = journal.entries()
        altered = InputJournal(S.base.BACKEND)
        for x in entries:
            args = copy.deepcopy(x["args"])
            if x["method"] == "install_configuration" and args[0]["config_version"] == "1":
                args[0]["joints"][0]["settling_duration_ms"] = 5000        # a different window: the move no longer settles
            altered.append(x["method"], args, x["kwargs"], x["raised"])
        other = replay(altered, fresh_engine)
        self.assertNotEqual(other.commands(), e._engine.commands())

    def test_a_missing_input_changes_the_outcome(self):
        e, reg, co, hist, journal = build()
        c1, _ = scenario(e, reg, co)
        short = InputJournal(S.base.BACKEND)
        for x in journal.entries():
            if not (x["method"] == "feedback" and x["args"][2] == 130):
                short.append(x["method"], x["args"], x["kwargs"], x["raised"])
        self.assertNotEqual(replay(short, fresh_engine).command(c1)["state"], "COMPLETED")

    def test_an_input_that_raised_is_recorded_and_must_raise_again(self):
        journal = InputJournal(S.base.BACKEND)
        e = RecordingEngine(fresh_engine(copy.deepcopy(S.base.BACKEND)), journal)
        e.install_configuration(copy.deepcopy(S.base.CONFIG), "d1")
        e.tick(10)
        with self.assertRaises(Exception):
            e.tick(5)                                                         # the monotonic reading went backwards
        self.assertEqual([x["raised"] for x in journal.entries()], [None, None, "ClockError"])
        replay(journal, fresh_engine)                                         # raises the same type again: no mismatch
        bad = InputJournal(S.base.BACKEND)
        bad.append("tick", (10,), {}, "ClockError")                           # recorded as raising, but it would not
        with self.assertRaises(ReplayMismatch):
            replay(bad, fresh_engine)

    def test_queries_are_not_journaled_and_entries_are_copies(self):
        journal = InputJournal(S.base.BACKEND)
        e = RecordingEngine(fresh_engine(copy.deepcopy(S.base.BACKEND)), journal)
        e.install_configuration(copy.deepcopy(S.base.CONFIG), "d1")
        e.commands()
        e.active_configuration_version()
        self.assertEqual(len(journal), 1)
        got = journal.entries()
        got[0]["args"][0]["config_version"] = "tampered"
        self.assertEqual(journal.entries()[0]["args"][0]["config_version"], "1")
        self.assertFalse(any(n in dir(journal) for n in ("update", "overwrite", "delete", "remove", "clear")))


if __name__ == "__main__":
    unittest.main()
