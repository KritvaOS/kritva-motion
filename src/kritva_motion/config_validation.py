"""Robot configuration validator (contract section 3, AC-201).

`validate_configuration(config, capabilities)` checks a configuration supplied as plain data
(dicts, lists, strings, numbers) against the declared backend capabilities and returns every
violation it finds. It does not activate anything: there is no activation runtime here. The
result is deterministic: joints are checked in list order and fields in a fixed order, then the
policy tables. No I/O, no clock, no randomness; the inputs are never modified.

The contract lists the configuration fields (3.1) but does not fix a serialization. This module
defines the plain-data shape below and reports violations by a `rule` name that traces to a
contract section. The rule names are not contract error codes: the contract defines no error code
for configuration activation (3.2 only requires that activation fail and that the reason be
explicit).

Configuration shape::

    {"config_version": "1",
     "joints": [{"joint_id": ..., "name": ..., "joint_type": "revolute" | "prismatic",
                 "positive_direction": ..., "position_min": ..., "position_max": ...,
                 "continuous": true,                      # revolute only; no position limits
                 "velocity_max": ..., "acceleration_max": ...,          # optional
                 "modes": ["position", "velocity"],
                 "max_feedback_age_ms": ..., "feedback_required": ...,
                 "feedback_timeout_policy": "STOP_AND_FAULT" | "DEGRADE",
                 "termination_confirm_timeout_ms": ...,
                 "degradation_policy": {"FEEDBACK_OPTIONAL_UNAVAILABLE": ["SET_VELOCITY"], ...},
                 "position_tolerance": ..., "settling_duration_ms": ...,
                 "default_execution_timeout_ms": ..., "default_deadline_ms": ...,
                 "fault_clearance": {"FEEDBACK_LOST": "CLIENT_AUTHORIZED", ...}}]}

Backend capabilities (17.2), only the parts configuration depends on::

    {"controlled_stop": bool, "position_hold": bool,
     "supported_modes": [...], "supported_joint_types": [...]}
"""
import math
import re
from dataclasses import dataclass

ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
FAULT_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+$")

JOINT_TYPES = ("revolute", "prismatic")
MODES = ("position", "velocity")
FEEDBACK_TIMEOUT_POLICIES = ("STOP_AND_FAULT", "DEGRADE")
CLEARANCE_VALUES = ("CLIENT_AUTHORIZED", "HUMAN_REQUIRED")
DEGRADATION_REASONS = ("FEEDBACK_OPTIONAL_UNAVAILABLE", "BACKEND_DEGRADED")
DEGRADATION_OPERATIONS = ("SET_POSITION", "SET_VELOCITY", "HOLD")
# Operations that cannot meet their precondition or completion rules without feedback (13.8).
FEEDBACK_DEPENDENT_OPERATIONS = ("SET_POSITION", "HOLD")

TOP_FIELDS = ("config_version", "joints")
JOINT_REQUIRED = (
    "joint_id", "name", "joint_type", "positive_direction", "velocity_max", "modes",
    "max_feedback_age_ms", "feedback_required", "feedback_timeout_policy",
    "termination_confirm_timeout_ms", "position_tolerance", "settling_duration_ms",
    "default_execution_timeout_ms", "default_deadline_ms",
)
JOINT_OPTIONAL = (
    "position_min", "position_max", "continuous", "acceleration_max",
    "degradation_policy", "fault_clearance",
)
CAPABILITY_FIELDS = ("controlled_stop", "position_hold", "supported_modes", "supported_joint_types")


@dataclass(frozen=True)
class Violation:
    rule: str      # stable name, traced to a contract section
    section: str   # contract section
    path: str      # where in the configuration, for example joints[0].modes
    message: str


@dataclass(frozen=True)
class ConfigResult:
    valid: bool
    violations: tuple


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_finite(v):
    return _is_number(v) and math.isfinite(v)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


class _Collector:
    def __init__(self):
        self.items = []

    def add(self, rule, section, path, message):
        self.items.append(Violation(rule, section, path, message))


def _check_capabilities(caps, out):
    """Return True when the capabilities are usable for the checks that need them."""
    if not isinstance(caps, dict):
        out.add("CFG_CAPABILITIES_INVALID", "17.2", "capabilities", "backend capabilities are missing or not an object")
        return False
    ok = True
    for f in CAPABILITY_FIELDS:
        if f not in caps:
            out.add("CFG_CAPABILITIES_INVALID", "17.2", f"capabilities.{f}", "capability not declared")
            ok = False
    for f in ("controlled_stop", "position_hold"):
        if f in caps and not isinstance(caps[f], bool):
            out.add("CFG_CAPABILITIES_INVALID", "17.2", f"capabilities.{f}", "must be true or false")
            ok = False
    for f, allowed in (("supported_modes", MODES), ("supported_joint_types", JOINT_TYPES)):
        if f in caps:
            v = caps[f]
            if not isinstance(v, list) or any(x not in allowed for x in v):
                out.add("CFG_CAPABILITIES_INVALID", "17.2", f"capabilities.{f}", f"must be a list of values from {list(allowed)}")
                ok = False
    for f in caps:
        if f not in CAPABILITY_FIELDS:
            out.add("CFG_CAPABILITIES_INVALID", "17.2", f"capabilities.{f}", "unknown capability field")
            ok = False
    return ok


def _positive_number(j, field, p, out, integer=False, minimum_zero=False):
    v = j[field]
    kind = "an integer" if integer else "a finite number"
    if integer and not _is_int(v):
        out.add("CFG_BAD_VALUE", "3.1", f"{p}.{field}", f"must be {kind}")
    elif not integer and not _is_finite(v):
        out.add("CFG_BAD_VALUE", "3.1", f"{p}.{field}", f"must be {kind}")
    elif v < 0 or (v == 0 and not minimum_zero):
        out.add("CFG_BAD_VALUE", "3.1", f"{p}.{field}", "must be " + ("zero or more" if minimum_zero else "greater than zero"))


def _check_joint(j, i, caps, caps_ok, out):
    p = f"joints[{i}]"
    if not isinstance(j, dict):
        out.add("CFG_BAD_VALUE", "3.1", p, "a joint must be an object")
        return
    for f in JOINT_REQUIRED:
        if f not in j:
            out.add("CFG_MISSING_FIELD", "3.1", f"{p}.{f}", "required field is missing")
    for f in j:
        if f not in JOINT_REQUIRED and f not in JOINT_OPTIONAL:
            out.add("CFG_UNKNOWN_FIELD", "3.1", f"{p}.{f}", "unknown field")

    if "joint_id" in j and not (isinstance(j["joint_id"], str) and ID_PATTERN.match(j["joint_id"])):
        out.add("CFG_BAD_ID", "1.4", f"{p}.joint_id", "must be 1 to 128 characters from A-Z a-z 0-9 . _ : -")
    for f in ("name", "positive_direction"):
        if f in j and not (isinstance(j[f], str) and j[f].strip()):
            out.add("CFG_BAD_VALUE", "3.1", f"{p}.{f}", "must be a non-empty string")

    jt = j.get("joint_type")
    if "joint_type" in j and jt not in JOINT_TYPES:
        out.add("CFG_UNKNOWN_VALUE", "3.1", f"{p}.joint_type", f"unknown joint_type; allowed {list(JOINT_TYPES)}")
    elif jt is not None and caps_ok and jt not in caps["supported_joint_types"]:
        out.add("CFG_BACKEND_CANNOT_SATISFY", "3.6", f"{p}.joint_type", f"the backend does not support joint type {jt}")

    modes = j.get("modes")
    modes_ok = False
    if "modes" in j:
        if not isinstance(modes, list) or not modes or any(m not in MODES for m in modes) or len(set(modes)) != len(modes):
            out.add("CFG_UNKNOWN_VALUE", "3.1", f"{p}.modes", f"must be a non-empty list without duplicates from {list(MODES)}")
        else:
            modes_ok = True
            if caps_ok:
                for m in modes:
                    if m not in caps["supported_modes"]:
                        out.add("CFG_BACKEND_CANNOT_SATISFY", "3.6", f"{p}.modes", f"the backend does not support mode {m}")

    # Position limits and continuous joints (3.1, 3.7).
    continuous = j.get("continuous", False)
    if "continuous" in j and not isinstance(continuous, bool):
        out.add("CFG_BAD_VALUE", "3.7", f"{p}.continuous", "must be true or false")
        continuous = False
    has_min, has_max = "position_min" in j, "position_max" in j
    if continuous:
        if jt == "prismatic":
            out.add("CFG_CONTINUOUS", "3.1", f"{p}.continuous", "continuous is allowed only for a revolute joint")
        if has_min or has_max:
            out.add("CFG_CONTINUOUS", "3.1", f"{p}.position_min", "a continuous joint has no position limits")
        if modes_ok and "position" in modes:
            out.add("CFG_CONTINUOUS_POSITION_MODE", "3.7", f"{p}.modes", "a continuous joint supports velocity mode only in v0.1.0")
    else:
        if not (has_min and has_max):
            out.add("CFG_POSITION_LIMITS", "3.1", f"{p}.position_min", "position_min and position_max are required unless the joint is continuous")
        for f in ("position_min", "position_max"):
            if f in j and not _is_finite(j[f]):
                out.add("CFG_BAD_VALUE", "3.1", f"{p}.{f}", "must be a finite number")
        if has_min and has_max and _is_finite(j["position_min"]) and _is_finite(j["position_max"]) and not j["position_min"] < j["position_max"]:
            out.add("CFG_POSITION_LIMITS", "3.1", f"{p}.position_min", "position_min must be less than position_max")

    if "velocity_max" in j:
        _positive_number(j, "velocity_max", p, out)
    if "acceleration_max" in j:
        _positive_number(j, "acceleration_max", p, out)
    if "position_tolerance" in j:
        _positive_number(j, "position_tolerance", p, out)
    for f in ("max_feedback_age_ms", "termination_confirm_timeout_ms", "default_execution_timeout_ms", "default_deadline_ms"):
        if f in j:
            _positive_number(j, f, p, out, integer=True)
    if "settling_duration_ms" in j:
        _positive_number(j, "settling_duration_ms", p, out, integer=True, minimum_zero=True)

    fr = j.get("feedback_required")
    if "feedback_required" in j and not isinstance(fr, bool):
        out.add("CFG_BAD_VALUE", "3.1", f"{p}.feedback_required", "must be true or false")
        fr = None

    # Policies (3.6).
    ftp = j.get("feedback_timeout_policy")
    if "feedback_timeout_policy" in j:
        if ftp not in FEEDBACK_TIMEOUT_POLICIES:
            hint = " (HOLD is never a response to feedback loss)" if ftp == "HOLD" else ""
            out.add("CFG_UNKNOWN_POLICY", "3.6", f"{p}.feedback_timeout_policy",
                    f"unknown policy value; allowed {list(FEEDBACK_TIMEOUT_POLICIES)}{hint}")
        elif ftp == "DEGRADE" and fr is True:
            out.add("CFG_DEGRADE_FEEDBACK_REQUIRED", "3.6", f"{p}.feedback_timeout_policy", "DEGRADE is allowed only when feedback_required is false")
        elif ftp == "STOP_AND_FAULT" and caps_ok and not caps["controlled_stop"]:
            out.add("CFG_BACKEND_CANNOT_SATISFY", "3.6", f"{p}.feedback_timeout_policy", "STOP_AND_FAULT requires backend controlled-stop support")

    if "degradation_policy" in j:
        dp = j["degradation_policy"]
        if not isinstance(dp, dict):
            out.add("CFG_BAD_VALUE", "3.6", f"{p}.degradation_policy", "must be an object mapping a degradation reason to a list of operations")
        else:
            for reason in sorted(dp, key=str):
                rp = f"{p}.degradation_policy.{reason}"
                if reason not in DEGRADATION_REASONS:
                    out.add("CFG_UNKNOWN_POLICY", "3.6", rp, f"unknown degradation reason; allowed {list(DEGRADATION_REASONS)}")
                    continue
                ops = dp[reason]
                if not isinstance(ops, list) or any(o not in DEGRADATION_OPERATIONS for o in ops):
                    out.add("CFG_UNKNOWN_POLICY", "3.6", rp, f"must be a list of operations from {list(DEGRADATION_OPERATIONS)}")
                    continue
                if reason == "FEEDBACK_OPTIONAL_UNAVAILABLE":
                    for o in FEEDBACK_DEPENDENT_OPERATIONS:
                        if o in ops:
                            out.add("CFG_DEGRADATION_UNSAFE_OPERATION", "13.8", rp,
                                    f"{o} cannot be permitted when optional feedback is unavailable")
                if "HOLD" in ops and caps_ok and not caps["position_hold"]:
                    # Runtime admission also needs backend hold support (13.8); a policy that can never be used is inconsistent.
                    out.add("CFG_BACKEND_CANNOT_SATISFY", "3.6", rp, "HOLD is listed but the backend does not support position hold")

    if "fault_clearance" in j:
        fc = j["fault_clearance"]
        if not isinstance(fc, dict):
            out.add("CFG_BAD_VALUE", "3.6", f"{p}.fault_clearance", "must be an object mapping a fault code to a clearance value")
        else:
            for code in sorted(fc, key=str):
                cp = f"{p}.fault_clearance.{code}"
                if not (isinstance(code, str) and FAULT_CODE_PATTERN.match(code)):
                    out.add("CFG_BAD_ID", "3.6", cp, "fault code must be upper-case letters, digits and underscores")
                if fc[code] not in CLEARANCE_VALUES:
                    out.add("CFG_UNKNOWN_POLICY", "3.6", cp, f"unknown clearance value; allowed {list(CLEARANCE_VALUES)}")


def validate_configuration(config, capabilities):
    """Return a ConfigResult. `valid` is True only when there are no violations."""
    out = _Collector()
    caps_ok = _check_capabilities(capabilities, out)
    if not isinstance(config, dict):
        out.add("CFG_BAD_VALUE", "3.2", "config", "configuration must be an object")
        return ConfigResult(False, tuple(out.items))
    for f in TOP_FIELDS:
        if f not in config:
            out.add("CFG_MISSING_FIELD", "3.2", f, "required field is missing")
    for f in config:
        if f not in TOP_FIELDS:
            out.add("CFG_UNKNOWN_FIELD", "3.2", f, "unknown field")
    if "config_version" in config and not (isinstance(config["config_version"], str) and config["config_version"].strip()):
        out.add("CFG_BAD_VALUE", "3.3", "config_version", "must be a non-empty string")
    joints = config.get("joints")
    if "joints" in config:
        if not isinstance(joints, list) or not joints:
            out.add("CFG_BAD_VALUE", "3.1", "joints", "must be a non-empty list")
        else:
            seen = {}
            for i, j in enumerate(joints):
                _check_joint(j, i, capabilities if caps_ok else None, caps_ok, out)
                jid = j.get("joint_id") if isinstance(j, dict) else None
                if isinstance(jid, str):
                    if jid in seen:
                        out.add("CFG_DUPLICATE_JOINT", "3.1", f"joints[{i}].joint_id", f"joint_id already used by joints[{seen[jid]}]")
                    else:
                        seen[jid] = i
    return ConfigResult(not out.items, tuple(out.items))
