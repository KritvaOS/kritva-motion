"""Tests of the event streams, sequence numbers and the abstract event sink (contract 14), KOS-MOTION-005 PR-05.

The five CT-EV methods are the single executable tests named by the IN_SCOPE manifest entries for CT-EV-01
to CT-EV-05 (method name = ID with hyphens replaced by underscores). The sinks and the reference consumer
live here, in the tests, not in `src`: the consumer that tolerates duplicates and detects gaps (14.4) is part
of the evidence, not of the product. Deterministic and offline: no transport, no clock, no randomness.
Software evidence only, never physical or safety validation.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "lifecycle"))
import lifecycle_support as S  # noqa: E402
from kritva_motion.lifecycle import LifecycleEngine  # noqa: E402
from kritva_motion.stores import (CommandHistory, ConfigurationRegistry, Coordinator, EventPublisher,  # noqa: E402
                                  IdempotencyStore)

SCHEMA = json.loads((ROOT / "contract" / "motion-event.schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
A = "client-A"
KIND_OF = {"COMMAND_STATE_CHANGED": "command", "COMMAND_PHASE_CHANGED": "command",
           "JOINT_STATE_CHANGED": "joint", "FEEDBACK_STATUS_CHANGED": "joint", "JOINT_FAULT_RAISED": "joint",
           "JOINT_FAULT_CLEARED": "joint", "BACKEND_HEALTH_CHANGED": "backend", "BACKEND_FAULT_RAISED": "backend",
           "BACKEND_FAULT_CLEARED": "backend"}


class ListSink:
    def __init__(self):
        self.events = []

    def deliver(self, event):
        self.events.append(event)


class AtLeastOnceSink(ListSink):
    """Delivers every event twice, as an at-least-once transport may (14.4)."""
    def deliver(self, event):
        self.events.append(event)
        self.events.append(copy.deepcopy(event))


class LossySink(ListSink):
    """A best-effort transport that drops the events its predicate names."""
    def __init__(self, drop):
        super().__init__()
        self.drop = drop

    def deliver(self, event):
        if not self.drop(event):
            self.events.append(event)


class RaisingSink:
    def deliver(self, event):
        raise RuntimeError("subscriber went away")


class Consumer:
    """The reference consumer: tolerates duplicates, detects skipped sequence numbers (gaps) per stream."""
    def __init__(self):
        self.seen, self.last, self.gaps, self.duplicates, self.state = set(), {}, [], 0, {}

    def receive(self, ev):
        if ev["event_id"] in self.seen:
            self.duplicates += 1
            return
        self.seen.add(ev["event_id"])
        key, got = (ev["stream"]["kind"], ev["stream"]["id"]), ev["sequence_number"]
        expect = self.last.get(key, 0) + 1
        if got > expect:
            self.gaps.append((key, expect, got - 1))
        if got >= expect:
            self.last[key] = got
            if ev["event_type"] == "COMMAND_STATE_CHANGED":
                self.state[ev["stream"]["id"]] = ev["data"]["to"]

    def tail_loss(self, publisher):
        """Streams whose last published number is beyond the last seen one: lost at the end, invisible to
        sequence continuity, found by comparing with `last_sequence_number` of the status query (14.1)."""
        return sorted(k for k in publisher._next if publisher.last_sequence_number(*k) > self.last.get(k, 0))


def build(sinks=()):
    e = LifecycleEngine(None, copy.deepcopy(S.base.BACKEND), None)
    store, pub = IdempotencyStore(20000), EventPublisher(sinks)
    assert ConfigurationRegistry(e, S.base.CAPS, store).activate(copy.deepcopy(S.base.CONFIG), 0)["outcome"] == "ACTIVATED"
    S.ready(e, "joint-1", t=0)
    S.ready(e, "joint-p", t=0)
    return e, Coordinator(e, store, CommandHistory(100000), pub), pub


def drive(e, co):
    """A fixed input sequence touching the command, joint and backend streams. Returns the command id."""
    cid = co.submit(A, S.pos_cmd(0.5), 10, "2026-11-15T00:00:10Z").command_id
    co.observe(e.execution_started(cid, e.command(cid)["backend_reference"], 20, "2026-11-15T00:00:20Z"))
    co.observe(e.feedback("joint-1", S.sample(0.5), 30, "2026-11-15T00:00:30Z"))
    co.observe(e.feedback("joint-1", S.sample(0.5), 130, "2026-11-15T00:00:40Z"))
    co.observe(e.joint_fault("joint-p", "TRACKING_ERROR", 140, "2026-11-15T00:00:50Z"))
    co.observe(e.backend_fault("BACKEND_COMMUNICATION_LOSS", 150, "2026-11-15T00:00:55Z", joints=["joint-1"]))
    co.observe(e.backend_fault_cleared(160, "2026-11-15T00:01:00Z"))
    return cid


def per_stream(events):
    out = {}
    for ev in events:
        out.setdefault((ev["stream"]["kind"], ev["stream"]["id"]), []).append(ev["sequence_number"])
    return out


class TestEventConformance(unittest.TestCase):
    def test_CT_EV_01(self):
        """Sequence numbers increase by one per stream and gaps are detectable (14.3, 14.4)."""
        sink = ListSink()
        e, co, pub = build([sink])
        cid = drive(e, co)
        log = pub.published()
        self.assertGreater(len(log), 8)
        streams = per_stream(log)
        self.assertGreaterEqual(len(streams), 4)             # a command, two joints and the backend stream
        for key, seqs in streams.items():
            with self.subTest(stream=key):
                self.assertEqual(seqs, list(range(1, len(seqs) + 1)))      # 1, 2, 3 ... with no repeat and no gap
                self.assertEqual(pub.last_sequence_number(*key), len(seqs))
        ids = [ev["event_id"] for ev in log]
        self.assertEqual(len(ids), len(set(ids)))                          # unique event_id
        for ev in log:
            self.assertEqual(list(VALIDATOR.iter_errors(ev)), [], ev)      # every event fits motion-event.schema.json
        self.assertEqual(sink.events, log)                                  # a healthy sink sees them all, in order
        # a gap is a skipped number
        c = Consumer()
        for ev in log:
            if not (ev["stream"] == {"kind": "command", "id": cid} and ev["sequence_number"] == 2):
                c.receive(ev)
        self.assertEqual(c.gaps, [(("command", cid), 2, 2)])

    def test_CT_EV_02(self):
        """Duplicate delivery is tolerated and the status query is authoritative after loss (14.4)."""
        twice = AtLeastOnceSink()
        e, co, pub = build([twice])
        cid = drive(e, co)
        c = Consumer()
        for ev in twice.events:
            c.receive(ev)
        self.assertEqual(c.duplicates, len(pub.published()))
        self.assertEqual(c.gaps, [])
        self.assertEqual(c.state[cid], "COMPLETED")
        # loss: the terminal event never arrives; the query still gives the true state
        lossy = LossySink(lambda ev: ev["event_type"] == "COMMAND_STATE_CHANGED" and ev["data"]["to"] == "COMPLETED")
        e2, co2, pub2 = build([lossy])
        cid2 = drive(e2, co2)
        c2 = Consumer()
        for ev in lossy.events:
            c2.receive(ev)
        self.assertEqual(c2.state[cid2], "RUNNING")                          # events alone are behind
        status = co2.command_status(cid2)
        self.assertEqual(status["state"], "COMPLETED")                       # the query is authoritative (14.1, 14.5)
        self.assertEqual(status["last_sequence_number"], pub2.last_sequence_number("command", cid2))
        self.assertEqual(e2.joint_state("joint-1", 160)["joint_id"], "joint-1")

    def test_CT_EV_03(self):
        """Execution continues when no subscriber is attached or notification delivery fails (14.2)."""
        e0, co0, pub0 = build()                                              # no subscriber at all
        drive(e0, co0)
        good = ListSink()
        e1, co1, pub1 = build([RaisingSink(), good])                         # a failing sink first, a good one after
        drive(e1, co1)
        self.assertEqual(e0.commands(), e1.commands())                       # execution is identical
        for jid in ("joint-1", "joint-p"):
            self.assertEqual(e0.joint_state(jid, 160), e1.joint_state(jid, 160))
        self.assertEqual(pub0.published(), pub1.published())                 # numbering is the same whatever the sinks do
        self.assertEqual(pub0.delivery_errors(), [])
        errs = pub1.delivery_errors()
        self.assertEqual(len(errs), len(pub1.published()))
        self.assertTrue(all(x["sink"] == 0 and x["error"] == "RuntimeError" for x in errs))
        self.assertEqual(good.events, pub1.published())                      # a failing sink does not starve the next one
        self.assertEqual(e1.command("cmd-1")["state"], "COMPLETED")

    def test_CT_EV_04(self):
        """Joint and backend changes appear in their own streams, not in command streams (14.3)."""
        e, co, pub = build()
        cid = drive(e, co)
        log = pub.published()
        for ev in log:
            self.assertEqual(ev["stream"]["kind"], KIND_OF[ev["event_type"]], ev)
        kinds = {}
        for ev in log:
            kinds.setdefault(ev["stream"]["kind"], set()).add(ev["event_type"])
        self.assertEqual(kinds["command"], {"COMMAND_STATE_CHANGED", "COMMAND_PHASE_CHANGED"})
        self.assertIn("JOINT_FAULT_RAISED", kinds["joint"])
        self.assertTrue({"BACKEND_FAULT_RAISED", "BACKEND_FAULT_CLEARED"} <= kinds["backend"])
        self.assertTrue(kinds["backend"] <= {"BACKEND_HEALTH_CHANGED", "BACKEND_FAULT_RAISED", "BACKEND_FAULT_CLEARED"})
        self.assertEqual(sorted(k for k in per_stream(log) if k[0] == "backend"), [("backend", "backend")])
        self.assertIn(("command", cid), per_stream(log))
        self.assertTrue(all(k[1].startswith("cmd-") for k in per_stream(log) if k[0] == "command"))
        self.assertTrue(all(k[1].startswith("joint-") for k in per_stream(log) if k[0] == "joint"))

    def test_CT_EV_05(self):
        """Best-effort transports: gaps are seen only where sequence continuity breaks, and state queries
        recover what was lost (14.4)."""
        lossy = LossySink(lambda ev: ev["stream"]["kind"] == "command" and ev["sequence_number"] in (2, 5))
        e, co, pub = build([lossy])
        cid = drive(e, co)
        self.assertEqual(pub.last_sequence_number("command", cid), 5)
        c = Consumer()
        for ev in lossy.events:
            c.receive(ev)
        self.assertEqual(c.gaps, [(("command", cid), 2, 2)])                 # the middle loss is visible
        self.assertEqual(c.tail_loss(pub), [("command", cid)])               # the last loss is not, until a status query
        self.assertEqual(c.state[cid], "RUNNING")
        status = co.command_status(cid)
        self.assertEqual((status["state"], status["last_sequence_number"]), ("COMPLETED", 5))
        self.assertGreater(status["last_sequence_number"], c.last[("command", cid)])   # the query reveals what was lost
        # no loss of the other streams: their continuity holds and the consumer sees no gap there
        self.assertEqual([g for g in c.gaps if g[0] != ("command", cid)], [])


class TestPublisherNegativeCases(unittest.TestCase):
    def test_a_result_is_taken_once(self):
        e, co, pub = build()
        res = e.joint_fault("joint-p", "TRACKING_ERROR", 5, "u5")
        co.observe(res)
        n = len(pub.published())
        co.observe(res)
        self.assertEqual(len(pub.published()), n)

    def test_command_events_carry_the_originating_client(self):
        e, co, pub = build()
        cid = drive(e, co)
        cmd_events = [ev for ev in pub.published() if ev["stream"]["kind"] == "command"]
        self.assertTrue(cmd_events and all(ev["client_id"] == A for ev in cmd_events))
        self.assertTrue(all("client_id" not in ev for ev in pub.published() if ev["stream"]["kind"] != "command"))
        self.assertEqual(co.command_status(cid)["last_sequence_number"], len(cmd_events))

    def test_sequence_stays_contiguous_when_every_sink_fails(self):
        e, co, pub = build([RaisingSink(), RaisingSink()])
        drive(e, co)
        for key, seqs in per_stream(pub.published()).items():
            self.assertEqual(seqs, list(range(1, len(seqs) + 1)), key)
        self.assertEqual(len(pub.delivery_errors()), 2 * len(pub.published()))

    def test_published_events_and_logs_are_copies(self):
        e, co, pub = build()
        drive(e, co)
        log = pub.published()
        log[0]["event_type"] = "TAMPERED"
        log[0]["data"]["x"] = 1
        self.assertNotEqual(pub.published()[0]["event_type"], "TAMPERED")
        sink = ListSink()
        pub2 = EventPublisher([sink])
        out = pub2.publish([{"stream": {"kind": "joint", "id": "joint-1"}, "event_type": "JOINT_STATE_CHANGED",
                             "occurred_at": "u", "data": {"a": 1}}])
        out[0]["data"]["a"] = 2
        sink.events[0]["data"]["a"] = 3
        self.assertEqual(pub2.published()[0]["data"], {"a": 1})

    def test_empty_publish_and_independent_publishers(self):
        p1, p2 = EventPublisher(), EventPublisher()
        self.assertEqual(p1.publish([]), [])
        ev = {"stream": {"kind": "backend", "id": "backend"}, "event_type": "BACKEND_FAULT_RAISED",
              "occurred_at": "u", "data": {"code": "X"}}
        p1.publish([ev])
        p1.publish([ev])
        self.assertEqual((p1.last_sequence_number("backend", "backend"), p2.last_sequence_number("backend", "backend")), (2, 0))

    def test_the_source_has_no_event_transport_or_sink_implementation(self):
        src = (ROOT / "src" / "kritva_motion" / "stores").glob("*.py")
        text = "\n".join(p.read_text(encoding="utf-8") for p in src)
        for banned in ("import socket", "import rclpy", "paho", "grpc", "import http", "import urllib", "open(", "time.time",
                       "datetime.now", "import subprocess"):
            self.assertNotIn(banned, text, banned)
        self.assertEqual(text.count("def deliver("), 1)        # only the abstract port declares it


if __name__ == "__main__":
    unittest.main()
