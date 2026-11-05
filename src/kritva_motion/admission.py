"""Command admission validator (contract 8.3 and 8.4, AC-202 and AC-203).

`first_failure(context, through_step)` runs the fixed validation order of contract 8.4 on one
read-only `AdmissionContext` and stops at the first failure, so the result is deterministic.
`admit(context)` is the public entry. In this change it covers steps 1 to 9; steps 10 (joint state
and preconditions) and 11 (arbitration) arrive in later changes of KOS-MOTION-002, and until then
`admit` raises NotImplementedError instead of accepting a command that passed only steps 1 to 9.

The validator judges a supplied, structurally valid context. It reads no clock, no file, no network
and no backend; authentication, authorization, the idempotency lookup, the active configuration, the
backend declaration and the command and fault records are all inputs. A result carries no command
ID and changes no state.

Sub-order inside a step (a task decision, recorded in tasks/KOS-MOTION-002/TASK.md section 10):
  step 2: INVALID_SCHEMA, NON_FINITE_VALUE, UNSUPPORTED_CONTRACT_VERSION (the order of 8.4);
  step 6: command type, target type, target ID, then the referenced command or fault; for a
          referenced command: not found, already terminal, not cancellable;
  step 7: mode, priority, unit (the order of 8.4);
  step 8: INVALID_CONSTRAINT (a constraint that widens, is contradictory or leaves an empty range),
          LIMIT_POSITION, LIMIT_VELOCITY, then INVALID_TIMEOUT;
  step 9: BACKEND_UNAVAILABLE, then BACKEND_CAPABILITY_UNSUPPORTED.
"""
import math
import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any, Optional

STEP_NAMES = {
    1: "identity", 2: "envelope", 3: "authorization", 4: "idempotency", 5: "configuration",
    6: "type and references", 7: "mode, priority and unit", 8: "limits and constraints",
    9: "backend health and capability", 10: "joint state", 11: "arbitration",
}
IMPLEMENTED_THROUGH_STEP = 9

# Copied from contract/motion-command.schema.json; tests compare them with the schema.
VERSION_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$"
ID_PATTERN = r"^[A-Za-z0-9._:-]{1,128}$"
_VERSION = re.compile(VERSION_PATTERN)
_ID = re.compile(ID_PATTERN)

COMMAND_TYPES = ("SET_POSITION", "SET_VELOCITY", "STOP", "HOLD", "CANCEL", "CLEAR_FAULT", "EXECUTE_TRAJECTORY")
TARGET_TYPES = ("joint", "joint_group", "end_effector", "robot")
RESERVED_TARGET_TYPES = ("joint_group", "end_effector", "robot")
ENVELOPE_FIELDS = (
    "contract_version", "client_request_id", "identity_assertion", "command_type", "target", "parameters",
    "constraints", "priority", "deadline_ms", "execution_timeout_ms", "issued_at",
)
CONSTRAINT_FIELDS = ("max_velocity", "max_acceleration", "position_min", "position_max", "unit_system")
NOT_CANCELLABLE_OPERATIONS = ("STOP", "CLEAR_FAULT", "CANCEL")
TERMINAL_STATES = ("COMPLETED", "CANCELLED", "FAILED")
UNAVAILABLE_BACKEND_HEALTH = ("UNAVAILABLE", "FAULTED")
BACKEND_HEALTH = ("AVAILABLE", "DEGRADED", "UNAVAILABLE", "FAULTED")
POSITION_UNIT = {"revolute": "rad", "prismatic": "m"}
VELOCITY_UNIT = {"revolute": "rad/s", "prismatic": "m/s"}


@dataclass(frozen=True)
class AdmissionContext:
    """Everything admission may look at. Nothing in it is read from the environment.

    command                 the command envelope exactly as received (any value)
    identity                supplied identity result: VALID, MISSING, INVALID or EXPIRED (16.2)
    supported_contract_major  the contract MAJOR version this validator supports (0 for v0.1.0)
    permission_granted      supplied authorization result for the operation and target scope (16.3)
    idempotency             supplied lookup result for (client, client_request_id) (7.4):
                            {"status": "NEW" | "IDENTICAL" | "DIFFERENT",
                             "stored_decision": {"accepted": bool, "code": str | None}}
    active_config           the validated active configuration (plain data, see config_validation) or None
    commands                known commands by command_id: {"operation", "state", "visible",
                            "hold_engaged"}; "visible" says whether this client may see the record
    faults                  known faults by fault_id: {"joint_id", "visible"}
    backend                 {"health": AVAILABLE | DEGRADED | UNAVAILABLE | FAULTED,
                             "capabilities": {controlled_stop, position_hold, supported_modes,
                                              supported_joint_types},
                             "joint_limits": {joint_id: {"no_narrower_limit": true} or
                                              {"position_min", "position_max", "velocity_max",
                                               "acceleration_max" (optional)}}} or None
    joint_state             the supplied joint-state snapshot (used from step 10, a later change)
    reference_time_ms       the supplied monotonic reference time (used from step 10)
    """
    command: Any
    identity: str = "VALID"
    supported_contract_major: int = 0
    permission_granted: bool = True
    idempotency: dict = dc_field(default_factory=lambda: {"status": "NEW"})
    active_config: Optional[dict] = None
    commands: dict = dc_field(default_factory=dict)
    faults: dict = dc_field(default_factory=dict)
    backend: Optional[dict] = None
    joint_state: Optional[dict] = None
    reference_time_ms: Optional[float] = None


@dataclass(frozen=True)
class AdmissionResult:
    """Accepted or rejected, the first error code, the step and field, and an optional message.

    `replay` is True when the result is the stored decision of an identical earlier request (7.4);
    the result still carries no command ID.
    """
    accepted: bool
    code: Optional[str] = None
    step: Optional[int] = None
    field: Optional[str] = None
    message: Optional[str] = None
    replay: bool = False


@dataclass(frozen=True)
class Failure:
    code: str
    step: int
    field: str
    message: str


@dataclass(frozen=True)
class EffectiveLimits:
    """Contract 8.1 and 8.3: the intersection of backend, configuration and command limits."""
    position_min: Optional[float]
    position_max: Optional[float]
    velocity_max: float
    acceleration_max: Optional[float]   # a declared maximum only: no v0.1.0 command requests acceleration
    empty: bool                          # the position range is empty


# ---------------------------------------------------------------- helpers

def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v):
    return _is_number(v) and math.isfinite(v)


def _nonfinite_float(v):
    return isinstance(v, float) and not math.isfinite(v)


def _is_integer_slot(v):
    """JSON Schema `integer`: an int, or a float with an integral value. A NaN or infinity is
    left for the non-finite check (step 2), not reported as a schema error."""
    if isinstance(v, bool):
        return False
    return isinstance(v, int) or (isinstance(v, float) and (v.is_integer() or _nonfinite_float(v)))


def _is_number_slot(v):
    return _is_number(v)


def _id_ok(v):
    return isinstance(v, str) and _ID.search(v) is not None


# ---------------------------------------------------------------- step 2: envelope

def schema_problem(cmd):
    """Mirror of contract/motion-command.schema.json. Returns (field, message) or None.

    Tests compare this function with the schema on a fixed corpus. `format` keywords are not asserted
    (as in the schema tests); identity_assertion is opaque.
    """
    if not isinstance(cmd, dict):
        return ("command", "the envelope must be an object")
    for k in sorted(cmd, key=str):
        if k not in ENVELOPE_FIELDS:
            return (str(k), "unknown field")
    for k in ("contract_version", "client_request_id", "command_type"):
        if k not in cmd:
            return (k, "required field is missing")
    v = cmd["contract_version"]
    if not (isinstance(v, str) and _VERSION.search(v)):
        return ("contract_version", "must be a semantic version")
    if not _id_ok(cmd["client_request_id"]):
        return ("client_request_id", "must be 1 to 128 characters from A-Z a-z 0-9 . _ : -")
    if "identity_assertion" in cmd and not isinstance(cmd["identity_assertion"], dict):
        return ("identity_assertion", "must be an object")
    ct = cmd["command_type"]
    if ct not in COMMAND_TYPES:
        return ("command_type", "unknown command type")
    if "target" in cmd:
        t = cmd["target"]
        if not isinstance(t, dict):
            return ("target", "must be an object")
        for k in sorted(t, key=str):
            if k not in ("type", "id"):
                return (f"target.{k}", "unknown field")
        for k in ("type", "id"):
            if k not in t:
                return (f"target.{k}", "required field is missing")
        if t["type"] not in TARGET_TYPES:
            return ("target.type", "unknown target type")
        if not _id_ok(t["id"]):
            return ("target.id", "must be 1 to 128 characters from A-Z a-z 0-9 . _ : -")
    if "parameters" in cmd and not isinstance(cmd["parameters"], dict):
        return ("parameters", "must be an object")
    if "constraints" in cmd:
        c = cmd["constraints"]
        if not isinstance(c, dict):
            return ("constraints", "must be an object")
        for k in sorted(c, key=str):
            if k not in CONSTRAINT_FIELDS:
                return (f"constraints.{k}", "unknown field")
        for k in ("max_velocity", "max_acceleration"):
            if k in c:
                if not _is_number_slot(c[k]):
                    return (f"constraints.{k}", "must be a number")
                if _finite(c[k]) and c[k] < 0:
                    return (f"constraints.{k}", "must not be negative")
        for k in ("position_min", "position_max"):
            if k in c and not _is_number_slot(c[k]):
                return (f"constraints.{k}", "must be a number")
        if "unit_system" in c and c["unit_system"] != "SI":
            return ("constraints.unit_system", "must be SI")
    if "priority" in cmd and not _is_integer_slot(cmd["priority"]):
        return ("priority", "must be an integer")
    for k in ("deadline_ms", "execution_timeout_ms"):
        if k in cmd:
            if not _is_integer_slot(cmd[k]):
                return (k, "must be an integer")
            if _finite(cmd[k]) and cmd[k] <= 0:
                return (k, "must be greater than zero")
    if "issued_at" in cmd and not isinstance(cmd["issued_at"], str):
        return ("issued_at", "must be a string")
    return _parameters_problem(cmd, ct)


def _params_object(cmd, required, optional):
    p = cmd.get("parameters")
    for k in sorted(p, key=str):
        if k not in required and k not in optional:
            return (f"parameters.{k}", "unknown field")
    for k in required:
        if k not in p:
            return (f"parameters.{k}", "required field is missing")
    return None


def _parameters_problem(cmd, ct):
    has_target, has_params = "target" in cmd, "parameters" in cmd
    if ct in ("SET_POSITION", "SET_VELOCITY", "CLEAR_FAULT"):
        for k, present in (("target", has_target), ("parameters", has_params)):
            if not present:
                return (k, "required field is missing")
    elif ct in ("STOP", "HOLD"):
        if not has_target:
            return ("target", "required field is missing")
        if has_params and cmd["parameters"]:
            return ("parameters", "must be empty")
    elif ct == "CANCEL":
        if not has_params:
            return ("parameters", "required field is missing")
        if has_target:
            return ("target", "not allowed for CANCEL")
    p = cmd.get("parameters")
    if ct == "SET_POSITION":
        r = _params_object(cmd, ("target_position", "unit"), ())
        if r:
            return r
        if not _is_number_slot(p["target_position"]):
            return ("parameters.target_position", "must be a number")
        if p["unit"] not in ("rad", "m"):
            return ("parameters.unit", "must be rad or m")
    elif ct == "SET_VELOCITY":
        r = _params_object(cmd, ("target_velocity", "unit"), ("duration_ms",))
        if r:
            return r
        if not _is_number_slot(p["target_velocity"]):
            return ("parameters.target_velocity", "must be a number")
        if p["unit"] not in ("rad/s", "m/s"):
            return ("parameters.unit", "must be rad/s or m/s")
        if "duration_ms" in p:
            if not _is_integer_slot(p["duration_ms"]):
                return ("parameters.duration_ms", "must be an integer")
            if _finite(p["duration_ms"]) and p["duration_ms"] <= 0:
                return ("parameters.duration_ms", "must be greater than zero")
    elif ct == "CANCEL":
        r = _params_object(cmd, ("command_id",), ())
        if r:
            return r
        if not _id_ok(p["command_id"]):
            return ("parameters.command_id", "must be 1 to 128 characters from A-Z a-z 0-9 . _ : -")
    elif ct == "CLEAR_FAULT":
        r = _params_object(cmd, ("fault_id",), ())
        if r:
            return r
        if not _id_ok(p["fault_id"]):
            return ("parameters.fault_id", "must be 1 to 128 characters from A-Z a-z 0-9 . _ : -")
    return None


def _find_nonfinite(node, path):
    if _nonfinite_float(node):
        return path
    if isinstance(node, dict):
        for k in sorted(node, key=str):
            r = _find_nonfinite(node[k], f"{path}.{k}" if path else str(k))
            if r:
                return r
    elif isinstance(node, list):
        for i, v in enumerate(node):
            r = _find_nonfinite(v, f"{path}[{i}]")
            if r:
                return r
    return None


# ---------------------------------------------------------------- limits (8.1 to 8.3)

def _backend_limit_entry(ctx, joint_id):
    """The numerical limits the backend declared for a joint: a dict of numbers, {} when it explicitly
    declared no narrower limit, or None when nothing usable was declared."""
    b = ctx.backend if isinstance(ctx.backend, dict) else None
    entry = (b or {}).get("joint_limits", {}).get(joint_id) if b else None
    if not isinstance(entry, dict):
        return None
    if entry.get("no_narrower_limit") is True and not any(k in entry for k in ("position_min", "position_max", "velocity_max", "acceleration_max")):
        return {}
    need = ("position_min", "position_max", "velocity_max")
    if all(_finite(entry.get(k)) for k in need) and ("acceleration_max" not in entry or _finite(entry["acceleration_max"])):
        return {k: entry[k] for k in (*need, "acceleration_max") if k in entry}
    return None


def effective_limits(joint, backend_entry, constraints):
    """Intersection of configuration, backend and command limits (8.1, 8.3), inclusive at the boundary.

    `joint` is the configured joint, `backend_entry` a dict of declared backend numbers ({} for an
    explicit no-narrower-limit declaration, None for an undeclared one, which narrows nothing here
    and is refused later at step 9) and `constraints` the command constraints or None. The
    acceleration value is a declared maximum only (MOTION-AD-045); nothing requests acceleration.
    """
    c = constraints or {}
    be = backend_entry or {}
    lows, highs, vels, accs = [], [], [joint["velocity_max"]], []
    continuous = joint.get("continuous") is True
    if not continuous:
        lows.append(joint["position_min"])
        highs.append(joint["position_max"])
        if "position_min" in be:
            lows.append(be["position_min"])
        if "position_max" in be:
            highs.append(be["position_max"])
    if "position_min" in c:
        lows.append(c["position_min"])
    if "position_max" in c:
        highs.append(c["position_max"])
    if "velocity_max" in be:
        vels.append(be["velocity_max"])
    if "max_velocity" in c:
        vels.append(c["max_velocity"])
    for v in (joint.get("acceleration_max"), be.get("acceleration_max"), c.get("max_acceleration")):
        if v is not None:
            accs.append(v)
    lo = max(lows) if lows else None
    hi = min(highs) if highs else None
    return EffectiveLimits(lo, hi, min(vels), min(accs) if accs else None,
                           lo is not None and hi is not None and lo > hi)


# ---------------------------------------------------------------- the steps

def _joint_of(ctx):
    cmd = ctx.command
    t = cmd.get("target") if isinstance(cmd, dict) else None
    if not isinstance(t, dict) or not isinstance(ctx.active_config, dict):
        return None
    for j in ctx.active_config.get("joints", []):
        if j.get("joint_id") == t.get("id"):
            return j
    return None


def _step1(ctx):
    if ctx.identity != "VALID":
        return Failure("UNAUTHENTICATED", 1, "identity_assertion", f"identity result is {ctx.identity}")


def _step2(ctx):
    p = schema_problem(ctx.command)
    if p:
        return Failure("INVALID_SCHEMA", 2, p[0], p[1])
    nf = _find_nonfinite(ctx.command, "")
    if nf:
        return Failure("NON_FINITE_VALUE", 2, nf, "a number is NaN or infinite")
    major = int(ctx.command["contract_version"].split(".")[0])
    if major != ctx.supported_contract_major:
        return Failure("UNSUPPORTED_CONTRACT_VERSION", 2, "contract_version", f"major version {major} is not supported")


def _step3(ctx):
    if not ctx.permission_granted:
        return Failure("PERMISSION_DENIED", 3, "command_type", "the client lacks permission for the operation or target scope")


def _step4(ctx):
    st = (ctx.idempotency or {}).get("status", "NEW")
    if st == "DIFFERENT":
        return Failure("REQUEST_ID_CONFLICT", 4, "client_request_id", "the request ID was used with different content")
    if st == "IDENTICAL":
        d = ctx.idempotency.get("stored_decision") or {}
        return _Replay(d)
    return None


class _Replay:
    """Internal marker: step 4 returns the stored decision of an identical earlier request."""
    def __init__(self, decision):
        self.decision = decision


def _step5(ctx):
    if not isinstance(ctx.active_config, dict):
        return Failure("CONFIG_NOT_ACTIVE", 5, "active_config", "no validated active configuration")


def _step6(ctx):
    cmd = ctx.command
    ct = cmd["command_type"]
    if ct == "EXECUTE_TRAJECTORY":
        return Failure("UNSUPPORTED_COMMAND", 6, "command_type", "EXECUTE_TRAJECTORY is reserved")
    if ct != "CANCEL":
        t = cmd["target"]
        if t["type"] in RESERVED_TARGET_TYPES:
            return Failure("UNSUPPORTED_TARGET_TYPE", 6, "target.type", f"{t['type']} is reserved")
        if _joint_of(ctx) is None:
            return Failure("UNKNOWN_TARGET", 6, "target.id", "the target is not in the active configuration")
    if ct == "CANCEL":
        rec = ctx.commands.get(cmd["parameters"]["command_id"])
        if not isinstance(rec, dict) or rec.get("visible") is not True:
            return Failure("COMMAND_NOT_FOUND", 6, "parameters.command_id", "unknown or invisible command")
        if rec.get("state") in TERMINAL_STATES:
            return Failure("COMMAND_ALREADY_TERMINAL", 6, "parameters.command_id", "the command is already terminal")
        if rec.get("operation") in NOT_CANCELLABLE_OPERATIONS or (rec.get("operation") == "HOLD" and rec.get("hold_engaged") is True):
            return Failure("COMMAND_NOT_CANCELLABLE", 6, "parameters.command_id", "the command cannot be cancelled")
    if ct == "CLEAR_FAULT":
        rec = ctx.faults.get(cmd["parameters"]["fault_id"])
        if (not isinstance(rec, dict) or rec.get("visible") is not True
                or rec.get("joint_id") != cmd["target"]["id"]):
            return Failure("FAULT_NOT_FOUND", 6, "parameters.fault_id", "unknown fault, a fault of another joint, or invisible")


def _step7(ctx):
    cmd = ctx.command
    ct = cmd["command_type"]
    j = _joint_of(ctx)
    if j is None:
        return None
    if ct == "SET_POSITION" and (j.get("continuous") is True or "position" not in j["modes"]):
        return Failure("UNSUPPORTED_MODE", 7, "command_type", "the joint does not support position mode")
    if ct == "SET_VELOCITY" and "velocity" not in j["modes"]:
        return Failure("UNSUPPORTED_MODE", 7, "command_type", "the joint does not support velocity mode")
    if "priority" in cmd and cmd["priority"] != j.get("default_priority", 0):
        return Failure("UNSUPPORTED_PRIORITY", 7, "priority", "only the configured default priority is accepted")
    if ct == "SET_POSITION" and cmd["parameters"]["unit"] != POSITION_UNIT[j["joint_type"]]:
        return Failure("UNIT_MISMATCH", 7, "parameters.unit", f"a {j['joint_type']} joint uses {POSITION_UNIT[j['joint_type']]}")
    if ct == "SET_VELOCITY" and cmd["parameters"]["unit"] != VELOCITY_UNIT[j["joint_type"]]:
        return Failure("UNIT_MISMATCH", 7, "parameters.unit", f"a {j['joint_type']} joint uses {VELOCITY_UNIT[j['joint_type']]}")


def _constraint_failure(j, c):
    cont = j.get("continuous") is True
    if cont and ("position_min" in c or "position_max" in c):
        return ("constraints.position_min" if "position_min" in c else "constraints.position_max",
                "a joint without position limits takes no position constraint")
    if not cont:
        if "position_min" in c and c["position_min"] < j["position_min"]:
            return ("constraints.position_min", "widens the configured position minimum")
        if "position_max" in c and c["position_max"] > j["position_max"]:
            return ("constraints.position_max", "widens the configured position maximum")
    if "max_velocity" in c and c["max_velocity"] > j["velocity_max"]:
        return ("constraints.max_velocity", "widens the configured velocity maximum")
    if "max_acceleration" in c and "acceleration_max" in j and c["max_acceleration"] > j["acceleration_max"]:
        return ("constraints.max_acceleration", "widens the configured acceleration maximum")
    if "position_min" in c and "position_max" in c and c["position_min"] > c["position_max"]:
        return ("constraints.position_min", "position_min is above position_max")
    return None


def _step8(ctx):
    cmd = ctx.command
    ct = cmd["command_type"]
    j = _joint_of(ctx)
    if j is None:
        return None
    moves = ct in ("SET_POSITION", "SET_VELOCITY")
    if moves:
        c = cmd.get("constraints") or {}
        bad = _constraint_failure(j, c)
        if bad:
            return Failure("INVALID_CONSTRAINT", 8, bad[0], bad[1])
        eff = effective_limits(j, _backend_limit_entry(ctx, j["joint_id"]), c)
        if eff.empty:
            return Failure("INVALID_CONSTRAINT", 8, "constraints", "the effective position range is empty")
        p = cmd["parameters"]
        if ct == "SET_POSITION" and not (eff.position_min <= p["target_position"] <= eff.position_max):
            return Failure("LIMIT_POSITION", 8, "parameters.target_position", "outside the effective position limits")
        if ct == "SET_VELOCITY" and abs(p["target_velocity"]) > eff.velocity_max:
            return Failure("LIMIT_VELOCITY", 8, "parameters.target_velocity", "outside the effective velocity limit")
    for k, mx in (("deadline_ms", "max_deadline_ms"), ("execution_timeout_ms", "max_execution_timeout_ms")):
        if k in cmd and mx in j and cmd[k] > j[mx]:
            return Failure("INVALID_TIMEOUT", 8, k, f"exceeds the configured {mx}")
    return None


def _step9(ctx):
    ct = ctx.command["command_type"]
    j = _joint_of(ctx)
    if j is None or ct in ("CANCEL", "CLEAR_FAULT"):
        return None
    b = ctx.backend if isinstance(ctx.backend, dict) else None
    if b is None or b.get("health") not in BACKEND_HEALTH or b["health"] in UNAVAILABLE_BACKEND_HEALTH:
        return Failure("BACKEND_UNAVAILABLE", 9, "backend", "no available backend for the target")
    caps = b.get("capabilities") if isinstance(b.get("capabilities"), dict) else {}
    if j["joint_type"] not in caps.get("supported_joint_types", []):
        return Failure("BACKEND_CAPABILITY_UNSUPPORTED", 9, "backend.capabilities.supported_joint_types", "the backend does not declare the joint type")
    if ct == "SET_POSITION" and "position" not in caps.get("supported_modes", []):
        return Failure("BACKEND_CAPABILITY_UNSUPPORTED", 9, "backend.capabilities.supported_modes", "the backend does not declare position mode")
    if ct == "SET_VELOCITY" and "velocity" not in caps.get("supported_modes", []):
        return Failure("BACKEND_CAPABILITY_UNSUPPORTED", 9, "backend.capabilities.supported_modes", "the backend does not declare velocity mode")
    if ct == "STOP" and caps.get("controlled_stop") is not True:
        return Failure("BACKEND_CAPABILITY_UNSUPPORTED", 9, "backend.capabilities.controlled_stop", "the backend does not declare controlled stop")
    if ct == "HOLD" and caps.get("position_hold") is not True:
        return Failure("BACKEND_CAPABILITY_UNSUPPORTED", 9, "backend.capabilities.position_hold", "the backend does not declare position hold")
    if ct in ("SET_POSITION", "SET_VELOCITY") and _backend_limit_entry(ctx, j["joint_id"]) is None:
        return Failure("BACKEND_CAPABILITY_UNSUPPORTED", 9, "backend.joint_limits", "the backend declared neither numerical limits nor that it has no narrower limit")


def _step10(ctx):
    raise NotImplementedError("step 10 (joint state and preconditions) is delivered by a later change of KOS-MOTION-002")


def _step11(ctx):
    raise NotImplementedError("step 11 (arbitration) is delivered by a later change of KOS-MOTION-002")


STEPS = [(1, _step1), (2, _step2), (3, _step3), (4, _step4), (5, _step5), (6, _step6), (7, _step7),
         (8, _step8), (9, _step9), (10, _step10), (11, _step11)]


def first_failure(ctx, through_step=11):
    """Run steps 1 to `through_step` in the fixed order; return the first Failure, a replay
    marker for a stored decision, or None when no step failed. Steps above
    IMPLEMENTED_THROUGH_STEP raise NotImplementedError."""
    for n, fn in STEPS:
        if n > through_step:
            break
        r = fn(ctx)
        if r is not None:
            return r
    return None


def admit(ctx):
    """Public entry: the AdmissionResult for one context. Fails closed until steps 10 and 11 exist."""
    r = first_failure(ctx, 11)
    if isinstance(r, _Replay):
        d = r.decision
        return AdmissionResult(bool(d.get("accepted")), d.get("code"), 4, "client_request_id",
                               "stored decision of an identical request", True)
    if r is None:
        return AdmissionResult(True)
    return AdmissionResult(False, r.code, r.step, r.field, r.message)
