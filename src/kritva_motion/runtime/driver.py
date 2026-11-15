"""The runtime driver (KOS-MOTION-004 PR-04; contract 17.3 to 17.5, interpretations I-41 and I-43).

`Driver(engine, coordinator, backend)` connects the lifecycle engine and the stores to an execution backend
through the port of `kritva_motion.backend`:

- it executes the requests that engine calls return (`dispatch`, `request_hold`, `release_hold`,
  `request_termination`), after checking each against the backend's current declaration (17.3). A request the
  declaration does not allow is never sent; the engine is told through `execution_rejected` (a dispatch or a
  hold: the command ends FAILED(BACKEND_REJECTED_DISPATCH) with the undeclared capability named in the record
  detail), `hold_release_failed` or `termination_refused`;
- `poll(now_ms)` pulls the backend's reports in order, applies each to the engine once, then runs the engine's
  `tick`; a report for an unknown reference, with another target than the execution's, or not well formed is
  ignored and recorded in the driver log, never applied;
- request accepted is not confirmation: an accepted termination request only reaches `termination_request_accepted`;
  the engine ends the command when a confirmation bound to the reference and the target arrives, or marks it
  unconfirmed when its bound passes (17.5). The driver never decides an outcome itself;
- an exception from the port, or an answer that is not of the allowed shape, is a loss of the backend:
  `backend_fault(BACKEND_COMMUNICATION_LOSS)` and the engine's existing consequences.

Every engine Result is handed to the coordinator (history and events). No clock, no thread, no I/O. The `trace`
holds what crossed the backend boundary, in order, for the tests. Software evidence only.
"""
import copy
from collections import deque

from kritva_motion.backend import (DispatchAnswer, TerminationAnswer, is_backend, validate_declaration,
                                   validate_report)
from kritva_motion.lifecycle import model as m

OPERATION_MODE = {"SET_POSITION": "position", "SET_VELOCITY": "velocity"}


class DriverError(ValueError):
    """The backend given to the driver is not usable (not a port, or its declaration does not conform)."""


class Driver:
    def __init__(self, engine, coordinator, backend):
        if not is_backend(backend):
            raise DriverError("the backend does not implement the port")
        problems = validate_declaration(backend.describe_capabilities())
        if problems:
            raise DriverError("the backend declaration does not conform: " + "; ".join(str(p) for p in problems))
        self._engine, self._co, self._backend = engine, coordinator, backend
        self._refs = {}            # backend_reference -> command_id, from the requests that were issued
        self._inflight = set()     # command ids whose dispatch or hold the backend accepted
        self.log = []              # inputs the driver ignored or could not apply, with the reason
        self.trace = []            # what crossed the backend boundary, in order
        self._sync_description()

    # ------------------------------------------------------------------ public

    def submit(self, client_id, command, now_ms, utc=None, **kwargs):
        """Admit a command through the coordinator and the engine, then execute the requests it produced."""
        self._sync_description()
        res = self._co.submit(client_id, command, now_ms, utc, **kwargs)
        self._run([res], now_ms, utc, observed=True)
        return res

    def terminate(self, command_id, cause, now_ms, utc=None):
        res = self._engine.terminate(command_id, cause, now_ms, utc)
        self._run([res], now_ms, utc)
        return res

    def dispatch(self, command_id, now_ms, utc=None):
        res = self._engine.dispatch(command_id, now_ms, utc)
        self._run([res], now_ms, utc)
        return res

    def tick(self, now_ms, utc=None):
        res = self._engine.tick(now_ms, utc)
        self._run([res], now_ms, utc)
        return res

    def poll(self, now_ms, utc=None):
        """Pull the backend's reports, apply each once in the order produced, then run the engine tick. Returns
        every Result produced."""
        self._sync_description()
        out = []
        try:
            reports = list(self._backend.poll(now_ms))
        except Exception as exc:                      # a backend that cannot be polled is lost (I-43)
            out.append(self._lost("poll", type(exc).__name__, now_ms, utc))
            reports = []
        for report in reports:
            res = self._apply(report, now_ms, utc)
            if res is not None:
                out.append(res)
        out.append(self._engine.tick(now_ms, utc))
        self._run(out, now_ms, utc)
        return out

    def command_status(self, command_id):
        return self._co.command_status(command_id)

    # ------------------------------------------------------------------ internals

    def _ignored(self, kind, reference, reason, now_ms):
        self.log.append({"input": kind, "backend_reference": reference, "reason": reason, "monotonic_ms": now_ms})

    def _sync_description(self):
        try:
            self._engine.update_backend_description(self._backend.describe_capabilities())
        except Exception as exc:
            self.log.append({"input": "describe_capabilities", "backend_reference": None,
                             "reason": type(exc).__name__, "monotonic_ms": None})

    def _declaration(self):
        try:
            return self._backend.describe_capabilities()
        except Exception:
            return None

    def _run(self, results, now_ms, utc, observed=False):
        """Observe each Result (coordinator) and execute its requests; follow-up Results join the queue."""
        queue = deque((r, observed and i == 0) for i, r in enumerate(results))
        while queue:
            res, seen = queue.popleft()
            if not seen:
                self._co.observe(res)
            for req in res.requests:
                for follow in self._execute(req, now_ms, utc):
                    queue.append((follow, False))

    def _lost(self, where, why, now_ms, utc):
        """A port failure: the backend is treated as lost (communication loss); the engine decides the consequences."""
        self._ignored("backend_error", None, f"{where}: {why}", now_ms)
        return self._engine.backend_fault("BACKEND_COMMUNICATION_LOSS", now_ms, utc)

    def _active(self):
        self._inflight = {c for c in self._inflight
                          if (self._engine.command(c) or {}).get("state") not in m.TERMINAL_STATES}
        return len(self._inflight)

    def missing_capability(self, request, decl=None):
        """The name of the first capability that the current declaration lacks for this outgoing request (17.3), or
        None when it is declared. Public so the tests can ask the same question the driver asks."""
        decl = decl if decl is not None else self._declaration()
        if not isinstance(decl, dict):
            return "declaration"
        caps, op = decl.get("capabilities", {}), request["op"]
        if op in ("dispatch", "request_hold"):
            if request["target"]["type"] not in decl.get("supported_target_types", []):
                return "supported_target_types"
        if op == "dispatch":
            if OPERATION_MODE.get(request["operation"]) not in caps.get("supported_modes", []):
                return "capabilities.supported_modes"
            if self._engine.joint_type(request["target"]["id"]) not in caps.get("supported_joint_types", []):
                return "capabilities.supported_joint_types"
            if self._active() >= caps.get("max_concurrent_executions", 0):
                return "capabilities.max_concurrent_executions"
        elif op in ("request_hold", "release_hold"):
            if caps.get("position_hold") is not True:
                return "capabilities.position_hold"
        elif op == "request_termination":
            need = "execution_cancellation" if request["cause"] == "CANCEL_REQUESTED" else "controlled_stop"
            if caps.get(need) is not True:
                return "capabilities." + need
        return None

    def _target_of(self, command_id):
        return {"type": "joint", "id": self._engine.command(command_id)["target"]["id"]}

    def _execute(self, req, now_ms, utc):
        op, ref, cid = req["op"], req["backend_reference"], req["command_id"]
        self._refs[ref] = cid
        missing = self.missing_capability(req)
        if missing is not None:
            self._ignored(op, ref, f"capability not declared: {missing}", now_ms)
            if op in ("dispatch", "request_hold"):
                return [self._engine.execution_rejected(cid, ref, f"CAPABILITY_NOT_DECLARED: {missing}", now_ms, utc)]
            if op == "release_hold":
                return [self._engine.hold_release_failed(cid, ref, now_ms, utc)]
            return [self._engine.termination_refused(cid, ref, now_ms, utc)]
        self.trace.append({"at_ms": now_ms, "direction": "to_backend", "op": op, "command_id": cid,
                           "backend_reference": ref})
        target = req.get("target", {}).get("id")
        try:
            if op == "dispatch":
                ans = self._backend.dispatch(copy.deepcopy(req), now_ms)
            elif op == "request_hold":
                ans = self._backend.request_hold(ref, target, now_ms)
            elif op == "release_hold":
                ans = self._backend.release_hold(ref, target, now_ms)
            else:
                ans = self._backend.request_termination(ref, req["cause"], now_ms, target=copy.deepcopy(self._target_of(cid)))
        except Exception as exc:
            return [self._lost(op, type(exc).__name__, now_ms, utc)]
        if op == "request_termination":
            if not isinstance(ans, TerminationAnswer):
                return [self._lost(op, "answer is not a TerminationAnswer", now_ms, utc)]
            if ans.accepted:
                return [self._engine.termination_request_accepted(cid, ref, now_ms, utc)]
            return [self._engine.termination_refused(cid, ref, now_ms, utc)]
        if not isinstance(ans, DispatchAnswer):
            return [self._lost(op, "answer is not a DispatchAnswer", now_ms, utc)]
        if ans.accepted and ans.backend_reference != ref:
            return [self._lost(op, "the answer does not echo the backend reference", now_ms, utc)]
        if op == "release_hold":
            return [] if ans.accepted else [self._engine.hold_release_failed(cid, ref, now_ms, utc)]
        if ans.accepted:
            self._inflight.add(cid)
            return []
        return [self._engine.execution_rejected(cid, ref, ans.reason, now_ms, utc)]

    def _apply(self, report, now_ms, utc):
        """Apply one report to the engine; None when it was ignored (and logged)."""
        problems = validate_report(report)
        if problems:
            self._ignored("report", getattr(report, "backend_reference", None),
                          "malformed report: " + "; ".join(str(p) for p in problems), now_ms)
            return None
        k, e = report.kind, self._engine
        self.trace.append({"at_ms": now_ms, "direction": "from_backend", "kind": k,
                           "backend_reference": report.backend_reference, "simulated": report.simulated})
        if k == "feedback":
            return e.feedback(report.joint_id, copy.deepcopy(report.record), now_ms, utc)
        if k == "health":
            return e.backend_health(report.health, now_ms, utc)
        if k == "fault":
            return e.backend_fault(report.code, now_ms, utc, joints=list(report.joints) if report.joints else None)
        if k == "fault_cleared":
            return e.backend_fault_cleared(now_ms, utc, report.code)
        ref = report.backend_reference
        cid = self._refs.get(ref)
        if cid is None:
            self._ignored(k, ref, "unknown_reference", now_ms)
            return None
        if k == "termination_confirmed":
            joint = e.command(cid)["target"]["id"]
            if report.target != {"type": "joint", "id": joint}:
                self._ignored(k, ref, "target_mismatch", now_ms)     # confirmation is bound to the target (17.5)
                return None
            return e.termination_confirmed(cid, ref, now_ms, utc)
        if k == "execution_started":
            return e.execution_started(cid, ref, now_ms, utc)
        if k == "execution_rejected":
            return e.execution_rejected(cid, ref, report.reason, now_ms, utc)
        if k == "hold_confirmed":
            return e.hold_confirmed(cid, ref, now_ms, utc)
        if k == "hold_released":
            return e.hold_released(cid, ref, now_ms, utc)
        return e.hold_release_failed(cid, ref, now_ms, utc)
