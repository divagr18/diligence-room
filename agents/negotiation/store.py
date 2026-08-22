"""Negotiation persistence (BUILD_PLAN D9-M4 / D12-M6, vision §11).

Artifact kinds, the approval state vocabulary, the frozen draft record, and
the Firestore-backed store at deals/{deal_id}/negotiations/{draft_id}. The
state machine and its transitions live in ``drafts.py``; this module owns
only the registry and the persistence seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, cast

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

_COLLECTION: Final[str] = "negotiations"


class NegotiationArtifactKind(StrEnum):
    REDLINE = "clause_redline"
    SELLER_REQUEST = "seller_request"
    CLARIFICATION_QUESTION = "clarification_question"


class NegotiationState(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SEND_LOGGED = "send_logged"


class DraftNotFound(KeyError):
    """Raised when a negotiation draft does not exist in Firestore."""


@dataclass(frozen=True, slots=True)
class NegotiationDraft:
    """One negotiation artifact bound to one finding."""

    draft_id: str
    deal_id: str
    finding_id: str
    kind: NegotiationArtifactKind
    state: NegotiationState
    body: str
    approved_by: str | None
    created_at: datetime
    updated_at: datetime


def _draft_to_doc(draft: NegotiationDraft) -> dict[str, object]:
    return {
        "draft_id": draft.draft_id,
        "deal_id": draft.deal_id,
        "finding_id": draft.finding_id,
        "kind": draft.kind.value,
        "state": draft.state.value,
        "body": draft.body,
        "approved_by": draft.approved_by,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


def _draft_from_doc(doc: dict[str, object]) -> NegotiationDraft:
    raw_approved_by = doc.get("approved_by")
    return NegotiationDraft(
        draft_id=str(doc["draft_id"]),
        deal_id=str(doc["deal_id"]),
        finding_id=str(doc["finding_id"]),
        kind=NegotiationArtifactKind(str(doc["kind"])),
        state=NegotiationState(str(doc["state"])),
        body=str(doc["body"]),
        approved_by=raw_approved_by if isinstance(raw_approved_by, str) else None,
        created_at=datetime.fromisoformat(str(doc["created_at"])),
        updated_at=datetime.fromisoformat(str(doc["updated_at"])),
    )


class NegotiationStore:
    """Firestore-backed drafts at deals/{deal_id}/negotiations/{draft_id}."""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def _collection(self, deal_id: str) -> firestore.CollectionReference:
        return cast(
            firestore.CollectionReference,
            self._client.collection("deals").document(deal_id).collection(_COLLECTION),
        )

    def create(self, draft: NegotiationDraft) -> None:
        self._collection(draft.deal_id).document(draft.draft_id).set(_draft_to_doc(draft))

    def update(self, draft: NegotiationDraft) -> None:
        ref = self._collection(draft.deal_id).document(draft.draft_id)
        if not ref.get().exists:
            raise DraftNotFound(draft.draft_id)
        ref.set(_draft_to_doc(draft))

    def get(self, deal_id: str, draft_id: str) -> NegotiationDraft:
        snapshot = self._collection(deal_id).document(draft_id).get()
        data = snapshot.to_dict()
        if data is None:
            raise DraftNotFound(draft_id)
        return _draft_from_doc(data)

    def list_for_finding(self, deal_id: str, finding_id: str) -> list[NegotiationDraft]:
        docs = (
            self._collection(deal_id)
            .where(filter=FieldFilter("finding_id", "==", finding_id))
            .stream()
        )
        drafts: list[NegotiationDraft] = []
        for doc in docs:
            data = doc.to_dict()
            if data is None:
                continue
            drafts.append(_draft_from_doc(data))
        return drafts
