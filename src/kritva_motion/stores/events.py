"""Event streams, sequence numbers and the abstract event sink (contract 14; KOS-MOTION-005 PR-05).

`EventPublisher` takes the events an engine call produced (`Result.events`, in order), gives each a
unique `event_id` and the next sequence number of its stream (kind plus id), keeps the published log,
and offers each event to the attached sinks. A sink is anything with `deliver(event)`; no transport is
implied (14.2). A sink that raises or refuses is recorded and never changes the engine, the sequence
numbers or any result (14.2, 14.4); with no sink attached events are still numbered and kept. Events are
never the source of state: the status query stays authoritative (14.1, 14.5).

Sequence numbers start at 1 and rise by one per stream in publication order, whatever the sinks do.
`event_id` is "<kind>:<stream id>:<sequence number>", unique because a stream id and a number are.
`occurred_at` is the caller's UTC audit value, passed through. Time is never read here. Interpretations
(tasks/KOS-MOTION-005/STORES.md): I-39 (event id form, sink failure record, client identity on command
events) and finding F-8 (the engine emits no BACKEND_HEALTH_CHANGED or FEEDBACK_STATUS_CHANGED event).
"""
import copy

try:                                    # a Protocol only documents the port; nothing implements it in src
    from typing import Protocol
except ImportError:                     # pragma: no cover
    Protocol = object


class EventSink(Protocol):
    """The abstract event interface (14.2): one method. Raise to refuse an event."""

    def deliver(self, event):
        ...


class EventPublisher:
    def __init__(self, sinks=()):
        self._sinks = list(sinks)
        self._next = {}           # (kind, id) -> last sequence number issued
        self._log = []            # every published event, in publication order
        self._clients = {}        # command_id -> client_id (14.5)
        self._errors = []         # failed deliveries: sink index, event_id, error type

    def add_sink(self, sink):
        self._sinks.append(sink)

    def bind_client(self, command_id, client_id):
        """Remember the originating client of a command so its events carry `client_id` (14.5)."""
        if isinstance(client_id, str) and client_id:
            self._clients.setdefault(command_id, client_id)

    def publish(self, events):
        """Number and deliver events in order. Returns copies of the published events."""
        out = []
        for ev in events:
            kind, ident = ev["stream"]["kind"], ev["stream"]["id"]
            seq = self._next.get((kind, ident), 0) + 1
            self._next[(kind, ident)] = seq
            pub = {"event_id": f"{kind}:{ident}:{seq}", "stream": {"kind": kind, "id": ident},
                   "sequence_number": seq, "occurred_at": ev["occurred_at"], "event_type": ev["event_type"],
                   "data": copy.deepcopy(ev["data"])}
            if kind == "command" and ident in self._clients:
                pub["client_id"] = self._clients[ident]
            self._log.append(pub)
            for i, sink in enumerate(self._sinks):
                try:
                    sink.deliver(copy.deepcopy(pub))
                except Exception as exc:          # a failing sink never reaches the caller (14.2)
                    self._errors.append({"sink": i, "event_id": pub["event_id"], "error": type(exc).__name__})
            out.append(copy.deepcopy(pub))
        return out

    def last_sequence_number(self, kind, ident):
        """The last number issued for a stream, or 0 (the `last_sequence_number` of GET_COMMAND_STATUS, 14.1)."""
        return self._next.get((kind, ident), 0)

    def published(self):
        """Copies of the published log, oldest first."""
        return copy.deepcopy(self._log)

    def delivery_errors(self):
        return copy.deepcopy(self._errors)
