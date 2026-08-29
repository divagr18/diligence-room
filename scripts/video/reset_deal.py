"""Delete a deal's Firestore state so a beat-3 take can start from zero.

Recording beat 3 means showing the findings count climb 0 -> 5, so every retake
needs the deal namespace emptied first. Deletes the deal document and its
subcollections (findings, events, and anything else nested under it).

The agent registry is global (top-level ``agents`` collection), not nested
under the deal, so a replay that publishes Legal v2.5.0 leaves that version
behind and the next run dies with DuplicateAgentError. ``--with-registry``
clears the registry too; re-seed it afterwards with ``registry/seed.py``.

Usage:
    uv run python scripts/video/reset_deal.py --deal-id deal-falcon --confirm
    uv run python scripts/video/reset_deal.py --deal-id deal-falcon --with-registry --confirm
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from google.cloud import firestore

from memory.db import make_client


def delete_deal(client: firestore.Client, deal_id: str, *, batch_size: int = 200) -> dict[str, int]:
    """Delete every document under ``deals/{deal_id}`` and the deal itself."""
    deleted: dict[str, int] = {}
    deal_ref = client.collection("deals").document(deal_id)
    for sub in deal_ref.collections():
        count = 0
        while True:
            docs = list(sub.limit(batch_size).stream())
            if not docs:
                break
            batch = client.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()
            count += len(docs)
        deleted[sub.id] = count
    if deal_ref.get().exists:
        deal_ref.delete()
        deleted["_deal_document"] = 1
    return deleted


def delete_registry(client: firestore.Client, *, batch_size: int = 200) -> int:
    """Delete every agent manifest and its nested versions subcollection."""
    deleted = 0
    for agent in list(client.collection("agents").stream()):
        for sub in agent.reference.collections():
            while True:
                docs = list(sub.limit(batch_size).stream())
                if not docs:
                    break
                batch = client.batch()
                for doc in docs:
                    batch.delete(doc.reference)
                batch.commit()
                deleted += len(docs)
        agent.reference.delete()
        deleted += 1
    return deleted


def delete_drafts(client: firestore.Client, deal_id: str, *, batch_size: int = 200) -> int:
    """Drop the deal's negotiation drafts.

    Draft creation is idempotent per finding and kind, so a second beat-7 take
    gets back the draft the first take already approved, and the approve step
    fails with "cannot move from approved to approved".
    """
    col = client.collection("deals").document(deal_id).collection("negotiations")
    deleted = 0
    while True:
        docs = list(col.limit(batch_size).stream())
        if not docs:
            break
        batch = client.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        deleted += len(docs)
    return deleted


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset a deal namespace for a fresh take.")
    # Optional: --with-registry alone resets just the global registry, which is
    # what beat 6 needs (it re-publishes v2.5.0 and must not find it already there),
    # without disturbing the deal findings the dashboard is showing.
    parser.add_argument("--deal-id", default=None)
    parser.add_argument("--with-registry", action="store_true")
    parser.add_argument("--drafts-only", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)

    if not args.confirm:
        sys.exit("Refused: pass --confirm to delete this deal's Firestore state.")
    if args.deal_id is None and not args.with_registry:
        sys.exit("Refused: pass --deal-id, or --with-registry to reset only the registry.")

    client = make_client()
    if args.drafts_only:
        if args.deal_id is None:
            sys.exit("Refused: --drafts-only needs --deal-id.")
        dropped = delete_drafts(client, args.deal_id)
        print(f"[reset] {args.deal_id}: deleted {dropped} negotiation draft(s)")
        return 0
    if args.deal_id is None:
        print(f"[reset] registry: deleted {delete_registry(client)} documents")
        return 0
    deleted = delete_deal(client, args.deal_id)
    if not deleted:
        print(f"[reset] {args.deal_id}: nothing to delete")
        if args.with_registry:
            print(f"[reset] registry: deleted {delete_registry(client)} documents")
        return 0
    for name, count in sorted(deleted.items()):
        print(f"[reset] {args.deal_id}: deleted {count} from {name}")
    if args.with_registry:
        print(f"[reset] registry: deleted {delete_registry(client)} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
