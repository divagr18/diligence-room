"""Gateway audit delegation layer (BUILD_PLAN D3-M4).

Thin wrapper over memory.event_log.EventLog — the canonical append-only
event writer. Public names (AuditRecord, DealEventAuditLog) are preserved
for backward compatibility with existing tests and runtime code.
"""

from __future__ import annotations

from google.cloud import firestore

from memory.event_log import EventLog, EventRecord
from runtime.events import EventEnvelope

# Type alias: fields are identical, so no conversion needed
AuditRecord = EventRecord


class DealEventAuditLog:
    """Firestore-backed append-only audit log for deal events.

    Each deal has an independent monotonic seq counter starting at 1.
    Append is idempotent on event_id: a duplicate returns the stored seq.

    Delegates to memory.event_log.EventLog (Day-3 canonical writer).
    """

    def __init__(self, client: firestore.Client) -> None:
        self._event_log = EventLog(client)

    def append(self, envelope: EventEnvelope) -> int:
        return self._event_log.append(envelope)

    def events(self, deal_id: str) -> list[AuditRecord]:
        return self._event_log.events(deal_id)
