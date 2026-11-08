"""Lifecycle engine, normal lifecycle and completion (KOS-MOTION-003, PR-02).

What this change implements (LIFECYCLE.md sections 3 to 5 and 8):

- admission through the KOS-MOTION-002 validator, with the AdmissionContext built from the engine's
  own state (interpretation I-2);
- the command lifecycle ACCEPTED, RUNNING, COMPLETED for SET_POSITION and SET_VELOCITY, with RUNNING
  only on a backend start confirmation (contract 7.2, 7.5);
- the dispatch request as returned data, carrying the command as received (contract 5.4, 5.5);
- completion from supplied evidence only (contract 12): SET_POSITION from valid fresh feedback that
  stays within tolerance for the settling duration, SET_VELOCITY with duration_ms from the injected
  monotonic clock since the confirmed start, SET_VELOCITY without duration never;
- effective deadline and execution timeout recorded in the command record (contract 10.3, 10.4);
- feedback records with the backend timestamp and the engine's own receipt time, and a flag for an
  unsynchronized backend clock (contract 10.2); freshness uses the receipt time only;
- a late, duplicate or unknown backend input is ignored and recorded (contract 7.5, CT-LC-03).

PR-03 adds the timing and termination half (LIFECYCLE.md sections 6 and 10, interpretations I-15 to I-19):
the command deadline and the execution timeout on the injected monotonic clock, the termination record
with its bounded wait, cancellation of one command by id, confirmed and unconfirmed termination, and the
joint fault that an unconfirmed termination leaves behind.

Not here yet (later pull requests of the task): STOP, HOLD, CANCEL commands and arbitration (PR-04);
other faults, degradation, recovery and CLEAR_FAULT (PR-05).
A command type that belongs to them raises NotImplementedError before any state changes.

Pure and deterministic: no system clock, no I/O, no randomness, no global state. Every public call
takes the caller's monotonic reading `now_ms`, which must never go backwards; UTC audit strings are
supplied by the caller and recorded as given. Software evidence only: nothing here shows that a
joint moved, stopped or settled physically (contract 2.2).
"""
import copy
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from kritva_motion import admission as ad
from kritva_motion.lifecycle import model as m

LATER_OPERATIONS = ("STOP", "HOLD", "CANCEL", "CLEAR_FAULT")
CANCEL_CAUSES = ("CANCEL_REQUESTED", "STOP_REQUESTED")   # causes a caller may give to terminate()
MOVEMENT = ("SET_POSITION", "SET_VELOCITY")


class ClockError(ValueError):
    """The supplied monotonic reading is not a finite number or went backwards."""


@dataclass
class Result:
    """What one call produced, in order. Nothing is delivered anywhere (LIFECYCLE.md section 5)."""
    admission: Optional[ad.AdmissionResult] = None
    command_id: Optional[str] = None
    requests: list = field(default_factory=list)   # backend requests, as data
    events: list = field(default_factory=list)     # event records of contract 14.3 without id or sequence number
    ignored: list = field(default_factory=list)    # inputs that changed nothing, with the reason


@dataclass
class _Command:
    command_id: str
    client_request_id: Any
    operation: str
    joint_id: str
    parameters: dict
    config_version: Any
    config_digest: Any
    accepted_at: Optional[str]
    accepted_ms: float
    deadline_ms: Any
    execution_timeout_ms: Any
    backend_reference: str
    state: str = "ACCEPTED"
    phase: str = "NONE"
    reason_code: Optional[str] = None
    started_ms: Optional[float] = None
    window_start_ms: Optional[float] = None    # SET_POSITION settling window (interpretation I-5)
    last_sample_ms: Optional[float] = None
    term: Optional[dict] = None                # the termination record (contract 10.6), once an attempt exists
    deadline_fired: bool = False
    timeout_fired: bool = False
    transitions: list = field(default_factory=list)


@dataclass
class _Joint:
    control_state: str = "UNKNOWN"   # contract 13.9: UNKNOWN until the backend confirms a state
    health_state: str = "READY"
    active_command_id: Optional[str] = None
    feedback: Optional[dict] = None       # the latest feedback record (valid or not)
    last_valid: Optional[dict] = None     # the latest record with validity VALID
    faults: list = field(default_factory=list)   # fault records; only TERMINATION_UNCONFIRMED in PR-03


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class LifecycleEngine:
    def __init__(self, config, backend, config_digest):
        """config: the validated active configuration (plain data); backend: the backend description
        used by admission (health, capabilities, joint_limits); config_digest: supplied by whoever
        activated the configuration (activation is not built here)."""
        self._config = copy.deepcopy(config)
        self._backend = copy.deepcopy(backend)
        self._digest = config_digest
        self._joint_cfg = {j["joint_id"]: j for j in self._config["joints"]}
        self._joints = {jid: _Joint() for jid in self._joint_cfg}
        self._commands = {}
        self._counter = 0
        self._fault_counter = 0
        self._last_now = None
        self.ignored_log = []

    # ------------------------------------------------------------------ clock

    def _advance(self, now_ms):
        if not _number(now_ms):
            raise ClockError("now_ms must be a finite number")
        if self._last_now is not None and now_ms < self._last_now:
            raise ClockError(f"the monotonic reading went backwards ({now_ms} < {self._last_now})")
        self._last_now = now_ms

    # ------------------------------------------------------------------ views

    def command(self, command_id):
        """A copy of one command record as plain data, or None."""
        c = self._commands.get(command_id)
        if c is None:
            return None
        return {"command_id": c.command_id, "operation": c.operation, "target": {"type": "joint", "id": c.joint_id},
                "state": c.state, "phase": c.phase, "reason_code": c.reason_code,
                "config_version": c.config_version, "config_digest": c.config_digest, "accepted_at": c.accepted_at,
                "deadline_ms": c.deadline_ms, "execution_timeout_ms": c.execution_timeout_ms,
                "backend_reference": c.backend_reference, "transitions": copy.deepcopy(c.transitions),
                "termination": copy.deepcopy(c.term)}

    def faults(self, joint_id):
        """Copies of the fault records of one joint, oldest first."""
        return copy.deepcopy(self._joints[joint_id].faults)

    def commands(self):
        return [self.command(cid) for cid in self._commands]

    def feedback_record(self, joint_id):
        """A copy of the latest feedback record for a joint (valid or not), or None. Both the backend
        timestamp and the engine's own receipt time are kept; clock_unsynchronized is true unless the
        backend declared its clock synchronized (an undeclared status fails closed)."""
        rec = self._joints[joint_id].feedback
        if rec is None:
            return None
        out = copy.deepcopy(rec)
        out["clock_unsynchronized"] = rec.get("clock_synchronized") is not True
        return out

    def _feedback_status(self, jid, now_ms):
        rec = self._joints[jid].feedback
        if rec is None:
            return "MISSING"
        if rec["validity"] != "VALID":
            return "INVALID"
        age = now_ms - rec["received_ms"]
        return "VALID" if 0 <= age <= self._joint_cfg[jid]["max_feedback_age_ms"] else "STALE"

    def joint_state(self, joint_id, now_ms):
        """The joint record of contract 13.2 and 13.5 (the motion-joint-state schema), as plain data.
        Reading it never changes anything; the monotonic reading must not go backwards."""
        self._advance(now_ms)
        return self._snapshot(joint_id, now_ms)

    def _snapshot(self, jid, now_ms):
        j = self._joints[jid]
        status = self._feedback_status(jid, now_ms)
        s = {"joint_id": jid, "control_state": j.control_state, "health_state": j.health_state,
             "feedback_status": status, "is_current": status == "VALID",
             "backend_status": self._backend["health"], "config_version": self._config["config_version"]}
        if j.active_command_id is not None:
            s["active_command_id"] = j.active_command_id
        if j.faults:
            s["fault_ids"] = [f["fault_id"] for f in j.faults]
        if j.last_valid is not None:
            s["measured_position"] = j.last_valid["measured_position"]
            if j.last_valid.get("measured_velocity") is not None:
                s["measured_velocity"] = j.last_valid["measured_velocity"]
        rec = j.feedback
        if rec is not None:
            for src, dst in (("backend_timestamp", "backend_timestamp"), ("clock_domain", "backend_clock_domain"),
                             ("clock_synchronized", "backend_clock_synchronized"), ("received_at", "received_at")):
                if rec.get(src) is not None:
                    s[dst] = rec[src]
        return s

    # ------------------------------------------------------------------ records and events

    def _event(self, kind, ident, event_type, utc, data):
        return {"stream": {"kind": kind, "id": ident}, "event_type": event_type, "occurred_at": utc, "data": data}

    def _joint_event(self, jid, utc, now_ms):
        return self._event("joint", jid, "JOINT_STATE_CHANGED", utc, self._snapshot(jid, now_ms))

    def _move(self, c, to, reason, now_ms, utc, trigger, res):
        """The only place a command state changes. Raises IllegalTransition for any pair not in 7.5."""
        m.check_transition(c.state, to, reason)
        frm, c.state = c.state, to
        c.reason_code = reason if to in m.TERMINAL_STATES else None
        old_phase = c.phase
        if c.phase not in m.PHASES_OF_STATE[to]:
            c.phase = "NONE"   # a terminal command, or a started one, has no dispatch phase (contract 7.6)
        c.transitions.append({"from": frm, "to": to, "reason_code": c.reason_code, "at": utc,
                              "monotonic_ms": now_ms, "trigger": trigger})
        res.events.append(self._event("command", c.command_id, "COMMAND_STATE_CHANGED", utc,
                                      {"from": frm, "to": to, "reason_code": c.reason_code, "phase": c.phase}))
        if c.phase != old_phase:
            res.events.append(self._event("command", c.command_id, "COMMAND_PHASE_CHANGED", utc, {"phase": c.phase}))

    def _set_phase(self, c, phase, utc, res):
        if phase not in m.PHASES_OF_STATE[c.state]:
            raise m.IllegalTransition(f"phase {phase} is not allowed on a {c.state} command")
        if c.phase != phase:
            c.phase = phase
            res.events.append(self._event("command", c.command_id, "COMMAND_PHASE_CHANGED", utc, {"phase": phase}))

    def _ignore(self, res, kind, command_id, reason, now_ms):
        entry = {"input": kind, "command_id": command_id, "reason": reason, "monotonic_ms": now_ms}
        self.ignored_log.append(entry)
        res.ignored.append(entry)

    # ------------------------------------------------------------------ admission and dispatch

    def _admission_context(self, command, now_ms, identity, permission_granted, human_operator_attested):
        records = {}
        for cid, c in self._commands.items():
            records[cid] = {"operation": c.operation, "state": c.state, "phase": c.phase,
                            "visible": True, "joint_id": c.joint_id}
        jid = None
        if isinstance(command, dict) and isinstance(command.get("target"), dict):
            jid = command["target"].get("id")
        snap, recv = None, None
        if jid in self._joints:
            snap = self._snapshot(jid, now_ms)
            fb = self._joints[jid].feedback
            recv = fb["received_ms"] if fb is not None else None
        return ad.AdmissionContext(
            command=command, identity=identity, permission_granted=permission_granted,
            active_config=self._config, commands=records, backend=self._backend, joint_state=snap,
            feedback_received_monotonic_ms=recv, reference_time_ms=now_ms,
            human_operator_attested=human_operator_attested)

    def submit(self, command, now_ms, utc=None, identity="VALID", permission_granted=True,
               human_operator_attested=False, defer_dispatch=False):
        """Admit one command. An accepted SET_POSITION or SET_VELOCITY becomes ACCEPTED with phase
        DISPATCH_PENDING and a dispatch request is returned; it stays ACCEPTED until the backend
        confirms the start (contract 7.2). A rejection creates no command and no lifecycle (7.3).
        With defer_dispatch=True no dispatch request is issued: the command stays ACCEPTED with phase
        NONE ("not dispatched", contract 7.6) until dispatch() is called (interpretation I-15)."""
        self._advance(now_ms)
        if isinstance(command, dict) and command.get("command_type") in LATER_OPERATIONS:
            raise NotImplementedError(f"{command['command_type']} belongs to a later pull request of KOS-MOTION-003")
        res = Result()
        ctx = self._admission_context(command, now_ms, identity, permission_granted, human_operator_attested)
        res.admission = ad.admit(ctx)
        if not res.admission.accepted or res.admission.replay:
            return res
        if command["command_type"] not in MOVEMENT:
            raise NotImplementedError(f"{command['command_type']} is not supported by this engine yet")
        jid = command["target"]["id"]
        cfg = self._joint_cfg[jid]
        self._counter += 1
        cid = f"cmd-{self._counter}"
        c = _Command(
            command_id=cid, client_request_id=command["client_request_id"], operation=command["command_type"],
            joint_id=jid, parameters=copy.deepcopy(command.get("parameters", {})),
            config_version=self._config["config_version"], config_digest=self._digest, accepted_at=utc,
            accepted_ms=now_ms,
            deadline_ms=command["deadline_ms"] if "deadline_ms" in command else cfg["default_deadline_ms"],
            execution_timeout_ms=(command["execution_timeout_ms"] if "execution_timeout_ms" in command
                                  else cfg["default_execution_timeout_ms"]),
            backend_reference="ref-" + cid)
        self._commands[cid] = c
        res.command_id = cid
        c.transitions.append({"from": None, "to": "ACCEPTED", "reason_code": None, "at": utc,
                              "monotonic_ms": now_ms, "trigger": "ADMISSION"})
        res.events.append(self._event("command", cid, "COMMAND_STATE_CHANGED", utc,
                                      {"from": None, "to": "ACCEPTED", "reason_code": None, "phase": "NONE"}))
        if not defer_dispatch:
            self._issue_dispatch(c, utc, res)
        return res

    def _issue_dispatch(self, c, utc, res):
        self._set_phase(c, "DISPATCH_PENDING", utc, res)
        res.requests.append({
            "op": "dispatch", "command_id": c.command_id, "backend_reference": c.backend_reference,
            "operation": c.operation, "target": {"type": "joint", "id": c.joint_id},
            "parameters": copy.deepcopy(c.parameters),
            "deadline_ms": c.deadline_ms, "execution_timeout_ms": c.execution_timeout_ms,
            "config_version": c.config_version, "config_digest": c.config_digest})

    def dispatch(self, command_id, now_ms, utc=None):
        """Issue the dispatch request of a command accepted with defer_dispatch=True (I-15).
        Ignored and recorded for an unknown, terminal, terminating or already dispatched command."""
        self._advance(now_ms)
        res = Result(command_id=command_id)
        c = self._commands.get(command_id)
        if c is None:
            self._ignore(res, "dispatch", command_id, "unknown_command", now_ms)
        elif c.state in m.TERMINAL_STATES:
            self._ignore(res, "dispatch", command_id, "terminal", now_ms)
        elif c.phase == "TERMINATING":
            self._ignore(res, "dispatch", command_id, "terminating", now_ms)
        elif c.state != "ACCEPTED" or c.phase != "NONE":
            self._ignore(res, "dispatch", command_id, "already_dispatched", now_ms)
        else:
            self._issue_dispatch(c, utc, res)
        return res

    # ------------------------------------------------------------------ backend inputs

    def execution_started(self, command_id, backend_reference, now_ms, utc=None):
        """The backend confirms that execution started (contract 17.5). The only way to RUNNING."""
        self._advance(now_ms)
        res = Result(command_id=command_id)
        c = self._commands.get(command_id)
        if c is None:
            self._ignore(res, "execution_started", command_id, "unknown_command", now_ms)
        elif backend_reference != c.backend_reference:
            self._ignore(res, "execution_started", command_id, "reference_mismatch", now_ms)
        elif c.state in m.TERMINAL_STATES:
            self._ignore(res, "execution_started", command_id, "terminal", now_ms)
        elif c.state == "RUNNING":
            self._ignore(res, "execution_started", command_id, "duplicate", now_ms)
        elif c.phase == "TERMINATING":
            self._ignore(res, "execution_started", command_id, "terminating", now_ms)   # never revives (7.6, INV-05)
        elif c.phase != "DISPATCH_PENDING":
            self._ignore(res, "execution_started", command_id, "not_dispatched", now_ms)
        else:
            self._move(c, "RUNNING", None, now_ms, utc, "EXECUTION_STARTED", res)
            c.started_ms = now_ms
            j = self._joints[c.joint_id]
            j.control_state, j.active_command_id = "ACTIVE", c.command_id
            res.events.append(self._joint_event(c.joint_id, utc, now_ms))
        return res

    def feedback(self, joint_id, record, now_ms, utc=None):
        """One feedback record (contract 11.1): measured_position, optional measured_velocity,
        validity ("VALID" or "INVALID"), backend_timestamp, clock_domain, clock_synchronized.
        The engine adds its own monotonic receipt time. It is the only evidence for SET_POSITION."""
        self._advance(now_ms)
        res = Result()
        if joint_id not in self._joints:
            self._ignore(res, "feedback", None, "unknown_joint", now_ms)
            return res
        validity = record.get("validity") if isinstance(record, dict) else None
        usable = (validity == "VALID" and _number(record.get("measured_position")))
        rec = {"validity": "VALID" if usable else "INVALID",
               "measured_position": record.get("measured_position") if usable else None,
               "measured_velocity": record.get("measured_velocity") if usable else None,
               "backend_timestamp": record.get("backend_timestamp") if isinstance(record, dict) else None,
               "clock_domain": record.get("clock_domain") if isinstance(record, dict) else None,
               "clock_synchronized": record.get("clock_synchronized") if isinstance(record, dict) else None,
               "received_ms": now_ms, "received_at": utc}
        j = self._joints[joint_id]
        prev = j.feedback
        j.feedback = rec
        if usable:
            j.last_valid = rec
        res.events.append(self._joint_event(joint_id, utc, now_ms))
        c = self._commands.get(j.active_command_id) if j.active_command_id else None
        if c is not None and c.state == "RUNNING" and c.operation == "SET_POSITION" and c.term is None:
            self._settle(c, rec, prev, now_ms, utc, res)
        return res

    def _settle(self, c, rec, prev, now_ms, utc, res):
        """Interpretation I-5: the settling window runs over consecutive valid samples within
        position_tolerance; a sample outside tolerance, an invalid sample, or a gap larger than
        max_feedback_age_ms since the previous sample restarts it. The command completes when a valid
        sample arrives at least settling_duration_ms after the window start. Only RUNNING commands
        count: samples before the confirmed start are not evidence."""
        cfg = self._joint_cfg[c.joint_id]
        inside = (rec["validity"] == "VALID"
                  and abs(rec["measured_position"] - c.parameters["target_position"]) <= cfg["position_tolerance"])
        if not inside:
            c.window_start_ms = c.last_sample_ms = None
            return
        gap = c.last_sample_ms is not None and now_ms - c.last_sample_ms > cfg["max_feedback_age_ms"]
        if c.window_start_ms is None or gap:
            c.window_start_ms = now_ms
        c.last_sample_ms = now_ms
        if now_ms - c.window_start_ms >= cfg["settling_duration_ms"]:
            self._complete(c, "GOAL_REACHED", now_ms, utc, res)

    def status_report(self, joint_id, control_state, age_ms, now_ms, utc=None):
        """An authoritative backend status report for a joint (contract 13.9, item 2). It can establish
        IDLE, ACTIVE or HOLDING only on a joint whose control state is UNKNOWN, only when it names a
        control state and is no older than max_feedback_age_ms; otherwise the state stays UNKNOWN.
        Only the establishment of a state is implemented here; the rest of 13.9 is PR-05."""
        self._advance(now_ms)
        res = Result()
        j = self._joints.get(joint_id)
        if j is None:
            self._ignore(res, "status_report", None, "unknown_joint", now_ms)
        elif j.control_state != "UNKNOWN":
            self._ignore(res, "status_report", None, "state_already_established", now_ms)
        elif (control_state not in ("IDLE", "ACTIVE", "HOLDING") or not _number(age_ms) or age_ms < 0
              or age_ms > self._joint_cfg[joint_id]["max_feedback_age_ms"]):
            self._ignore(res, "status_report", None, "partial_ambiguous_or_stale", now_ms)
        else:
            j.control_state = control_state
            res.events.append(self._joint_event(joint_id, utc, now_ms))
        return res

    # ------------------------------------------------------------------ time

    def tick(self, now_ms, utc=None):
        """Time passing. At one reading the passes run in this order (interpretation I-4): command
        deadlines, execution timeouts, termination bounds, SET_VELOCITY durations. Backend inputs
        supplied at the same reading must be applied before the tick (the caller orders them); a
        limit is reached when the elapsed time is at least the limit. Each pass visits the commands in
        the order they were accepted. Elapsed times use only the monotonic readings (contract 10.1)."""
        self._advance(now_ms)
        res = Result()
        cmds = list(self._commands.values())
        for c in cmds:      # command deadline: duration from acceptance until the start is confirmed (10.3)
            if (c.state == "ACCEPTED" and not c.deadline_fired and _number(c.deadline_ms)
                    and now_ms - c.accepted_ms >= c.deadline_ms):
                c.deadline_fired = True
                if c.term is not None:
                    self._append_cause(c, "DEADLINE_EXPIRED", now_ms, utc, res)
                elif c.phase == "NONE":
                    # never dispatched: nothing for the backend to terminate (10.3 asks for termination only "if already dispatched")
                    self._move(c, "FAILED", "DEADLINE_EXPIRED", now_ms, utc, "DEADLINE", res)
                else:
                    self._begin_termination(c, "DEADLINE_EXPIRED", now_ms, utc, res)
        for c in cmds:      # execution timeout: duration from the confirmed start (10.4)
            if (c.state == "RUNNING" and not c.timeout_fired and _number(c.execution_timeout_ms)
                    and now_ms - c.started_ms >= c.execution_timeout_ms):
                c.timeout_fired = True
                if c.term is not None:
                    self._append_cause(c, "EXECUTION_TIMEOUT", now_ms, utc, res)
                else:
                    self._begin_termination(c, "EXECUTION_TIMEOUT", now_ms, utc, res)
        for c in cmds:      # termination bound: started once, never restarted (10.6 rule 1, 3)
            if (c.state not in m.TERMINAL_STATES and c.term is not None and c.term["outcome"] == "PENDING"
                    and now_ms - c.term["requested_ms"] >= c.term["bound_ms"]):
                self._unconfirmed(c, now_ms, utc, res)
        for c in cmds:
            if (c.state == "RUNNING" and c.term is None and c.operation == "SET_VELOCITY"
                    and "duration_ms" in c.parameters and now_ms - c.started_ms >= c.parameters["duration_ms"]):
                self._complete(c, "DURATION_ELAPSED", now_ms, utc, res)
        return res

    # ------------------------------------------------------------------ cancellation and termination

    def terminate(self, command_id, cause, now_ms, utc=None):
        """Engine-level cancellation of one SET_POSITION or SET_VELOCITY command by id, with cause
        CANCEL_REQUESTED or STOP_REQUESTED (interpretation I-16). The CANCEL and STOP commands that
        carry these causes are PR-04; this is the lifecycle behaviour they will use.

        Not dispatched (ACCEPTED, phase NONE): the command ends CANCELLED at once, with no backend
        request, because the engine itself knows no dispatch was issued (contract 7.6).
        DISPATCH_PENDING or RUNNING: phase TERMINATING, one termination request goes to the backend,
        and the bounded wait starts. A second request for the same command only appends its cause:
        no second backend request, no new bound (10.6 rule 1). Nothing ends the command but the
        backend confirmation or the bound."""
        self._advance(now_ms)
        res = Result(command_id=command_id)
        if cause not in CANCEL_CAUSES:
            raise ValueError(f"cause must be one of {CANCEL_CAUSES}")
        c = self._commands.get(command_id)
        if c is None:
            self._ignore(res, "terminate", command_id, "unknown_command", now_ms)
        elif c.state in m.TERMINAL_STATES:
            self._ignore(res, "terminate", command_id, "terminal", now_ms)
        elif c.term is not None:
            self._append_cause(c, cause, now_ms, utc, res)
        elif c.state == "ACCEPTED" and c.phase == "NONE":
            self._move(c, "CANCELLED", "STOPPED" if cause == "STOP_REQUESTED" else "CANCEL_REQUESTED",
                       now_ms, utc, "CANCEL_BEFORE_DISPATCH", res)
        else:
            self._begin_termination(c, cause, now_ms, utc, res)
        return res

    def _begin_termination(self, c, cause, now_ms, utc, res):
        bound = self._joint_cfg[c.joint_id]["termination_confirm_timeout_ms"]
        c.term = {"causes": [], "requested_ms": now_ms, "requested_at": utc, "bound_ms": bound,
                  "outcome": "PENDING", "backend_accepted_ms": None}
        self._append_cause(c, cause, now_ms, utc, res)
        self._set_phase(c, "TERMINATING", utc, res)
        res.requests.append({"op": "request_termination", "command_id": c.command_id,
                             "backend_reference": c.backend_reference, "cause": cause})

    def _append_cause(self, c, cause, now_ms, utc, res):
        c.term["causes"].append({"cause": cause, "at": utc, "monotonic_ms": now_ms})

    def termination_request_accepted(self, command_id, backend_reference, now_ms, utc=None):
        """The backend accepted the termination request (contract 17.5). It is recorded and is never
        confirmation: the phase, the bound and the outcome do not change."""
        self._advance(now_ms)
        res = Result(command_id=command_id)
        c = self._commands.get(command_id)
        reason = self._termination_input_problem(c, backend_reference)
        if reason:
            self._ignore(res, "termination_request_accepted", command_id, reason, now_ms)
        elif c.term["backend_accepted_ms"] is not None:
            self._ignore(res, "termination_request_accepted", command_id, "duplicate", now_ms)
        else:
            c.term["backend_accepted_ms"] = now_ms
        return res

    def _termination_input_problem(self, c, backend_reference):
        if c is None:
            return "unknown_command"
        if backend_reference != c.backend_reference:
            return "reference_mismatch"
        if c.state in m.TERMINAL_STATES:
            return "terminal"
        if c.term is None or c.term["outcome"] != "PENDING":
            return "no_termination_outstanding"
        return None

    def termination_confirmed(self, command_id, backend_reference, now_ms, utc=None):
        """The backend confirms the identified execution reached its termination condition (17.5).
        Ends the command by the most consequential recorded cause (10.6 rule 2): a timeout or deadline
        cause gives FAILED with the one recorded first; only cancel and stop causes give CANCELLED,
        reason STOPPED if any STOP_REQUESTED is present, else CANCEL_REQUESTED. A confirmation that
        arrives after the bound ended the attempt, or for no attempt, is ignored and recorded."""
        self._advance(now_ms)
        res = Result(command_id=command_id)
        c = self._commands.get(command_id)
        reason = self._termination_input_problem(c, backend_reference)
        if reason:
            self._ignore(res, "termination_confirmed", command_id, reason, now_ms)
            return res
        c.term["outcome"] = "CONFIRMED"
        c.term["confirmed_ms"] = now_ms
        to, why = m.outcome_of_causes([x["cause"] for x in c.term["causes"]])
        self._move(c, to, why, now_ms, utc, "TERMINATION_CONFIRMED", res)
        self._release_joint(c, now_ms, utc, res)
        return res

    def _unconfirmed(self, c, now_ms, utc, res):
        """The bound expired (10.6 rule 3): FAILED(TERMINATION_UNCONFIRMED), the joint is FAULTED with
        that fault and its control state is UNKNOWN. The joint is never reported stopped."""
        c.term["outcome"] = "UNCONFIRMED"
        self._move(c, "FAILED", "TERMINATION_UNCONFIRMED", now_ms, utc, "TERMINATION_BOUND_EXPIRED", res)
        j = self._joints[c.joint_id]
        self._fault_counter += 1
        fault = {"fault_id": f"fault-{self._fault_counter}", "code": "TERMINATION_UNCONFIRMED",
                 "joint_id": c.joint_id, "command_id": c.command_id, "raised_at": utc, "raised_ms": now_ms}
        j.faults.append(fault)
        j.health_state, j.control_state = "FAULTED", "UNKNOWN"
        if j.active_command_id == c.command_id:
            j.active_command_id = None
        res.events.append(self._event("joint", c.joint_id, "JOINT_FAULT_RAISED", utc, copy.deepcopy(fault)))
        res.events.append(self._joint_event(c.joint_id, utc, now_ms))

    def _release_joint(self, c, now_ms, utc, res):
        """A confirmed termination frees the movement slot; an ACTIVE joint becomes IDLE (13.3)."""
        j = self._joints[c.joint_id]
        if j.active_command_id == c.command_id:
            j.active_command_id = None
            if j.control_state == "ACTIVE":
                j.control_state = "IDLE"
            res.events.append(self._joint_event(c.joint_id, utc, now_ms))

    def _complete(self, c, reason, now_ms, utc, res):
        self._move(c, "COMPLETED", reason, now_ms, utc, "COMPLETION", res)
        j = self._joints[c.joint_id]
        if j.active_command_id == c.command_id:
            j.active_command_id = None
            if j.control_state == "ACTIVE":
                j.control_state = "IDLE"   # contract 13.3: ACTIVE to IDLE on completion with no hold engaged
            res.events.append(self._joint_event(c.joint_id, utc, now_ms))
