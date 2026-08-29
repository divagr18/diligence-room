"""Read the deal's entity memories back out of Memory Bank, for the camera.

Deliberately imports nothing from Firestore: the point the segment makes is that
these facts survive in Memory Bank across sessions, so the retrieval has to be
provably independent of the findings store.

Run under ``-W ignore``; the ADK emits a ``vertexai.Client is deprecated``
FutureWarning that would otherwise sit on screen mid-take.

Usage:
    uv run python -W ignore scripts/video/recall_demo.py
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from memory.memory_bank import memory_bank_from_env


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recall entity memories from Memory Bank.")
    parser.add_argument("--deal-id", default="deal-falcon")
    parser.add_argument("--query", default="Meridian")
    parser.add_argument("--width", type=int, default=76)
    args = parser.parse_args(argv)

    bank = memory_bank_from_env()
    if bank is None:
        sys.exit(
            "Memory Bank is disabled. Set DILIGENCE_MEMORY_BANK_ENABLED=1 and GOOGLE_CLOUD_PROJECT."
        )

    print(f'Memory Bank: recall("{args.query}") for {args.deal_id}')
    print("  (a fresh process - Firestore is not imported here)")
    print()

    hits = bank.recall(args.deal_id, args.query)
    if not hits:
        print("  no memories yet - run scripts/backfill_memories.py --confirm-live")
        return 0

    for hit in hits:
        text = hit if len(hit) <= args.width else f"{hit[: args.width - 1]}..."
        print(f"  - {text}")
    print()
    print(f"  {len(hits)} memories, carried across sessions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
