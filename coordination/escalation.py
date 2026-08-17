"""Escalation path (BUILD_PLAN D7-M6, vision §10 escalation policy).

Critical findings automatically notify the deal lead: an audit event
(``finding.escalated``) plus a dashboard-readable inbox entry under
``deals/{deal_id}/inbox/{finding_id}``. Non-critical findings never escalate.
When no publisher is supplied, the inbox entry is still written — event
emission follows the optional-publisher convention of the agent tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from google.cloud import firestore

from memory.findings import Finding, FindingSeverity
from runtime.events import EventEnvelope, EventType, new_event

_ESCALATION_ACTOR = "coordination-escalation"
_INBOX_COLLECTION = "inbox"
_ENTRY_KIND = "escalation"
_ENTRY_STATUS_OPEN = "open"


@dataclass(frozen=True, slots=True)
class EscalationRecord:
    """One deal-lead escalation for a critical finding."""

    finding_id: str
    deal_id: str
    severity: str
    workstream: str
    title: str
    owner: str
    message: str
    created_at: datetime


class _Publisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


def _message_for(finding: Finding) -> str:
    return f"Critical {finding.workstream.value} finding requires deal-lead review: {finding.title}"


def escalate_critical(
    client: firestore.Client,
    publisher: _Publisher | None,
    finding: Finding,
    now: datetime | None = None,
) -> EscalationRecord:
    """Escalate a CRITICAL finding to the deal lead; reject anything else."""
    if finding.severity is not FindingSeverity.CRITICAL:
        raise ValueError(
            f"finding {finding.finding_id} is {finding.severity.value}; "
            "only critical findings escalate"
        )
    stamp = now if now is not None else datetime.now(UTC)
    record = EscalationRecord(
        finding_id=finding.finding_id,
        deal_id=finding.deal_id,
        severity=finding.severity.value,
        workstream=finding.workstream.value,
        title=finding.title,
        owner=finding.owner,
        message=_message_for(finding),
        created_at=stamp,
    )
    client.collection("deals").document(record.deal_id).collection(_INBOX_COLLECTION).document(
        record.finding_id
    ).set(
        {
            "kind": _ENTRY_KIND,
            "finding_id": record.finding_id,
            "title": record.title,
            "severity": record.severity,
            "workstream": record.workstream,
            "owner": record.owner,
            "message": record.message,
            "status": _ENTRY_STATUS_OPEN,
            "created_at": record.created_at.isoformat(),
        }
    )
    if publisher is not None:
        publisher.publish(
            new_event(
                record.deal_id,
                _ESCALATION_ACTOR,
                EventType.FINDING_ESCALATED,
                {
                    "finding_id": record.finding_id,
                    "title": record.title,
                    "severity": record.severity,
                    "workstream": record.workstream,
                    "owner": record.owner,
                    "message": record.message,
                },
                now=stamp,
            )
        )
    return record


def escalate_if_critical(
    client: firestore.Client,
    publisher: _Publisher | None,
    finding: Finding,
    now: datetime | None = None,
) -> EscalationRecord | None:
    """Escalate when the finding is critical; return None otherwise."""
    if finding.severity is not FindingSeverity.CRITICAL:
        return None
    return escalate_critical(client, publisher, finding, now=now)
