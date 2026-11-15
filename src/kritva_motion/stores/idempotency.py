"""Idempotency store (contract 7.3 and 7.4; KOS-MOTION-005 PR-03).

Entries are keyed by (client_id, client_request_id), so request identity is scoped to the client. The
store keeps the original decision of a submission, an acceptance or a rejection, for the retention
period. A lookup answers NEW, IDENTICAL (with the stored decision) or DIFFERENT, which is the supplied
lookup result that admission step 4 reads. Time is the injected monotonic reading; the system clock
is never read. A lookup never changes a stored entry; an entry that has reached its expiry is
dropped, after which the same ID is a new request (7.4).

Interpretations (tasks/KOS-MOTION-005/STORES.md): content identity is a canonical comparison of the
command fields without audit and transport fields (Q-3, refined in I-37); the retention minimum is
checked at activation (Q-2); a decision is recorded only when it was taken at admission step 4 or later,
because steps 1 to 3 come before the lookup and a REQUEST_ID_CONFLICT is not an original decision.
"""
import copy
import json

CONTENT_FIELDS = ("contract_version", "command_type", "target", "parameters", "constraints", "priority",
                  "deadline_ms", "execution_timeout_ms")
NEW, IDENTICAL, DIFFERENT = "NEW", "IDENTICAL", "DIFFERENT"


def content_key(command):
    """Canonical JSON over the content fields that are present (Q-3, I-37). `client_request_id`,
    `identity_assertion` and `issued_at` are excluded: the first is the key, the others are
    audit and transport fields."""
    picked = {f: command[f] for f in CONTENT_FIELDS if isinstance(command, dict) and f in command}
    return json.dumps(picked, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=repr)


def minimum_retention_ms(config):
    """The least retention contract 7.4 allows for a configuration: the longest effective execution
    timeout (the largest `max_execution_timeout_ms`) plus the termination-confirmation bound (the largest
    `termination_confirm_timeout_ms`)."""
    joints = config["joints"]
    return (max(j["max_execution_timeout_ms"] for j in joints)
            + max(j["termination_confirm_timeout_ms"] for j in joints))


def _usable(client_id, request_id):
    return (isinstance(client_id, str) and client_id != "" and isinstance(request_id, str) and request_id != "")


class IdempotencyStore:
    def __init__(self, retention_ms):
        if isinstance(retention_ms, bool) or not isinstance(retention_ms, (int, float)) or retention_ms <= 0:
            raise ValueError("retention_ms must be a positive number")
        self.retention_ms = retention_ms
        self._entries = {}

    def retention_problem(self, config):
        """None when the retention satisfies contract 7.4 for the configuration, else a description."""
        need = minimum_retention_ms(config)
        if self.retention_ms < need:
            return f"retention {self.retention_ms} ms is below the minimum {need} ms (7.4)"
        return None

    def lookup(self, client_id, request_id, command, now_ms):
        """The admission lookup result for one submission. Never changes a live entry."""
        if not _usable(client_id, request_id):
            return {"status": NEW}
        key = (client_id, request_id)
        e = self._entries.get(key)
        if e is not None and now_ms >= e["expires_at_ms"]:
            del self._entries[key]       # retention over: the ID is a new request again (7.4)
            e = None
        if e is None:
            return {"status": NEW}
        if e["content_key"] != content_key(command):
            return {"status": DIFFERENT}
        return {"status": IDENTICAL, "stored_decision": copy.deepcopy(e["decision"])}

    def record(self, client_id, request_id, command, decision, now_ms):
        """Store the original decision of a submission. Returns False and stores nothing when an entry
        for the key is still live (the first decision stays) or the key is unusable."""
        if not _usable(client_id, request_id):
            return False
        key = (client_id, request_id)
        e = self._entries.get(key)
        if e is not None and now_ms < e["expires_at_ms"]:
            return False
        self._entries[key] = {"client_id": client_id, "client_request_id": request_id,
                              "content_key": content_key(command), "decision": copy.deepcopy(decision),
                              "stored_at_ms": now_ms, "expires_at_ms": now_ms + self.retention_ms}
        return True

    def live_entries(self, now_ms):
        """Copies of the entries that have not expired, in key order (for tests and review)."""
        return [copy.deepcopy(e) for k, e in sorted(self._entries.items()) if now_ms < e["expires_at_ms"]]
