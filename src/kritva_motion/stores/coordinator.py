"""Coordinator (KOS-MOTION-005): wires the stores around one engine for a submission. It holds no
lifecycle logic. PR-03 wires the idempotency store; the history and the event publisher join in PR-04
and PR-05. Software evidence only."""

class Coordinator:
    def __init__(self, engine, idempotency):
        self._engine = engine
        self._idem = idempotency

    def submit(self, client_id, command, now_ms, utc=None, **kwargs):
        """Admit one submission for a client. An identical resubmission inside the retention period
        returns the stored original result (`admission.replay` is True, the original `command_id`) and
        creates no second command; the same request ID with different content is REQUEST_ID_CONFLICT."""
        req = command.get("client_request_id") if isinstance(command, dict) else None
        lookup = self._idem.lookup(client_id, req, command, now_ms)
        res = self._engine.submit(command, now_ms, utc, idempotency=lookup, **kwargs)
        adm = res.admission
        if adm.replay:
            res.command_id = lookup["stored_decision"].get("command_id")
            return res
        if lookup["status"] == "NEW" and (adm.accepted or adm.step is None or adm.step >= 4):
            self._idem.record(client_id, req, command, self._decision(res), now_ms)
        return res

    def _decision(self, res):
        adm = res.admission
        d = {"accepted": adm.accepted, "code": adm.code, "step": adm.step, "field": adm.field,
             "message": adm.message, "command_id": res.command_id}
        if adm.accepted:
            c = self._engine.command(res.command_id)
            d.update(config_version=c["config_version"], config_digest=c["config_digest"],
                     accepted_at=c["accepted_at"])
        return d
