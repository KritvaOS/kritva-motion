"""Capability declaration of an execution backend (contract 17.2) and its validator (KOS-MOTION-004).

Contract 17.2 lists what a backend MUST declare but defines no format. The shape below is interpretation
I-40 of tasks/KOS-MOTION-004/BACKEND.md section 3 (contract finding C-1): plain data that extends the
`backend` description admission already reads (health, capabilities, joint limits) with the missing items.

    {"supported_target_types": ["joint"],
     "health": "AVAILABLE" | "DEGRADED" | "UNAVAILABLE" | "FAULTED",
     "capabilities": {"supported_joint_types": ["revolute", "prismatic"],
                      "supported_modes": ["position", "velocity"],
                      "controlled_stop": bool, "position_hold": bool, "execution_cancellation": bool,
                      "feedback": {"position": bool, "velocity": bool},
                      "feedback_rate_hz": {"min": number, "max": number} or None,
                      "feedback_rate_declared_absent": bool,       # true exactly when feedback_rate_hz is None
                      "max_concurrent_executions": integer >= 1},
     "joint_limits": {joint_id: {"no_narrower_limit": true} or
                                {"position_min", "position_max", "velocity_max", "acceleration_max" (optional)}},
     "clock": {"domain": string, "synchronized": bool}}

The validator returns every missing or malformed item with its path. It never stops at the first problem and
never fills a default: an absent boolean is a problem, not false. Fields it does not know are ignored, so the
declaration can grow without breaking older validators. Pure, standard library only, no I/O, no clock.
"""
import math
import re
from dataclasses import dataclass

TARGET_TYPES = ("joint", "joint_group", "end_effector", "robot")   # contract 4.1 and 18; only `joint` is usable in v0.1.0
JOINT_TYPES = ("revolute", "prismatic")                            # contract 3.1
MODES = ("position", "velocity")                                   # contract 3.1, 5
HEALTH_VALUES = ("AVAILABLE", "DEGRADED", "UNAVAILABLE", "FAULTED")  # contract 17.2
ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True)
class Problem:
    """One missing or malformed item: where it is and what is wrong."""
    path: str
    message: str

    def __str__(self):
        return f"{self.path or '<declaration>'}: {self.message}"


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _integer(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _enum_list(value, allowed, path, out):
    if not isinstance(value, list) or not value:
        out.append(Problem(path, "must be a non-empty list"))
        return
    for i, item in enumerate(value):
        if item not in allowed:
            out.append(Problem(f"{path}[{i}]", f"{item!r} is not one of {list(allowed)}"))
    if len(set(map(str, value))) != len(value):
        out.append(Problem(path, "must not list a value twice"))


def _boolean(parent, key, path, out):
    if key not in parent:
        out.append(Problem(f"{path}.{key}", "is missing (it must be declared explicitly, true or false)"))
    elif not isinstance(parent[key], bool):
        out.append(Problem(f"{path}.{key}", "must be true or false"))


def _check_capabilities(caps, out):
    p = "capabilities"
    if not isinstance(caps, dict):
        out.append(Problem(p, "is missing or not an object"))
        return
    for key, allowed in (("supported_joint_types", JOINT_TYPES), ("supported_modes", MODES)):
        if key not in caps:
            out.append(Problem(f"{p}.{key}", "is missing"))
        else:
            _enum_list(caps[key], allowed, f"{p}.{key}", out)
    for key in ("controlled_stop", "position_hold", "execution_cancellation"):
        _boolean(caps, key, p, out)
    fb = caps.get("feedback")
    if not isinstance(fb, dict):
        out.append(Problem(f"{p}.feedback", "is missing or not an object (declare position and velocity availability)"))
    else:
        for key in ("position", "velocity"):
            _boolean(fb, key, f"{p}.feedback", out)
    absent = caps.get("feedback_rate_declared_absent")
    if "feedback_rate_declared_absent" not in caps:
        out.append(Problem(f"{p}.feedback_rate_declared_absent", "is missing (true when the backend declares no feedback rate)"))
    elif not isinstance(absent, bool):
        out.append(Problem(f"{p}.feedback_rate_declared_absent", "must be true or false"))
    if "feedback_rate_hz" not in caps:
        out.append(Problem(f"{p}.feedback_rate_hz", "is missing (a {min, max} range, or null with feedback_rate_declared_absent true)"))
    else:
        rate = caps["feedback_rate_hz"]
        if rate is None:
            if absent is not True:
                out.append(Problem(f"{p}.feedback_rate_hz", "is null but feedback_rate_declared_absent is not true"))
        elif not isinstance(rate, dict) or not _number(rate.get("min")) or not _number(rate.get("max")):
            out.append(Problem(f"{p}.feedback_rate_hz", "must be {min, max} with finite numbers, or null"))
        elif not 0 < rate["min"] <= rate["max"]:
            out.append(Problem(f"{p}.feedback_rate_hz", "needs 0 < min <= max"))
        elif absent is True:
            out.append(Problem(f"{p}.feedback_rate_declared_absent", "is true but a feedback rate range is declared"))
    n = caps.get("max_concurrent_executions")
    if "max_concurrent_executions" not in caps:
        out.append(Problem(f"{p}.max_concurrent_executions", "is missing"))
    elif not _integer(n) or n < 1:
        out.append(Problem(f"{p}.max_concurrent_executions", "must be an integer of at least 1"))


def _check_joint_limits(limits, out):
    p = "joint_limits"
    if not isinstance(limits, dict) or not limits:
        out.append(Problem(p, "is missing, empty or not an object (declare the limits of every joint, or no_narrower_limit)"))
        return
    for jid, lim in limits.items():
        path = f"{p}.{jid}"
        if not isinstance(jid, str) or not ID_PATTERN.match(jid):
            out.append(Problem(path, "joint id is not a valid identifier"))
        if not isinstance(lim, dict):
            out.append(Problem(path, "must be an object"))
            continue
        if "no_narrower_limit" in lim:
            if lim["no_narrower_limit"] is not True:
                out.append(Problem(f"{path}.no_narrower_limit", "must be true when present"))
            numeric = [k for k in ("position_min", "position_max", "velocity_max", "acceleration_max") if k in lim]
            if numeric:
                out.append(Problem(path, f"declares no_narrower_limit and also {numeric}"))
            continue
        for key in ("position_min", "position_max", "velocity_max"):
            if key not in lim:
                out.append(Problem(f"{path}.{key}", "is missing (or declare no_narrower_limit: true)"))
            elif not _number(lim[key]):
                out.append(Problem(f"{path}.{key}", "must be a finite number"))
        if _number(lim.get("position_min")) and _number(lim.get("position_max")) and lim["position_min"] > lim["position_max"]:
            out.append(Problem(path, "position_min is above position_max"))
        if _number(lim.get("velocity_max")) and lim["velocity_max"] <= 0:
            out.append(Problem(f"{path}.velocity_max", "must be above 0"))
        if "acceleration_max" in lim and (not _number(lim["acceleration_max"]) or lim["acceleration_max"] <= 0):
            out.append(Problem(f"{path}.acceleration_max", "must be a finite number above 0 when present"))


def validate_declaration(declaration):
    """Return every Problem of a capability declaration; an empty list means it declares every item of 17.2."""
    out = []
    d = declaration
    if not isinstance(d, dict):
        return [Problem("", "the declaration must be an object")]
    _enum_list(d.get("supported_target_types"), TARGET_TYPES, "supported_target_types", out)
    if d.get("health") not in HEALTH_VALUES:
        out.append(Problem("health", f"must be one of {list(HEALTH_VALUES)}"))
    _check_capabilities(d.get("capabilities"), out)
    _check_joint_limits(d.get("joint_limits"), out)
    clock = d.get("clock")
    if not isinstance(clock, dict):
        out.append(Problem("clock", "is missing or not an object (declare the clock domain and synchronization status)"))
    else:
        if not isinstance(clock.get("domain"), str) or not clock["domain"].strip():
            out.append(Problem("clock.domain", "must be a non-empty string"))
        _boolean(clock, "synchronized", "clock", out)
    return out


def is_conforming(declaration):
    """True when the declaration has no Problem."""
    return not validate_declaration(declaration)
