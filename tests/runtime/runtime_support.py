"""Fixtures of the driver tests (KOS-MOTION-004 PR-04): an engine, the stores, a scripted S1 simulator and the
driver, all deterministic and offline. Software evidence only."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "lifecycle"))
import lifecycle_support as S  # noqa: E402
from kritva_motion.backend.simulator import Simulator, default_declaration  # noqa: E402
from kritva_motion.lifecycle import LifecycleEngine  # noqa: E402
from kritva_motion.lifecycle import model as m  # noqa: E402
from kritva_motion.runtime import Driver  # noqa: E402
from kritva_motion.stores import (CommandHistory, ConfigurationRegistry, Coordinator, EventPublisher,  # noqa: E402
                                  IdempotencyStore)

A = "client-A"
J1, JP = "joint-1", "joint-p"


class ListSink:
    def __init__(self):
        self.events = []

    def deliver(self, event):
        self.events.append(event)


def declaration(**caps):
    d = default_declaration([J1, "joint-c", JP])
    d["joint_limits"] = copy.deepcopy(S.base.LIMITS)
    d["capabilities"].update(caps)
    return d


def config():
    """joint-1 with optional feedback (silence is a degradation, not a fault) so that long waits stay about the backend."""
    return S.config(feedback_required=False, feedback_timeout_policy="DEGRADE")


def joint_script(**over):
    base = {"dispatch": {"answer": "accept", "start": {"after_ms": 5}},
            "termination": {"answer": "accept", "confirm": {"after_ms": 30}}}
    base.update(over)
    return base


def build(script=None, decl=None, backend=None):
    """Returns a namespace-like tuple: engine, coordinator, publisher, sink, simulator, driver."""
    sim = Simulator(script if script is not None else {"joints": {J1: joint_script(), JP: joint_script()}},
                    decl or declaration())
    be = backend if backend is not None else sim
    e = LifecycleEngine(None, sim.describe_capabilities(), None)
    store, sink = IdempotencyStore(20000), ListSink()
    pub = EventPublisher([sink])
    assert ConfigurationRegistry(e, S.base.CAPS, store).activate(copy.deepcopy(config()), 0)["outcome"] == "ACTIVATED"
    S.ready(e, J1, t=0)
    S.ready(e, JP, t=0)
    co = Coordinator(e, store, CommandHistory(100000), pub)
    return e, co, pub, sink, sim, Driver(e, co, be)


def view(e, cid):
    c = e.command(cid)
    return c["state"], c["phase"], c["reason_code"]


def kinds(sink, kind=None):
    return [(ev["event_type"], ev["stream"]["id"]) for ev in sink.events
            if kind is None or ev["stream"]["kind"] == kind]


class Drifting:
    """A backend that wraps another and changes what it declares after the first `good` calls of
    describe_capabilities (the declaration can change after admission, 17.2). It counts the operations it received."""

    def __init__(self, inner, mutate, good=1):
        self._inner, self._mutate, self._good, self._calls = inner, mutate, good, 0
        self.received = []

    def describe_capabilities(self):
        self._calls += 1
        d = self._inner.describe_capabilities()
        if self._calls > self._good:
            self._mutate(d)
        return d

    def health(self):
        return self._inner.health()

    def poll(self, now_ms):
        return self._inner.poll(now_ms)

    def dispatch(self, request, now_ms):
        self.received.append("dispatch")
        return self._inner.dispatch(request, now_ms)

    def request_hold(self, ref, joint_id, now_ms):
        self.received.append("request_hold")
        return self._inner.request_hold(ref, joint_id, now_ms)

    def release_hold(self, ref, joint_id, now_ms):
        self.received.append("release_hold")
        return self._inner.release_hold(ref, joint_id, now_ms)

    def request_termination(self, ref, cause, now_ms, target=None):
        self.received.append("request_termination")
        return self._inner.request_termination(ref, cause, now_ms, target=target)
