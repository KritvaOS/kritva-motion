"""Scenario runner of the integration tests (KOS-MOTION-004 PR-05).

A scenario is plain data: a behaviour `profile` of the backend, optional declaration overrides and a list of
steps (submit, poll, terminate, tick) on the injected clock. The same scenario runs on the scripted S1 simulator
and on the LoopbackBackend; what is compared and scanned is the public output: the published events, the command
records, the status view, the history records, the joint snapshots and the admission answers. Nothing of ours is
mocked: engine, stores, driver and backend are the real ones. Software evidence only."""
import copy
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for sub in ("src", "tests/lifecycle", "tests/runtime", "tests/integration"):
    sys.path.insert(0, str(ROOT / sub))
import runtime_support as T  # noqa: E402
from loopback_backend import LoopbackBackend  # noqa: E402
from kritva_motion.backend.simulator import Simulator  # noqa: E402
from kritva_motion.lifecycle import LifecycleEngine  # noqa: E402
from kritva_motion.runtime import Driver  # noqa: E402
from kritva_motion.stores import (CommandHistory, ConfigurationRegistry, Coordinator, EventPublisher,  # noqa: E402
                                  IdempotencyStore)

S, A, J1, JP = T.S, T.A, T.J1, T.JP
CLOCK = "backend-clock"          # the same declared clock domain on both backends: it is a contract field (13.2)
JOINTS = [J1, "joint-c", JP]

# What the scan looks for in public output (CT-BE-03): vendor, device, bus and address spellings.
FORBIDDEN = [r"acme", r"drv-?3000", r"can\d", r"\bnode\s?\d", r"\bbus\b", r"/dev/", r"tty", r"usb", r"overcurrent",
             r"0x[0-9a-f]{2,}", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b"]


def to_sim_script(profile):
    """Translate the shared behaviour profile into the simulator's script."""
    joints = {}
    for jid, p in profile.get("joints", {}).items():
        j = {}
        d = p.get("dispatch")
        if d:
            j["dispatch"] = {"answer": "accept"} if d[0] == "accept" else {"answer": "reject", "reason": d[1]}
            if d[0] == "accept" and p.get("start"):
                s = p["start"]
                j["dispatch"]["start"] = {"after_ms": s[1]} if s[0] == "ok" else {"reject": s[1], "after_ms": s[2]}
        t = p.get("terminate")
        if t:
            j["termination"] = {"answer": "accept", "confirm": None if t[1] is None else {"after_ms": t[1]}} \
                if t[0] == "accept" else {"answer": "refuse", "reason": t[1]}
        h = p.get("hold")
        if h:
            j["hold"] = {"answer": "accept", "start": {"after_ms": h[1]}, "confirm": {"after_ms": h[2]}} \
                if h[0] == "accept" else {"answer": "refuse", "reason": h[1]}
            r = p.get("release")
            if r and r[0] == "accept":
                o = r[1]
                j["hold"]["release"] = {"answer": "accept", "confirm": {"after_ms": o[1]} if o[0] == "ok" else
                                        {"after_ms": o[1], "fail": True, "reason": o[2]}}
            elif r:
                j["hold"]["release"] = {"answer": "refuse", "reason": r[1]}
        if p.get("feedback"):
            j["feedback"] = [{"at_ms": at, "position": pos, "validity": "VALID" if ok else "INVALID"}
                             if ok else {"at_ms": at, "position": None, "validity": "INVALID"}
                             for at, pos, ok in p["feedback"]]
        joints[jid] = j
    events = []
    for ev in profile.get("events", []):
        if ev[1] == "health":
            events.append({"at_ms": ev[0], "kind": "health", "health": ev[2]})
        elif ev[1] == "fault":
            e = {"at_ms": ev[0], "kind": "fault", "code": ev[2]}
            if ev[3]:
                e["joints"] = list(ev[3])
            events.append(e)
        else:
            e = {"at_ms": ev[0], "kind": "fault_cleared"}
            if len(ev) > 2 and ev[2]:
                e["code"] = ev[2]
            events.append(e)
    return {"joints": joints, "events": events}


def make_backend(kind, scenario):
    caps = scenario.get("caps", {})
    if kind == "simulator":
        decl = T.declaration(**caps)
        decl["clock"]["domain"] = CLOCK
        return Simulator(to_sim_script(scenario["profile"]), decl)
    return LoopbackBackend(scenario["profile"], JOINTS, CLOCK, max_concurrent=caps.get("max_concurrent_executions", 8))


def assemble(backend):
    e = LifecycleEngine(None, backend.describe_capabilities(), None)
    store, sink = IdempotencyStore(20000), T.ListSink()
    pub = EventPublisher([sink])
    assert ConfigurationRegistry(e, S.base.CAPS, store).activate(copy.deepcopy(T.config()), 0)["outcome"] == "ACTIVATED"
    S.ready(e, J1, t=0)
    S.ready(e, JP, t=0)
    co = Coordinator(e, store, CommandHistory(100000), pub)
    return e, co, pub, sink, Driver(e, co, backend)


def run_scenario(kind, scenario):
    """Run one scenario on one backend. Returns (public output, the driver, the backend)."""
    backend = make_backend(kind, scenario)
    e, co, pub, sink, d = assemble(backend)
    ids, admissions, last = {}, [], 0

    def utc(t):
        return f"2026-11-15T00:{t // 60:02d}:{t % 60:02d}Z"
    for step in scenario["steps"]:
        op = step[0]
        if op == "submit":
            _, key, cmd, t = step
            r = d.submit(A, cmd, t, utc(t))
            adm = r.admission
            admissions.append({"key": key, "accepted": adm.accepted, "code": adm.code, "step": adm.step,
                               "field": adm.field, "message": adm.message, "replay": adm.replay})
            if adm.accepted:
                ids[key] = r.command_id
            last = t
        elif op == "poll":
            d.poll(step[1], utc(step[1]))
            last = step[1]
        elif op == "terminate":
            _, key, cause, t = step
            d.terminate(ids[key], cause, t, utc(t))
            last = t
        else:
            d.tick(step[1], utc(step[1]))
            last = step[1]
    public = {
        "admissions": admissions,
        "events": copy.deepcopy(sink.events),
        "commands": {k: e.command(c) for k, c in ids.items()},
        "status": {k: co.command_status(c) for k, c in ids.items()},
        "history": {k: co._history.get(c) for k, c in ids.items()},
        "joints": {j: e.joint_state(j, last) for j in (J1, JP)},
        "faults": {j: e.faults(j) for j in (J1, JP)},
    }
    return public, d, backend


def strings(obj):
    """Every key and string value in a public structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from strings(v)
    elif isinstance(obj, str):
        yield obj


def scan(public):
    """The forbidden spellings found in a public structure, as (pattern, text) pairs."""
    found = []
    for text in strings(public):
        for pat in FORBIDDEN:
            if re.search(pat, text, re.IGNORECASE):
                found.append((pat, text))
    return found


VENDOR_TEXT = "ACME-DRV-3000 can0/node7 /dev/ttyUSB0 overcurrent"


def vel(client_request_id, jid=J1, unit="rad/s", v=0.1):
    return S.env("SET_VELOCITY", jid, parameters={"target_velocity": v, "unit": unit}, client_request_id=client_request_id)


def pos(client_request_id, target=0.5, jid=J1):
    return S.env("SET_POSITION", jid, parameters={"target_position": target, "unit": "rad"}, client_request_id=client_request_id)


def scenarios():
    fb = [(t, 0.5, True) for t in (20, 60, 100, 140)]
    ok = ("accept",)
    base = {"dispatch": ok, "start": ("ok", 5), "terminate": ("accept", 30)}
    return {
        "move_and_cancel": {"profile": {"joints": {J1: base}}, "steps": [
            ("submit", "a", vel("r1"), 10), ("poll", 15), ("terminate", "a", "CANCEL_REQUESTED", 20), ("poll", 49), ("poll", 50)]},
        "position_completes_from_feedback": {"profile": {"joints": {J1: {**base, "feedback": fb}}}, "steps": [
            ("submit", "a", pos("r1"), 10), ("poll", 15), ("poll", 20), ("poll", 60), ("poll", 100), ("poll", 140), ("poll", 150)]},
        "rejected_at_dispatch": {"profile": {"joints": {J1: {"dispatch": ("reject", VENDOR_TEXT)}}}, "steps": [
            ("submit", "a", vel("r1"), 10), ("poll", 20)]},
        "rejected_after_acceptance": {"profile": {"joints": {J1: {"dispatch": ok, "start": ("reject", VENDOR_TEXT, 3)}}}, "steps": [
            ("submit", "a", vel("r1"), 10), ("poll", 13)]},
        "termination_never_confirmed": {"profile": {"joints": {J1: {**base, "terminate": ("accept", None)}}}, "steps": [
            ("submit", "a", vel("r1"), 10), ("poll", 15), ("terminate", "a", "CANCEL_REQUESTED", 20), ("poll", 500), ("poll", 1020)]},
        "stop_with_nothing_running": {"profile": {"joints": {J1: {**base, "terminate": ("accept", 10)}}}, "steps": [
            ("submit", "s", S.stop_cmd(client_request_id="r1"), 10), ("poll", 19), ("poll", 20)]},
        "refused_stop": {"profile": {"joints": {J1: {**base, "terminate": ("refuse", VENDOR_TEXT)}}}, "steps": [
            ("submit", "s", S.stop_cmd(client_request_id="r1"), 10), ("poll", 20)]},
        "hold_then_movement_releases_it": {"profile": {"joints": {J1: {**base, "hold": ("accept", 1, 2),
                                                                        "release": ("accept", ("ok", 2))}}}, "steps": [
            ("submit", "h", S.hold_cmd(client_request_id="r1"), 10), ("poll", 12),
            ("submit", "m", vel("r2"), 20), ("poll", 25), ("poll", 27)]},
        "hold_release_fails": {"profile": {"joints": {J1: {**base, "hold": ("accept", 1, 2),
                                                           "release": ("accept", ("fail", 2, VENDOR_TEXT))}}}, "steps": [
            ("submit", "h", S.hold_cmd(client_request_id="r1"), 10), ("poll", 12),
            ("submit", "m", vel("r2"), 20), ("poll", 25), ("poll", 27)]},
        "backend_health_and_faults": {"profile": {"joints": {J1: base}, "events": [
            (12, "health", "DEGRADED"), (30, "fault", "BACKEND_COMMUNICATION_LOSS", [J1]), (40, "fault_cleared", "BACKEND_COMMUNICATION_LOSS"),
            (50, "health", "AVAILABLE")]}, "steps": [
            ("submit", "a", vel("r1"), 10), ("poll", 15), ("poll", 30), ("poll", 40), ("poll", 50)]},
        "admission_rejection": {"profile": {"joints": {J1: base}}, "steps": [
            ("submit", "bad", vel("r1", unit="m/s"), 10), ("poll", 20)]},
        "idempotent_resubmission": {"profile": {"joints": {J1: base}}, "steps": [
            ("submit", "a", vel("r1"), 10), ("submit", "again", vel("r1"), 11), ("poll", 15)]},
        "concurrency_limit": {"caps": {"max_concurrent_executions": 1},
                              "profile": {"joints": {J1: base, JP: base}}, "steps": [
            ("submit", "a", vel("r1"), 10), ("submit", "b", vel("r2", JP, "m/s", 0.05), 11), ("poll", 20)]},
    }
