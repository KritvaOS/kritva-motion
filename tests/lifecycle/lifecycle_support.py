"""Fixtures for the lifecycle engine tests. Plain data; deterministic and offline: no clock, no
randomness, no network. Passing the tests is software evidence only, never physical or safety
validation."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "validator"))
import test_admission as base  # noqa: E402
from kritva_motion.lifecycle import LifecycleEngine  # noqa: E402

env, joint = base.env, base.joint


def config(**joint_1_over):
    c = copy.deepcopy(base.CONFIG)
    c["joints"][0] = joint(**joint_1_over)
    return c


def engine(cfg=None, backend=None):
    return LifecycleEngine(copy.deepcopy(cfg or base.CONFIG), copy.deepcopy(backend or base.BACKEND), "digest-1")


def sample(pos=0.0, validity="VALID", synchronized=True, stamp="2026-11-08T00:00:00Z", **extra):
    s = {"measured_position": pos, "validity": validity, "backend_timestamp": stamp,
         "clock_domain": "backend-clock", "clock_synchronized": synchronized}
    s.update(extra)
    return s


def ready(e, jid="joint-1", t=0, pos=0.0):
    """Establish IDLE by a fresh authoritative report and give the joint one valid feedback sample."""
    e.status_report(jid, "IDLE", 0, t)
    e.feedback(jid, sample(pos), t)


def submit_start(e, cmd, t_submit, t_start=None):
    """Submit, then confirm the start. Returns (command_id, submit result)."""
    r = e.submit(cmd, t_submit)
    assert r.admission.accepted, r.admission
    cid = r.command_id
    e.execution_started(cid, e.command(cid)["backend_reference"], t_submit if t_start is None else t_start)
    return cid, r


def pos_cmd(target=0.5, jid="joint-1", unit="rad", **over):
    return env("SET_POSITION", jid, parameters={"target_position": target, "unit": unit}, **over)


def vel_cmd(vel=0.1, jid="joint-1", unit="rad/s", duration=None, **over):
    p = {"target_velocity": vel, "unit": unit}
    if duration is not None:
        p["duration_ms"] = duration
    return env("SET_VELOCITY", jid, parameters=p, **over)


def stop_cmd(jid="joint-1", **over):
    return env("STOP", jid, **over)


def hold_cmd(jid="joint-1", **over):
    return env("HOLD", jid, **over)


def cancel_cmd(command_id, **over):
    return env("CANCEL", parameters={"command_id": command_id}, **over)
