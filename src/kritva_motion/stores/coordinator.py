"""Coordinator (KOS-MOTION-005): wires the stores around one engine for a submission. It holds no
lifecycle logic. PR-03 wired the idempotency store, PR-04 the command history and PR-05 adds the
event publisher. Software evidence only."""
import copy


class Coordinator:
    def __init__(self, engine, idempotency, history=None, publisher=None):
        self._engine = engine
        self._idem = idempotency
        self._history = history
        self._publisher = publisher

    def submit(self, client_id, command, now_ms, utc=None, **kwargs):
        """Admit one submission for a client. An identical resubmission inside the retention period
        returns the stored original result (`admission.replay` is True, the original `command_id`) and
        creates no second command; the same request ID with different content is REQUEST_ID_CONFLICT.
        Every submission that is not a replay gets one history record, accepted or rejected."""
        req = command.get("client_request_id") if isinstance(command, dict) else None
        lookup = self._idem.lookup(client_id, req, command, now_ms)
        res = self._engine.submit(command, now_ms, utc, idempotency=lookup, **kwargs)
        adm = res.admission
        if adm.replay:
            res.command_id = lookup["stored_decision"].get("command_id")
            seq = lookup["stored_decision"].get("history_sequence")
            if self._history is not None and seq is not None:
                self._history.append_replay(seq, utc, now_ms)
            return res
        seq = self._record_history(client_id, command, res, now_ms, utc, kwargs)
        if adm.accepted and self._publisher is not None:
            self._publisher.bind_client(res.command_id, client_id)
        if lookup["status"] == "NEW" and (adm.accepted or adm.step is None or adm.step >= 4):
            self._idem.record(client_id, req, command, self._decision(res, seq), now_ms)
        self.observe(res)
        return res

    def observe(self, result):
        """Take the Result of any engine call: append its command events to the history (one lifecycle
        entry per state or phase change, a reference for every fault a termination cause names) and
        publish all its events. A Result is taken once; a second call with the same Result does nothing.
        Callers pass the Result of every engine call they make; entries are only ever appended."""
        if getattr(result, "_observed", False):
            return
        result._observed = True
        if self._history is not None:
            self._to_history(result)
        if self._publisher is not None:
            self._publisher.publish(result.events)

    def command_status(self, command_id):
        """GET_COMMAND_STATUS (14.1): the engine's authoritative view plus `last_sequence_number` of the
        command's event stream."""
        view = self._engine.command(command_id)
        if view is not None and self._publisher is not None:
            view["last_sequence_number"] = self._publisher.last_sequence_number("command", command_id)
        return view

    def _to_history(self, result):
        for ev in result.events:
            st = ev["stream"]
            if st["kind"] != "command" or self._history.sequence_of(st["id"]) is None:
                continue
            cid, d = st["id"], ev["data"]
            if ev["event_type"] == "COMMAND_STATE_CHANGED":
                self._history.append_lifecycle(cid, {"state": d["to"], "phase": d["phase"],
                                                     "reason_code": d["reason_code"], "at": ev["occurred_at"]})
            elif ev["event_type"] == "COMMAND_PHASE_CHANGED":
                life = self._history.get(cid)["lifecycle_history"]
                self._history.append_lifecycle(cid, {"state": life[-1]["state"] if life else None,
                                                     "phase": d["phase"], "reason_code": None,
                                                     "at": ev["occurred_at"]})
            term = self._engine.command(cid)["termination"]
            for cause in (term or {}).get("causes", []):
                if "fault_id" in cause:
                    self._history.append_fault_reference(cid, cause["fault_id"])

    def _record_history(self, client_id, command, res, now_ms, utc, kwargs):
        if self._history is None:
            return None
        adm = res.admission
        env = command if isinstance(command, dict) else {}
        rec = {"client_id": client_id, "client_request_id": env.get("client_request_id"),
               "operation": env.get("command_type"), "target": copy.deepcopy(env.get("target")),
               "submitted_at": utc, "validation_result": {"accepted": adm.accepted, "code": adm.code,
                                                          "step": adm.step, "field": adm.field},
               "authorization_outcome": {"identity": kwargs.get("identity", "VALID"),
                                         "permission_granted": kwargs.get("permission_granted", True)},
               "submission_result": "ACCEPTED" if adm.accepted else "REJECTED", "command_id": None}
        if adm.accepted:
            c = self._engine.command(res.command_id)
            rec.update(command_id=c["command_id"], accepted_at=c["accepted_at"],
                       backend_reference=c["backend_reference"], config_version=c["config_version"],
                       config_digest=c["config_digest"], deadline_ms=c["deadline_ms"],
                       execution_timeout_ms=c["execution_timeout_ms"])
        else:
            rec.update(accepted_at=None, backend_reference=None, config_version=None, config_digest=None,
                       deadline_ms=None, execution_timeout_ms=None)
        return self._history.append_submission(rec, now_ms)

    def _decision(self, res, seq):
        adm = res.admission
        d = {"accepted": adm.accepted, "code": adm.code, "step": adm.step, "field": adm.field,
             "message": adm.message, "command_id": res.command_id, "history_sequence": seq}
        if adm.accepted:
            c = self._engine.command(res.command_id)
            d.update(config_version=c["config_version"], config_digest=c["config_digest"],
                     accepted_at=c["accepted_at"])
        return d
