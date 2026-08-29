"""Beat 6 on camera: publish Legal v2.5, watch the eval fail it, roll it back.

Runs against whatever Firestore the environment points at (live, for the take).
Paced with sleeps so a viewer can read each step, and so the recorder can
refresh the Registry view while v2.5 is the serving version.

Usage:
    uv run python scripts/video/beat6_rollback.py
"""

from __future__ import annotations

import argparse
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from google.cloud import firestore

from agents.fleet import DEEP_WORKSTREAM_DOCUMENTS
from evals.harness import run_harness
from evals.legal_v25 import extractor_from_registry, publish_legal_v25
from memory.db import make_client
from memory.findings import FindingsStore
from registry.store import AgentRegistryStore

KNOWN_GOOD = "2.4.0"
PUBLISH_NOW = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)


def finding_counts(client: firestore.Client, deal_id: str) -> dict[str, int]:
    store = FindingsStore(client)
    return {
        ws.value: len(store.list_for_workstream(deal_id, ws)) for ws in DEEP_WORKSTREAM_DOCUMENTS
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upgrade, catch the regression, roll back.")
    parser.add_argument("--deal-id", default="deal-falcon")
    parser.add_argument("--pace", type=float, default=2.5)
    args = parser.parse_args(argv)

    pace = args.pace
    client = make_client()
    registry = AgentRegistryStore(client)
    # The harness writes findings into its own deal namespace; reuse the same
    # one across takes and the second run dies on duplicate_finding.
    run_tag = uuid.uuid4().hex[:6]

    current = registry.get_manifest("legal")
    print(f"[registry] legal is serving v{current.version}  approved={current.approved}")
    time.sleep(pace)

    print("\n[publish]  shipping legal v2.5.0 ...")
    published = publish_legal_v25(registry, now=PUBLISH_NOW)
    print(
        f"[publish]  legal now v{published.version}  approved={published.approved}  "
        f"rollback_target={published.rollback_target}"
    )
    time.sleep(pace * 2)

    print("\n[eval]     replaying the golden set against v2.5.0 ...")
    red = run_harness(
        client, f"{args.deal_id}-eval-red-{run_tag}", extractor_from_registry(registry)
    )
    missing = [doc.doc_id for doc in red.missing]
    print(f"[eval]     FAILED  passed={red.passed}  missing={missing}")
    time.sleep(pace)

    before = finding_counts(client, args.deal_id)
    print(f"\n[memory]   findings before rollback: {before}")
    time.sleep(pace)

    print("\n[rollback] rolling legal back to v2.4.0 ...")
    rolled = registry.rollback("legal", KNOWN_GOOD)
    print(
        f"[rollback] legal now v{rolled.version}  approved={rolled.approved}  "
        f"replaced={rolled.rollback_target}"
    )
    time.sleep(pace * 2)

    after = finding_counts(client, args.deal_id)
    print(f"[memory]   findings after rollback:  {after}")
    print(f"[memory]   unchanged = {after == before}")
    time.sleep(pace)

    green = run_harness(
        client, f"{args.deal_id}-eval-green-{run_tag}", extractor_from_registry(registry)
    )
    print(f"\n[eval]     re-run on v2.4.0: passed={green.passed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
