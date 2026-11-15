"""A scripted, deterministic contract simulator at level S1 (contract 17.7, KOS-MOTION-004 PR-03).

S1 is a contract simulation: it answers operations and produces reports exactly as its script says, on the
caller's injected monotonic clock. It models no joint dynamics and no kinematics, uses no randomness, no system
clock, no thread and no I/O. Every output (answer, report, declaration) is marked `simulated`: a result from this
backend is software evidence and is never physical validation (17.7). A completed simulated move shows only that
the driver reacted to scripted reports as the contract says; it says nothing about any actuator.

The same script and the same calls give the same answers and reports byte for byte. Anything the script does not
mention does not happen: an operation with no scripted answer is rejected `NOT_SCRIPTED`, and a report that is
not scripted is never produced. The script is checked at construction and an inconsistent one is refused.

Script (plain data; all delays are milliseconds of the caller's clock, counted from the call that causes them;
`at_ms` values are absolute readings of that clock)::

    {"joints": {joint_id: {
         "dispatch":    {"answer": "accept"} or {"answer": "reject", "reason": text},
                        optional "start": None (never reported) | {"after_ms": n} | {"reject": text, "after_ms": n},
         "termination": {"answer": "accept"} or {"answer": "refuse", "reason": text},
                        optional "confirm": None (never) | {"after_ms": n, "reference": other, "target": other_joint},
         "hold":        {"answer": "accept"} or {"answer": "refuse", "reason": text},
                        optional "start": None | {"after_ms": n},       # the HOLD's execution_started
                        optional "confirm": None | {"after_ms": n},
                        optional "release": {"answer": "accept" | "refuse", "reason": text,
                                             "confirm": None | {"after_ms": n} | {"after_ms": n, "fail": True, "reason": text}},
         "feedback":    [{"at_ms": n, "position": x or None, "velocity": y (optional),
                          "validity": "VALID" | "INVALID"}, ...]}},        # non-decreasing at_ms
     "events": [{"at_ms": n, "kind": "health", "health": value} |
                {"at_ms": n, "kind": "fault", "code": backend fault code, "joints": [ids] (optional)} |
                {"at_ms": n, "kind": "fault_cleared", "code": backend fault code (optional)}, ...]}

The `reference` and `target` of a termination confirmation are for the partial and unknown outcomes of 17.5:
the report names another reference or another target, which Motion must not accept as the confirmation.
"""
import copy
import math

from kritva_motion.backend.capabilities import HEALTH_VALUES, ID_PATTERN, Problem, validate_declaration
from kritva_motion.backend.reports import (BACKEND_FAULT_CODES, FEEDBACK_VALIDITY, DispatchAnswer, TerminationAnswer,
                                           make_report)

JOINT_KEYS = ("dispatch", "termination", "hold", "feedback")
OPERATION_MODE = {"SET_POSITION": "position", "SET_VELOCITY": "velocity"}


class ScriptError(ValueError):
    """The script or the declaration given to the simulator is inconsistent."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(str(p) for p in self.problems))


class ClockError(ValueError):
    """The supplied monotonic reading is not a finite number or went backwards."""


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _delay(v):
    return _num(v) and v >= 0


def _text(v):
    return isinstance(v, str) and bool(v.strip())


def default_declaration(joint_ids):
    """A complete S1 declaration for the given joints: every 17.2 item declared, a simulated, synchronized clock."""
    return {
        "supported_target_types": ["joint"],
        "health": "AVAILABLE",
        "capabilities": {
            "supported_joint_types": ["revolute", "prismatic"],
            "supported_modes": ["position", "velocity"],
            "controlled_stop": True, "position_hold": True, "execution_cancellation": True,
            "feedback": {"position": True, "velocity": True},
            "feedback_rate_hz": {"min": 10, "max": 100}, "feedback_rate_declared_absent": False,
            "max_concurrent_executions": 8,
        },
        "joint_limits": {j: {"position_min": -1.5, "position_max": 1.5, "velocity_max": 1.0} for j in joint_ids},
        "clock": {"domain": "simulated-monotonic", "synchronized": True},
    }


def _check_answer(spec, path, out):
    if not isinstance(spec, dict) or spec.get("answer") not in ("accept", "reject", "refuse"):
        out.append(Problem(path, "needs an `answer` of accept, reject or refuse"))
        return False
    if spec["answer"] != "accept" and not _text(spec.get("reason")):
        out.append(Problem(f"{path}.reason", "is required when the answer is not accept"))
    return True


def _check_after(spec, path, out, extra=()):
    if not isinstance(spec, dict) or not _delay(spec.get("after_ms")):
        out.append(Problem(path, "needs `after_ms`, a finite number of at least 0"))
        return
    for key in ("reference", "target", "reject", "fail", "reason"):
        if key in spec and key not in extra:
            out.append(Problem(f"{path}.{key}", "is not allowed here"))


def _check_script(script, declaration):
    out = []
    if not isinstance(script, dict) or set(script) - {"joints", "events"}:
        return [Problem("", "the script must be an object with only `joints` and `events`")]
    caps = declaration.get("capabilities", {})
    limits = declaration.get("joint_limits", {})
    joints = script.get("joints", {})
    if not isinstance(joints, dict):
        return [Problem("joints", "must be an object")]
    for jid, spec in joints.items():
        base = f"joints.{jid}"
        if jid not in limits:
            out.append(Problem(base, "is not a joint of the declaration"))
        if not isinstance(spec, dict) or set(spec) - set(JOINT_KEYS):
            out.append(Problem(base, f"must be an object with only {list(JOINT_KEYS)}"))
            continue
        d = spec.get("dispatch")
        if d is not None and _check_answer(d, f"{base}.dispatch", out):
            if d["answer"] == "reject" and "start" in d:
                out.append(Problem(f"{base}.dispatch.start", "cannot be scripted for a rejected dispatch"))
            st = d.get("start")
            if st is not None:
                if isinstance(st, dict) and "reject" in st:
                    if not _text(st["reject"]):
                        out.append(Problem(f"{base}.dispatch.start.reject", "must be a non-empty reason"))
                    _check_after(st, f"{base}.dispatch.start", out, extra=("reject",))
                else:
                    _check_after(st, f"{base}.dispatch.start", out)
        t = spec.get("termination")
        if t is not None and _check_answer(t, f"{base}.termination", out):
            if t["answer"] == "refuse" and "confirm" in t:
                out.append(Problem(f"{base}.termination.confirm", "cannot be scripted for a refused request"))
            if t["answer"] == "accept" and caps.get("controlled_stop") is not True:
                out.append(Problem(f"{base}.termination", "accepts termination but the declaration has no controlled stop"))
            c = t.get("confirm")
            if c is not None:
                _check_after(c, f"{base}.termination.confirm", out, extra=("reference", "target"))
                if isinstance(c, dict) and "reference" in c and not _text(c["reference"]):
                    out.append(Problem(f"{base}.termination.confirm.reference", "must be a non-empty string"))
                if isinstance(c, dict) and "target" in c and not (isinstance(c["target"], str) and ID_PATTERN.match(c["target"])):
                    out.append(Problem(f"{base}.termination.confirm.target", "must be a joint id"))
        h = spec.get("hold")
        if h is not None:
            if caps.get("position_hold") is not True:
                out.append(Problem(f"{base}.hold", "is scripted but the declaration has no position hold"))
            if _check_answer(h, f"{base}.hold", out):
                for key in ("start", "confirm"):
                    if h.get(key) is not None:
                        _check_after(h[key], f"{base}.hold.{key}", out)
                r = h.get("release")
                if r is not None and _check_answer(r, f"{base}.hold.release", out):
                    rc = r.get("confirm")
                    if rc is not None:
                        _check_after(rc, f"{base}.hold.release.confirm", out, extra=("fail", "reason"))
                        if isinstance(rc, dict) and rc.get("fail") is True and not _text(rc.get("reason")):
                            out.append(Problem(f"{base}.hold.release.confirm.reason", "is required when `fail` is true"))
        fb = spec.get("feedback")
        if fb is not None:
            if not isinstance(fb, list):
                out.append(Problem(f"{base}.feedback", "must be a list of samples"))
            else:
                if caps.get("feedback", {}).get("position") is not True:
                    out.append(Problem(f"{base}.feedback", "is scripted but the declaration has no position feedback"))
                last = None
                for i, smp in enumerate(fb):
                    sp = f"{base}.feedback[{i}]"
                    if not isinstance(smp, dict) or not _delay(smp.get("at_ms")):
                        out.append(Problem(sp, "needs `at_ms`, a finite number of at least 0"))
                        continue
                    if smp.get("validity") not in FEEDBACK_VALIDITY:
                        out.append(Problem(f"{sp}.validity", f"must be one of {list(FEEDBACK_VALIDITY)}"))
                    elif smp["validity"] == "VALID" and not _num(smp.get("position")):
                        out.append(Problem(f"{sp}.position", "must be a finite number in a VALID sample"))
                    if "velocity" in smp and smp["velocity"] is not None:
                        if not _num(smp["velocity"]):
                            out.append(Problem(f"{sp}.velocity", "must be a finite number or absent"))
                        elif caps.get("feedback", {}).get("velocity") is not True:
                            out.append(Problem(f"{sp}.velocity", "is scripted but the declaration has no velocity feedback"))
                    if last is not None and smp["at_ms"] < last:
                        out.append(Problem(sp, "at_ms is before the previous sample"))
                    last = smp["at_ms"]
    events = script.get("events", [])
    if not isinstance(events, list):
        out.append(Problem("events", "must be a list"))
    else:
        last = None
        for i, ev in enumerate(events):
            p = f"events[{i}]"
            if not isinstance(ev, dict) or not _delay(ev.get("at_ms")):
                out.append(Problem(p, "needs `at_ms`, a finite number of at least 0"))
                continue
            kind = ev.get("kind")
            if kind == "health":
                if ev.get("health") not in HEALTH_VALUES:
                    out.append(Problem(f"{p}.health", f"must be one of {list(HEALTH_VALUES)}"))
            elif kind == "fault":
                if ev.get("code") not in BACKEND_FAULT_CODES:
                    out.append(Problem(f"{p}.code", f"must be one of {list(BACKEND_FAULT_CODES)}"))
            elif kind == "fault_cleared":
                if ev.get("code") is not None and ev["code"] not in BACKEND_FAULT_CODES:
                    out.append(Problem(f"{p}.code", f"must be one of {list(BACKEND_FAULT_CODES)} or absent"))
            else:
                out.append(Problem(f"{p}.kind", "must be health, fault or fault_cleared"))
            for j in ev.get("joints") or []:
                if j not in limits:
                    out.append(Problem(f"{p}.joints", f"{j!r} is not a joint of the declaration"))
            if last is not None and ev["at_ms"] < last:
                out.append(Problem(p, "at_ms is before the previous event"))
            last = ev["at_ms"]
    return out


class Simulator:
    """The S1 contract simulator. Implements the port of `kritva_motion.backend.interface`."""

    def __init__(self, script, declaration=None):
        script = copy.deepcopy(script)
        joints = script.get("joints", {}) if isinstance(script, dict) and isinstance(script.get("joints", {}), dict) else {}
        decl = copy.deepcopy(declaration) if declaration is not None else default_declaration(list(joints))
        problems = validate_declaration(decl)
        if problems:
            raise ScriptError([Problem(f"declaration.{p.path}".rstrip("."), p.message) for p in problems])
        problems = _check_script(script, decl)
        if problems:
            raise ScriptError(problems)
        self._script, self._decl = script, decl
        self._health = decl["health"]
        self._faults = []
        self._last_now = None
        self._seq = 0
        self._queue = []       # (due_ms, seq, kind, payload)
        self._exec = {}        # backend_reference -> {"joint", "kind", "state"}
        for jid, spec in joints.items():
            for smp in spec.get("feedback") or []:
                self._schedule(smp["at_ms"], "feedback", {"joint": jid, "sample": smp})
        for ev in script.get("events", []):
            self._schedule(ev["at_ms"], "event", ev)

    # ---------------------------------------------------------------- internals

    def _advance(self, now_ms):
        if not _num(now_ms):
            raise ClockError("now_ms must be a finite number")
        if self._last_now is not None and now_ms < self._last_now:
            raise ClockError(f"the monotonic reading went backwards ({now_ms} < {self._last_now})")
        self._last_now = now_ms

    def _schedule(self, due_ms, kind, payload):
        self._seq += 1
        self._queue.append((due_ms, self._seq, kind, payload))

    def _spec(self, joint_id, key):
        return (self._script.get("joints", {}).get(joint_id) or {}).get(key)

    def _active_executions(self):
        return sum(1 for e in self._exec.values() if e["kind"] == "dispatch" and e["state"] in ("dispatched", "terminating"))

    def _rejected(self, reason):
        return DispatchAnswer(False, reason=reason, simulated=True)

    # ---------------------------------------------------------------- the port (contract 17.4)

    def describe_capabilities(self):
        d = copy.deepcopy(self._decl)
        d["health"] = self._health
        d["simulated"] = True
        return d

    def dispatch(self, request, now_ms):
        self._advance(now_ms)
        ref = request.get("backend_reference") if isinstance(request, dict) else None
        target = request.get("target") if isinstance(request, dict) else None
        joint = target.get("id") if isinstance(target, dict) else None
        if not _text(ref) or not isinstance(joint, str):
            return self._rejected("MALFORMED_REQUEST")
        if ref in self._exec:
            return self._rejected("DUPLICATE_REFERENCE")
        mode = OPERATION_MODE.get(request.get("operation"))
        if mode is None or mode not in self._decl["capabilities"]["supported_modes"]:
            return self._rejected("UNSUPPORTED_OPERATION")
        if self._health in ("UNAVAILABLE", "FAULTED"):
            return self._rejected("BACKEND_UNAVAILABLE")
        if self._active_executions() >= self._decl["capabilities"]["max_concurrent_executions"]:
            return self._rejected("BACKEND_BUSY")
        spec = self._spec(joint, "dispatch")
        if spec is None:
            return self._rejected("NOT_SCRIPTED")
        if spec["answer"] == "reject":
            return self._rejected(spec["reason"])
        self._exec[ref] = {"joint": joint, "kind": "dispatch", "state": "dispatched"}
        start = spec.get("start")
        if isinstance(start, dict) and "reject" in start:
            self._schedule(now_ms + start["after_ms"], "report", ("execution_rejected", ref, {"reason": start["reject"]}))
        elif isinstance(start, dict):
            self._schedule(now_ms + start["after_ms"], "report", ("execution_started", ref, {}))
        return DispatchAnswer(True, backend_reference=ref, simulated=True)

    def request_termination(self, backend_reference, cause, now_ms, target=None):
        self._advance(now_ms)
        ex = self._exec.get(backend_reference)
        if ex is None and isinstance(target, dict) and target.get("type") == "joint" and isinstance(target.get("id"), str):
            # an attempt that no dispatch created (a STOP with nothing running): the target names the joint
            ex = self._exec[backend_reference] = {"joint": target["id"], "kind": "dispatch", "state": "dispatched"}
        if ex is None:
            return TerminationAnswer(False, reason="UNKNOWN_REFERENCE", simulated=True)
        spec = self._spec(ex["joint"], "termination")
        if spec is None:
            return TerminationAnswer(False, reason="NOT_SCRIPTED", simulated=True)
        if spec["answer"] == "refuse":
            return TerminationAnswer(False, reason=spec["reason"], simulated=True)
        ex["state"] = "terminating"
        c = spec.get("confirm")
        if isinstance(c, dict):
            self._schedule(now_ms + c["after_ms"], "report",
                           ("termination_confirmed", c.get("reference", backend_reference),
                            {"target": {"type": "joint", "id": c.get("target", ex["joint"])}, "of": backend_reference}))
        return TerminationAnswer(True, simulated=True)

    def request_hold(self, backend_reference, joint_id, now_ms):
        self._advance(now_ms)
        if not _text(backend_reference) or not isinstance(joint_id, str):
            return self._rejected("MALFORMED_REQUEST")
        if backend_reference in self._exec:
            return self._rejected("DUPLICATE_REFERENCE")
        if self._decl["capabilities"]["position_hold"] is not True:
            return self._rejected("UNSUPPORTED_OPERATION")
        if self._health in ("UNAVAILABLE", "FAULTED"):
            return self._rejected("BACKEND_UNAVAILABLE")
        spec = self._spec(joint_id, "hold")
        if spec is None:
            return self._rejected("NOT_SCRIPTED")
        if spec["answer"] == "refuse":
            return self._rejected(spec["reason"])
        self._exec[backend_reference] = {"joint": joint_id, "kind": "hold", "state": "holding_requested"}
        st = spec.get("start")
        if isinstance(st, dict):
            self._schedule(now_ms + st["after_ms"], "report", ("execution_started", backend_reference, {}))
        c = spec.get("confirm")
        if isinstance(c, dict):
            self._schedule(now_ms + c["after_ms"], "report", ("hold_confirmed", backend_reference, {"joint": joint_id}))
        return DispatchAnswer(True, backend_reference=backend_reference, simulated=True)

    def release_hold(self, backend_reference, joint_id, now_ms):
        self._advance(now_ms)
        # the reference is the one of the movement that asks for the release (the engine's release_hold request),
        # so it is echoed in the report and never looked up
        if not _text(backend_reference) or not isinstance(joint_id, str):
            return self._rejected("MALFORMED_REQUEST")
        spec = self._spec(joint_id, "hold")
        rel = spec.get("release") if spec else None
        if rel is None:
            return self._rejected("NOT_SCRIPTED")
        if rel["answer"] != "accept":
            return self._rejected(rel["reason"])
        c = rel.get("confirm")
        if isinstance(c, dict):
            if c.get("fail") is True:
                self._schedule(now_ms + c["after_ms"], "report", ("hold_release_failed", backend_reference, {"reason": c["reason"]}))
            else:
                self._schedule(now_ms + c["after_ms"], "report", ("hold_released", backend_reference, {}))
        return DispatchAnswer(True, backend_reference=backend_reference, simulated=True)

    def health(self):
        return {"health": self._health, "faults": sorted(self._faults), "simulated": True}

    def poll(self, now_ms):
        self._advance(now_ms)
        due = sorted((q for q in self._queue if q[0] <= now_ms), key=lambda q: (q[0], q[1]))
        self._queue = [q for q in self._queue if q[0] > now_ms]
        return [self._emit(kind, payload) for _due, _seq, kind, payload in due]

    # ---------------------------------------------------------------- reports

    def _emit(self, kind, payload):
        if kind == "feedback":
            smp, clock = payload["sample"], self._decl["clock"]
            rec = {"validity": smp["validity"], "measured_position": smp.get("position") if smp["validity"] == "VALID" else None,
                   "backend_timestamp": smp["at_ms"], "clock_domain": clock["domain"], "clock_synchronized": clock["synchronized"]}
            if smp.get("velocity") is not None:
                rec["measured_velocity"] = smp["velocity"]
            return make_report("feedback", joint_id=payload["joint"], record=rec, simulated=True)
        if kind == "event":
            ev = payload
            joints = tuple(ev["joints"]) if ev.get("joints") else None
            if ev["kind"] == "health":
                self._health = ev["health"]
                return make_report("health", health=ev["health"], simulated=True)
            if ev["kind"] == "fault":
                if ev["code"] not in self._faults:
                    self._faults.append(ev["code"])
                return make_report("fault", code=ev["code"], joints=joints, simulated=True)
            if ev.get("code") is None:
                self._faults = []
            elif ev["code"] in self._faults:
                self._faults.remove(ev["code"])
            return make_report("fault_cleared", code=ev.get("code"), joints=joints, simulated=True)
        name, ref, extra = payload
        if name == "termination_confirmed":
            ex = self._exec.get(extra["of"])
            if ex is not None and ref == extra["of"] and extra["target"]["id"] == ex["joint"]:
                ex["state"] = "terminated"      # only a confirmation bound to the right reference and target ends it
            return make_report(name, backend_reference=ref, target=extra["target"], simulated=True)
        return make_report(name, backend_reference=ref, simulated=True, **({"reason": extra["reason"]} if "reason" in extra else {}))
