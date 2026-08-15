"""Memory partition key helpers (BUILD_PLAN D3-M3, vision §7.3).

Translates the organization/deal/workstream namespace into Firestore paths.
Validation is strict: deal_id must match ^[a-z][a-z0-9-]*$ and workstream must
be a valid Workstream enum member or its string value.
"""

from __future__ import annotations

import re
from typing import cast

from google.cloud import firestore

from registry.models import Workstream

ORG = "diligence-room"

_DEAL_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _validate_deal_id(deal_id: str) -> None:
    if not _DEAL_ID_RE.match(deal_id):
        raise ValueError(f"invalid deal_id {deal_id!r}: must match ^[a-z][a-z0-9-]*$")


def _workstream_value(workstream: Workstream | str) -> str:
    if isinstance(workstream, Workstream):
        return workstream.value
    try:
        return Workstream(workstream).value
    except ValueError:
        raise ValueError(
            f"invalid workstream {workstream!r}: "
            f"expected one of {sorted(ws.value for ws in Workstream)}"
        ) from None


def partition_key(
    deal_id: str,
    workstream: Workstream | str,
    org: str = ORG,
) -> str:
    """Return the memory bank namespace key: {org}/{deal_id}/{workstream}."""
    _validate_deal_id(deal_id)
    return f"{org}/{deal_id}/{_workstream_value(workstream)}"


def get_partition(deal_id: str, workstream: Workstream | str) -> str:
    """Return the Firestore path: deals/{deal_id}/workstreams/{workstream}."""
    _validate_deal_id(deal_id)
    return f"deals/{deal_id}/workstreams/{_workstream_value(workstream)}"


def partition_collection(
    client: firestore.Client,
    deal_id: str,
    workstream: Workstream | str,
) -> firestore.CollectionReference:
    """Return a Firestore CollectionReference for workstream partition data.

    The workstream document path (``deals/{deal_id}/workstreams/{ws}``) is a
    4-segment document path; partition data lives in the ``items`` subcollection
    beneath it, yielding the 5-segment collection path
    ``deals/{deal_id}/workstreams/{ws}/items``.
    """
    return cast(
        firestore.CollectionReference,
        client.document(get_partition(deal_id, workstream)).collection("items"),
    )
