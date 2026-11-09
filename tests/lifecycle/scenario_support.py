"""Scripted input streams for the lifecycle engine (KOS-MOTION-003 PR-06): the interpreter of one step, the
fault-injection scenario set of CT-TMO-07 and a snapshot of everything the engine records. Plain data in, plain
data out; no clock, no randomness, no I/O. Software evidence only: every fault, confirmation and report is a
supplied input, never proof that anything stopped or failed physically.

A step is a tuple (operation, *arguments), where an argument "@ref:cmd-N" stands for the backend reference
the engine assigned to that command. Times are explicit, non-decreasing monotonic readings in milliseconds.

  ("status", joint, control_state, age_ms, t)       ("feedback", joint, position, t[, validity])
  ("submit", spec, t[, options])                    ("dispatch", command_id, t)
  ("started", command_id, t)                        ("tick", t)
  ("term_accepted" | "term_confirmed" | "term_refused", command_id, t)
  ("hold_confirmed" | "hold_released" | "hold_release_failed", command_id, t)
  ("joint_fault", joint, code, t)                   ("backend_fault", code, t[, joints])
  ("backend_fault_cleared", t[, code])              ("backend_health", health, t)

spec is ("pos", joint, target[, options]), ("vel", joint, velocity[, options]), ("veld", joint, velocity, duration_ms),
("stop", joint), ("hold", joint),
("cancel", command_id) or ("clear", joint, fault_id); options are envelope fields such as deadline_ms.
"""
import copy

import lifecycle_support as S

JOINT, JOINT_2 = "joint-1", "joint-c"     # joint-1 is limited and in radians; joint-c is continuous
UNITS = {"joint-1": "rad", "joint-c": "rad"}
BOUND = 1000                                # termination_confirm_timeout_ms of the fixture configuration
FAR = 10_000_000                            # a reading far after every limit of the fixtures


def build_command(spec):
    kind, *rest = spec
    options = rest.pop() if rest and isinstance(rest[-1], dict) else {}
    if kind == "pos":
        return S.pos_cmd(rest[1], rest[0], UNITS.get(rest[0], "rad"), **options)
    if kind == "vel":
        return S.vel_cmd(rest[1], rest[0], UNITS.get(rest[0], "rad") + "/s", **options)
    if kind == "veld":      # a velocity command with a duration: ("veld", joint, velocity, duration_ms[, options])
        return S.vel_cmd(rest[1], rest[0], UNITS.get(rest[0], "rad") + "/s", duration=rest[2], **options)
    if kind == "stop":
        return S.stop_cmd(rest[0], **options)
    if kind == "hold":
        return S.hold_cmd(rest[0], **options)
    if kind == "cancel":
        return S.cancel_cmd(rest[0], **options)
    if kind == "clear":
        return S.env("CLEAR_FAULT", rest[0], parameters={"fault_id": rest[1]}, **options)
    raise ValueError(f"unknown command spec {kind!r}")


def _ref(e, x):
    if isinstance(x, str) and x.startswith("@ref:"):
        rec = e.command(x[5:])
        return rec["backend_reference"] if rec else "ref-unknown"
    return x


def apply(e, step):
    """Apply one step to the engine and return the Result (or None for a step that returns nothing)."""
    op, *a = step
    a = [_ref(e, x) for x in a]
    if op == "status":
        return e.status_report(a[0], a[1], a[2], a[3])
    if op == "feedback":
        validity = a[3] if len(a) > 3 else "VALID"
        return e.feedback(a[0], S.sample(a[1], validity=validity), a[2])
    if op == "submit":
        opts = dict(a[2]) if len(a) > 2 else {}
        opts.setdefault("human_operator_attested", True)
        return e.submit(build_command(a[0]), a[1], **opts)
    if op == "dispatch":
        return e.dispatch(a[0], a[1])
    if op == "started":
        return e.execution_started(a[0], _ref(e, "@ref:" + a[0]), a[1])
    if op == "tick":
        return e.tick(a[0])
    if op in ("term_accepted", "term_confirmed", "term_refused", "hold_confirmed", "hold_released",
              "hold_release_failed"):
        method = {"term_accepted": e.termination_request_accepted, "term_confirmed": e.termination_confirmed,
                  "term_refused": e.termination_refused, "hold_confirmed": e.hold_confirmed,
                  "hold_released": e.hold_released, "hold_release_failed": e.hold_release_failed}[op]
        return method(a[0], _ref(e, "@ref:" + a[0]), a[1])
    if op == "joint_fault":
        return e.joint_fault(a[0], a[1], a[2])
    if op == "backend_fault":
        return e.backend_fault(a[0], a[1], joints=a[2] if len(a) > 2 else None)
    if op == "backend_fault_cleared":
        return e.backend_fault_cleared(a[0], code=a[1] if len(a) > 1 else None)
    if op == "backend_health":
        return e.backend_health(a[0], a[1])
    raise ValueError(f"unknown step {op!r}")


def result_data(r):
    """A Result as plain data, so two runs can be compared for equality."""
    if r is None:
        return None
    adm = r.admission
    return {"admission": None if adm is None else repr(adm), "command_id": r.command_id,
            "requests": copy.deepcopy(r.requests), "events": copy.deepcopy(r.events),
            "ignored": copy.deepcopy(r.ignored)}


def run(steps, engine=None):
    """Apply every step in order. Returns (engine, outputs) with one plain-data output per step."""
    e = engine if engine is not None else S.engine()
    out = [result_data(apply(e, s)) for s in steps]
    return e, out


def settle(e, t=FAR, rounds=6):
    """Let every limit pass: one far reading, then one more after each termination bound that began (a limit that
    ends in a termination starts its bound at that reading). Stops as soon as no command is non-terminal."""
    out = []
    for i in range(rounds):
        out.append(result_data(e.tick(t + i * (BOUND + 1))))
        if all(c["state"] in ("COMPLETED", "CANCELLED", "FAILED") for c in e.commands()):
            break
    return out


def snapshot(e, t):
    """Everything the engine records, as plain data: commands with their transitions and termination records,
    the joint states, the fault records and the joint transitions of every joint."""
    joints = sorted(e._joints)
    return {"commands": e.commands(),
            "joints": {j: e.joint_state(j, t) for j in joints},
            "faults": {j: e.faults(j) for j in joints},
            "joint_transitions": {j: e.joint_transitions(j) for j in joints}}


def ready_both(t=0):
    return [("status", JOINT, "IDLE", 0, t), ("feedback", JOINT, 0.0, t),
            ("status", JOINT_2, "IDLE", 0, t), ("feedback", JOINT_2, 0.0, t)]


def _s(name, why, steps):
    return {"name": name, "why": why, "steps": ready_both() + steps}


# The fault-injection scenario set of CT-TMO-07 ("every fault-injection scenario" means exactly these; I-9).
# Every scenario injects at least one fault into a stream that holds accepted commands; the test then lets every
# limit pass and checks that each accepted command reached exactly one terminal state.
SCENARIOS = [
    _s("feedback-lost-then-stop-confirmed", "required feedback goes silent on a running movement; the stop is confirmed",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("tick", 202), ("term_accepted", "cmd-1", 210),
        ("term_confirmed", "cmd-1", 300)]),
    _s("feedback-lost-stop-never-confirmed", "as above, but the backend never confirms: the bound ends it",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("tick", 202), ("tick", 202 + BOUND)]),
    _s("tracking-error-while-running", "a reported tracking error on a running position command",
       [("submit", ("pos", JOINT, 0.5), 1), ("started", "cmd-1", 1), ("joint_fault", JOINT, "TRACKING_ERROR", 50),
        ("term_confirmed", "cmd-1", 80)]),
    _s("joint-limit-violation-after-dispatch", "a fault after dispatch and before the backend confirmed the start",
       [("submit", ("pos", JOINT, 0.5), 1), ("joint_fault", JOINT, "JOINT_LIMIT_VIOLATION", 20),
        ("term_confirmed", "cmd-1", 40)]),
    _s("fault-before-dispatch", "a fault while the command is accepted and was never dispatched",
       [("submit", ("pos", JOINT, 0.5), 1, {"defer_dispatch": True}), ("joint_fault", JOINT, "TRACKING_ERROR", 10)]),
    _s("late-start-after-fault", "the backend confirms a start after the fault began the termination",
       [("submit", ("vel", JOINT, 0.1), 1), ("joint_fault", JOINT, "TRACKING_ERROR", 10), ("started", "cmd-1", 20),
        ("term_confirmed", "cmd-1", 30)]),
    _s("backend-unavailable-two-joints", "a backend fault on every joint while two commands run",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("submit", ("vel", JOINT_2, 0.1), 2),
        ("started", "cmd-2", 2), ("backend_fault", "BACKEND_UNAVAILABLE", 60), ("term_confirmed", "cmd-1", 70)]),
    _s("backend-fault-one-joint-then-cleared", "a communication loss on one joint that later ends; no fault record clears",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("submit", ("vel", JOINT_2, 0.1), 2),
        ("started", "cmd-2", 2), ("backend_fault", "BACKEND_COMMUNICATION_LOSS", 60, [JOINT]),
        ("backend_fault_cleared", 100), ("term_confirmed", "cmd-1", 110)]),
    _s("backend-execution-failure-no-confirmation", "an execution failure; the termination is refused by silence",
       [("submit", ("pos", JOINT, 0.5), 1), ("started", "cmd-1", 1),
        ("backend_fault", "BACKEND_EXECUTION_FAILURE", 30)]),
    _s("pending-hold-then-fault", "a HOLD waiting for engagement meets a fault",
       [("submit", ("hold", JOINT), 1), ("joint_fault", JOINT, "TRACKING_ERROR", 20), ("term_confirmed", "cmd-1", 40)]),
    _s("fault-during-stop", "a fault reaches a joint while its STOP is waiting for confirmation",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("submit", ("stop", JOINT), 10),
        ("joint_fault", JOINT, "TRACKING_ERROR", 20), ("term_confirmed", "cmd-1", 40)]),
    _s("fault-during-cancel", "a fault reaches a joint while a CANCEL of its command is outstanding",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("submit", ("cancel", "cmd-1"), 10),
        ("joint_fault", JOINT, "JOINT_LIMIT_VIOLATION", 20), ("term_confirmed", "cmd-1", 40)]),
    _s("stop-refused-then-fault", "the backend refuses a STOP on an idle joint, then a movement meets a fault",
       [("submit", ("stop", JOINT), 10), ("term_refused", "cmd-1", 15), ("submit", ("vel", JOINT, 0.1), 20),
        ("started", "cmd-2", 21), ("joint_fault", JOINT, "TRACKING_ERROR", 30)]),
    _s("deadline-passes-during-fault", "a command never started; its deadline and a fault both apply",
       [("submit", ("pos", JOINT, 0.5, {"deadline_ms": 100}), 1), ("joint_fault", JOINT, "TRACKING_ERROR", 50),
        ("tick", 150)]),
    _s("execution-timeout-unconfirmed-then-fault", "a timeout begins the termination, a fault joins it, nothing is confirmed",
       [("submit", ("vel", JOINT, 0.1, {"execution_timeout_ms": 100}), 1), ("started", "cmd-1", 1),
        ("feedback", JOINT, 0.0, 90), ("tick", 101), ("joint_fault", JOINT, "TRACKING_ERROR", 200)]),
    _s("duplicate-fault-and-confirmation", "the same fault and the same confirmation reported twice",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("joint_fault", JOINT, "TRACKING_ERROR", 20),
        ("joint_fault", JOINT, "TRACKING_ERROR", 21), ("term_confirmed", "cmd-1", 30), ("term_confirmed", "cmd-1", 31),
        ("started", "cmd-1", 32)]),
    _s("clear-fault-then-new-fault", "an accepted CLEAR_FAULT is overtaken by a new fault before it is applied",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("joint_fault", JOINT, "TRACKING_ERROR", 20),
        ("term_confirmed", "cmd-1", 30), ("submit", ("clear", JOINT, "fault-1"), 40, {"defer_dispatch": True}),
        ("joint_fault", JOINT, "JOINT_LIMIT_VIOLATION", 50), ("dispatch", "cmd-2", 60)]),
    _s("clear-fault-applied", "recovery: fault, confirmed stop, CLEAR_FAULT applied; later motion is accepted",
       [("submit", ("vel", JOINT, 0.1), 1), ("started", "cmd-1", 1), ("joint_fault", JOINT, "TRACKING_ERROR", 20),
        ("term_confirmed", "cmd-1", 30), ("submit", ("clear", JOINT, "fault-1"), 40),
        ("feedback", JOINT, 0.0, 41), ("submit", ("pos", JOINT, 0.2), 50), ("started", "cmd-3", 51)]),
    _s("hold-engaged-then-fault", "a confirmed hold is faulted; the hold's own command is already terminal",
       [("submit", ("hold", JOINT), 1), ("started", "cmd-1", 2), ("hold_confirmed", "cmd-1", 5),
        ("joint_fault", JOINT, "TRACKING_ERROR", 20), ("submit", ("stop", JOINT), 30), ("term_confirmed", "cmd-2", 40)]),
    _s("movement-releases-hold-then-fault", "a movement releases a hold and a fault arrives before the release is confirmed",
       [("submit", ("hold", JOINT), 1), ("started", "cmd-1", 2), ("hold_confirmed", "cmd-1", 5),
        ("submit", ("pos", JOINT, 0.5), 10), ("started", "cmd-2", 11), ("joint_fault", JOINT, "TRACKING_ERROR", 12), ("hold_release_failed", "cmd-2", 13)]),
]


def records(e):
    """The recorded facts that no later input may change once a command is terminal: the commands with their
    transitions and termination records, the fault records and the joint transitions (no time-dependent view)."""
    joints = sorted(e._joints)
    return {"commands": e.commands(), "faults": {j: e.faults(j) for j in joints},
            "joint_transitions": {j: e.joint_transitions(j) for j in joints}}
