"""Command history (contract 15; KOS-MOTION-005 PR-04).

One record per submission with the fields of 15.1 that this layer can fill. Accepted and rejected
submissions are kept apart (`submission_result`), a rejected submission has no `command_id` and no
lifecycle (7.3), and the store has no operation that overwrites or deletes an entry: it can only
append a submission, a lifecycle entry, a fault reference or a replay marker. Fields that depend on
a lifecycle (`execution_started_at`, `completed_at`, `result`) are derived on read from the appended
lifecycle entries, so an earlier entry can never be changed. Retention is a parameter; `purge` drops
whole records that are past it and, for an accepted command, only once the command is terminal.

In memory only, no durability claim (15.2). Time is the injected monotonic reading. Interpretations
(tasks/KOS-MOTION-005/STORES.md): an idempotent replay is not a new record, it is appended to the
original record's `replays` (I-38); fields that depend on a supplied result are recorded as supplied.
"""
import copy

TERMINAL = ("COMPLETED", "CANCELLED", "FAILED")
ACCEPTED, REJECTED = "ACCEPTED", "REJECTED"


class CommandHistory:
    def __init__(self, retention_ms):
        if isinstance(retention_ms, bool) or not isinstance(retention_ms, (int, float)) or retention_ms <= 0:
            raise ValueError("retention_ms must be a positive number")
        self.retention_ms = retention_ms
        self._subs = []          # submission entries, oldest first
        self._by_command = {}    # command_id -> submission entry
        self._life = {}          # command_id -> lifecycle entries, oldest first
        self._faults = {}        # command_id -> fault ids, in the order first seen
        self._replays = {}       # submission sequence -> replay markers

    # -- appends (the only way the store changes) ------------------------------------------------
    def append_submission(self, record, now_ms):
        """Append the record of one submission and return its sequence number (from 1)."""
        entry = copy.deepcopy(record)
        entry["sequence"] = len(self._subs) + 1
        entry["recorded_ms"] = now_ms
        cid = entry.get("command_id")
        if entry["submission_result"] == REJECTED and cid is not None:
            raise ValueError("a rejected submission has no command_id (contract 7.3)")
        if entry["submission_result"] == ACCEPTED:
            if cid is None or cid in self._by_command:
                raise ValueError("an accepted submission needs a new command_id")
            self._by_command[cid] = entry
            self._life[cid] = []
            self._faults[cid] = []
        self._subs.append(entry)
        return entry["sequence"]

    def append_lifecycle(self, command_id, entry):
        """Append one lifecycle entry (state, phase, reason_code, at). Earlier entries are untouched."""
        if command_id not in self._life:
            raise KeyError(command_id)
        self._life[command_id].append(copy.deepcopy(entry))

    def append_fault_reference(self, command_id, fault_id):
        """Append a fault reference once; a repeat is ignored. Returns True when it was added."""
        if command_id not in self._faults:
            raise KeyError(command_id)
        if fault_id in self._faults[command_id]:
            return False
        self._faults[command_id].append(fault_id)
        return True

    def append_replay(self, sequence, at, now_ms):
        """Note that the original submission was replayed (an identical resubmission, 7.4)."""
        self._replays.setdefault(sequence, []).append({"at": at, "recorded_ms": now_ms})

    # -- reads -----------------------------------------------------------------------------------
    def read(self):
        """Copies of every record, oldest first."""
        return [self._record(e) for e in self._subs]

    def get(self, command_id):
        e = self._by_command.get(command_id)
        return None if e is None else self._record(e)

    def accepted(self):
        return [r for r in self.read() if r["submission_result"] == ACCEPTED]

    def rejected(self):
        return [r for r in self.read() if r["submission_result"] == REJECTED]

    def sequence_of(self, command_id):
        e = self._by_command.get(command_id)
        return None if e is None else e["sequence"]

    # -- retention -------------------------------------------------------------------------------
    def purge(self, now_ms):
        """Drop whole records older than the retention period (15.2). An accepted command that is not
        terminal is kept. Returns the sequence numbers dropped. Nothing is ever rewritten."""
        keep, dropped = [], []
        for e in self._subs:
            old = now_ms - e["recorded_ms"] >= self.retention_ms
            live = e["submission_result"] == ACCEPTED and not self._terminal_entry(e["command_id"])
            (keep if (not old or live) else dropped).append(e)
        for e in dropped:
            self._replays.pop(e["sequence"], None)
            cid = e.get("command_id")
            if cid is not None:
                self._by_command.pop(cid, None)
                self._life.pop(cid, None)
                self._faults.pop(cid, None)
        self._subs = keep
        return [e["sequence"] for e in dropped]

    # -- internals -------------------------------------------------------------------------------
    def _terminal_entry(self, cid):
        return next((x for x in self._life.get(cid, []) if x.get("state") in TERMINAL), None)

    def _record(self, e):
        r = copy.deepcopy({k: v for k, v in e.items() if k != "recorded_ms"})
        r["replays"] = copy.deepcopy(self._replays.get(e["sequence"], []))
        if e["submission_result"] == ACCEPTED:
            cid = e["command_id"]
            life = self._life[cid]
            started = next((x for x in life if x.get("state") == "RUNNING"), None)
            done = self._terminal_entry(cid)
            r["lifecycle_history"] = copy.deepcopy(life)
            r["execution_started_at"] = None if started is None else started.get("at")
            r["completed_at"] = None if done is None else done.get("at")
            r["fault_references"] = list(self._faults[cid])
            r["result"] = ({"state": done["state"], "reason_code": done.get("reason_code")}
                           if done is not None else {"state": "PENDING"})
        else:
            r["lifecycle_history"] = None
            r["execution_started_at"] = r["completed_at"] = None
            r["fault_references"] = []
            r["result"] = {"state": "REJECTED", "code": e["validation_result"].get("code")}
        return r
