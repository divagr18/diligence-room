"""Publish a deal's existing findings into Memory Bank.

The coordinator writes a memory when it synthesises the CRITICAL finding, so a
fresh replay populates Memory Bank on its own. This script covers the other
case: a deal whose findings already exist, where re-running the replay just to
seed memory would be silly.

Write-only guard, matching registry/seed.py and infra/data_room.py: it refuses
to touch anything without --confirm-live.

Usage:
    uv run python scripts/backfill_memories.py --deal-id deal-falcon --confirm-live
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from memory.db import make_client
from memory.findings import FindingsStore
from memory.memory_bank import EntityMemory, memory_bank_from_env
from registry.models import Workstream


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Memory Bank from existing findings.")
    parser.add_argument("--deal-id", default="deal-falcon")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        default=False,
        help="Required to write to live Memory Bank (write-only guard).",
    )
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("WRITE-ONLY: this script refuses to write to Memory Bank without --confirm-live.")
        sys.exit("Refused: pass --confirm-live to acknowledge a live memory write.")

    bank = memory_bank_from_env()
    if bank is None:
        sys.exit(
            "Refused: Memory Bank is disabled. Set DILIGENCE_MEMORY_BANK_ENABLED=1 "
            "and GOOGLE_CLOUD_PROJECT."
        )

    store = FindingsStore(make_client(args.project or None))
    written = 0
    for workstream in Workstream:
        for finding in store.list_for_workstream(args.deal_id, workstream):
            for entity in finding.affected_entities:
                bank.remember_entity(
                    EntityMemory(
                        deal_id=args.deal_id,
                        entity=entity,
                        summary=finding.summary,
                        finding_id=finding.finding_id,
                    )
                )
                written += 1
                print(f"    remembered {entity} <- {finding.finding_id} ({workstream.value})")

    if written == 0:
        print(f"No findings with entities for {args.deal_id}; nothing written.")
        return 0
    print(f"\nMemory Bank holds {written} entity memories for {args.deal_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
