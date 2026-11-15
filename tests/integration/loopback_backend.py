"""A second, deliberately different conforming backend for the swap test (CT-BE-06, KOS-MOTION-004 PR-05).

`LoopbackBackend` implements the same port as the scripted simulator but is built differently: it keeps a device
table with vendor-style identifiers (a bus, a node number, a device path) that it uses in its own diagnostics and
reasons, it holds its pending work as a heap of closures, and it takes a small behaviour profile instead of the
simulator's script. It is a test double that lives under tests/, so the package ships one simulator. Software
evidence only: it models no joint and no hardware.

Its ordering rule is the contract's ("the reports in the order it produced them"): reports due at the same reading
come out in the order they were scheduled. The scenarios avoid ties between reports of different origin.
"""
import copy
import heapq
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from kritva_motion.backend import DispatchAnswer, TerminationAnswer, make_report  # noqa: E402

VENDOR = "ACME-DRV-3000"


class LoopbackBackend:
    def __init__(self, profile, joints, clock_domain, max_concurrent=8, caps=None):
        self._p = copy.deepcopy(profile)
        self._order = itertools.count()
        self._heap = []
        self._devices = {j: {"bus": "can0", "node": 7 + i, "path": f"/dev/ttyUSB{i}", "vendor": VENDOR}
                         for i, j in enumerate(joints)}
        self._active, self._refs, self._health, self._faults = {}, {}, "AVAILABLE", []
        self._clock, self._max, self._caps = clock_domain, max_concurrent, dict(caps or {})
        self._joints = list(joints)
        self._now = None
        self.diagnostics = []          # vendor-flavoured internal log; never public output
        for jid, jp in self._p.get("joints", {}).items():
            for at, pos, valid in jp.get("feedback", []):
                self._later(at, self._feedback_report, jid, at, pos, valid)
        for ev in self._p.get("events", []):
            self._later(ev[0], self._event_report, ev)

    # ---------------------------------------------------------------- internals

    def _later(self, due, fn, *args):
        heapq.heappush(self._heap, (due, next(self._order), fn, args))

    def _dev(self, jid):
        d = self._devices[jid]
        return f"{d['vendor']} {d['bus']}/node{d['node']} {d['path']}"

    def _tick_clock(self, now):
        if self._now is not None and now < self._now:
            raise ValueError("time went backwards")
        self._now = now

    def _feedback_report(self, jid, at, pos, valid):
        rec = {"validity": "VALID" if valid else "INVALID", "measured_position": pos if valid else None,
               "backend_timestamp": at, "clock_domain": self._clock, "clock_synchronized": True}
        return make_report("feedback", joint_id=jid, record=rec)

    def _event_report(self, ev):
        kind = ev[1]
        if kind == "health":
            self._health = ev[2]
            return make_report("health", health=ev[2])
        joints = tuple(ev[3]) if kind == "fault" and ev[3] else None
        if kind == "fault":
            self._faults.append(ev[2])
            return make_report("fault", code=ev[2], joints=joints)
        code = ev[2] if len(ev) > 2 else None
        self._faults = [] if code is None else [f for f in self._faults if f != code]
        return make_report("fault_cleared", code=code)

    def _report(self, name, ref, **kw):
        return make_report(name, backend_reference=ref, **kw)

    def _busy(self):
        return sum(1 for v in self._active.values() if v["kind"] == "move") >= self._max

    # ---------------------------------------------------------------- the port

    def describe_capabilities(self):
        c = {"supported_joint_types": ["revolute", "prismatic"], "supported_modes": ["position", "velocity"],
             "controlled_stop": True, "position_hold": True, "execution_cancellation": True,
             "feedback": {"position": True, "velocity": True}, "feedback_rate_hz": {"min": 10, "max": 100},
             "feedback_rate_declared_absent": False, "max_concurrent_executions": self._max}
        c.update(self._caps)
        return {"supported_target_types": ["joint"], "health": self._health, "capabilities": c,
                "joint_limits": {j: {"no_narrower_limit": True} for j in self._joints},
                "clock": {"domain": self._clock, "synchronized": True}}

    def dispatch(self, request, now_ms):
        self._tick_clock(now_ms)
        ref, jid = request["backend_reference"], request["target"]["id"]
        jp = self._p.get("joints", {}).get(jid, {})
        answer = jp.get("dispatch", ("reject", "not configured"))
        if self._health in ("UNAVAILABLE", "FAULTED") or self._busy() or answer[0] == "reject":
            why = answer[1] if answer[0] == "reject" else f"{self._dev(jid)} busy or unavailable"
            self.diagnostics.append(f"dispatch refused on {self._dev(jid)}: {why}")
            return DispatchAnswer(False, reason=why)
        self._active[ref] = {"joint": jid, "kind": "move"}
        start = jp.get("start")
        if start and start[0] == "ok":
            self._later(now_ms + start[1], lambda: self._report("execution_started", ref))
        elif start and start[0] == "reject":
            self._later(now_ms + start[2], lambda: self._report("execution_rejected", ref, reason=start[1]))
        return DispatchAnswer(True, backend_reference=ref)

    def request_termination(self, backend_reference, cause, now_ms, target=None):
        self._tick_clock(now_ms)
        item = self._active.get(backend_reference)
        if item is None and isinstance(target, dict):
            item = self._active[backend_reference] = {"joint": target["id"], "kind": "move"}
        if item is None:
            return TerminationAnswer(False, reason="unknown reference")
        jid = item["joint"]
        spec = self._p.get("joints", {}).get(jid, {}).get("terminate", ("refuse", "not configured"))
        if spec[0] == "refuse":
            return TerminationAnswer(False, reason=f"{self._dev(jid)}: {spec[1]}")
        if spec[1] is not None:
            self._later(now_ms + spec[1], lambda: self._report(
                "termination_confirmed", backend_reference, target={"type": "joint", "id": jid}))
        return TerminationAnswer(True)

    def request_hold(self, backend_reference, joint_id, now_ms):
        self._tick_clock(now_ms)
        spec = self._p.get("joints", {}).get(joint_id, {}).get("hold")
        if spec is None or spec[0] == "refuse":
            return DispatchAnswer(False, reason=f"{self._dev(joint_id)}: hold refused")
        self._active[backend_reference] = {"joint": joint_id, "kind": "hold"}
        self._later(now_ms + spec[1], lambda: self._report("execution_started", backend_reference))
        self._later(now_ms + spec[2], lambda: self._report("hold_confirmed", backend_reference))
        return DispatchAnswer(True, backend_reference=backend_reference)

    def release_hold(self, backend_reference, joint_id, now_ms):
        self._tick_clock(now_ms)
        spec = self._p.get("joints", {}).get(joint_id, {}).get("release")
        if spec is None or spec[0] == "refuse":
            return DispatchAnswer(False, reason=f"{self._dev(joint_id)}: release refused")
        outcome = spec[1]
        if outcome[0] == "ok":
            self._later(now_ms + outcome[1], lambda: self._report("hold_released", backend_reference))
        else:
            self._later(now_ms + outcome[1], lambda: self._report("hold_release_failed", backend_reference, reason=outcome[2]))
        return DispatchAnswer(True, backend_reference=backend_reference)

    def health(self):
        return {"health": self._health, "faults": sorted(self._faults)}

    def poll(self, now_ms):
        self._tick_clock(now_ms)
        out = []
        while self._heap and self._heap[0][0] <= now_ms:
            _due, _n, fn, args = heapq.heappop(self._heap)
            out.append(fn(*args))
        return out
