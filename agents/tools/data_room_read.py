"""Scoped data-room read tool (BUILD_PLAN D6-M1 toolset, vision §7.4).

ADK tool bound to one agent principal. Every read passes agent→data AuthZ
(``identity.authz``): a denied read emits a ``security.event`` through the
dispatcher and returns a machine-readable deny to the agent instead of
raising. Allowed reads resolve the document via a ``DocSource`` and return
parsed text plus located chunks.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from identity.authz import AuthzDenied, Resource
from identity.principals import Principal
from ingestion.chunking import chunk
from ingestion.parsing import LocalParser
from runtime.dispatcher import authorized_read
from runtime.events import EventEnvelope

_DATA_ROOTS = (
    Path(__file__).resolve().parents[2] / "data" / "vantage_robotics",
    Path(__file__).resolve().parents[2] / "data" / "scenarios",
)


class _EventPublisher(Protocol):
    def publish(self, event: EventEnvelope) -> str: ...


class DocSource(Protocol):
    def read(self, name: str) -> bytes | None: ...


class DatasetDocSource:
    """Offline doc source resolving names against the committed dataset dirs."""

    def __init__(self, roots: Sequence[Path] = _DATA_ROOTS) -> None:
        self._roots = tuple(roots)

    def read(self, name: str) -> bytes | None:
        if name != Path(name).name or name.startswith("."):
            return None
        for root in self._roots:
            candidate = root / name
            if candidate.is_file():
                return candidate.read_bytes()
        return None


def make_data_room_read(
    principal: Principal, publisher: _EventPublisher, doc_source: DocSource
) -> Any:
    """Bind the data-room-read tool to *principal* (one agent, one deal)."""

    def data_room_read(category: str, name: str) -> dict[str, Any]:
        """Read one data-room document, scoped to this agent's workstream.

        Args:
            category: Document category such as "contracts" or "financials".
            name: Document file name within the deal data room.

        Returns:
            Dict with "decision" ("allow" or "deny"). On allow: "document_id",
            "text" (null when the document needs OCR), "needs_ocr", and located
            "chunks". On deny: machine-readable "reason"
            ("workstream_boundary", "cross_deal", "invalid_resource",
            "not_found").
        """
        try:
            resource = Resource(
                deal_id=principal.deal_id, workstream=None, category=category, name=name
            )
        except ValueError as exc:
            return {"decision": "deny", "reason": "invalid_resource", "detail": str(exc)}
        try:
            authorized_read(principal, resource, publisher=publisher)
        except AuthzDenied as denied:
            return {"decision": "deny", "reason": denied.reason.value}
        blob = doc_source.read(name)
        if blob is None:
            return {"decision": "deny", "reason": "not_found"}
        parsed = LocalParser().parse(blob, name, principal.deal_id)
        if parsed.text is None:
            return {
                "decision": "allow",
                "document_id": name,
                "text": None,
                "needs_ocr": True,
                "chunks": [],
            }
        chunks = [
            {"locator": item.locator, "text": item.text, "kind": item.kind}
            for item in chunk(parsed)
        ]
        return {
            "decision": "allow",
            "document_id": name,
            "text": parsed.text,
            "needs_ocr": False,
            "chunks": chunks,
        }

    return data_room_read
