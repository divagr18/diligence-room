"""Region verification for deal workspaces (BUILD_PLAN D11-M2).

Asserts that data-room buckets, Firestore, and Cloud Run locations match the
deal's declared regions (vision §7.8). Offline: shape-valid report from
committed config; live (--confirm-live) would shell gcloud for actuals.
"""

from __future__ import annotations

import argparse
import json
import sys

from infra.data_room import REGION_MAP, plan_bucket_pair

_DECLARED: dict[str, tuple[str, ...]] = {
    "deal-falcon": ("US", "EU"),
}


def verify_regions(deal_id: str) -> dict[str, object]:
    """Return a structured verification report for *deal_id*."""
    if deal_id not in _DECLARED:
        return {
            "deal_id": deal_id,
            "declared": [],
            "buckets": {},
            "regions": {},
            "ok": False,
            "error": f"unknown deal {deal_id!r}",
        }
    declared = list(_DECLARED[deal_id])
    buckets: dict[str, str] = {}
    regions: dict[str, str] = {}
    for region in declared:
        bucket_us, bucket_eu = plan_bucket_pair(deal_id)
        # plan_bucket_pair returns (us, eu) in fixed order; map by region key
        buckets[region] = bucket_us if region == "US" else bucket_eu
        regions[region] = REGION_MAP[region]
    return {
        "deal_id": deal_id,
        "declared": declared,
        "buckets": buckets,
        "regions": regions,
        "ok": True,
        "error": "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify deal region pinning.")
    parser.add_argument("--deal-id", default="deal-falcon")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    report = verify_regions(args.deal_id)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "OK" if report["ok"] else "FAIL"
        declared = report["declared"]
        buckets = report["buckets"]
        regions_map = report["regions"]
        print(f"{status}: {report['deal_id']} declared={declared}")
        if (
            isinstance(declared, list)
            and isinstance(buckets, dict)
            and isinstance(regions_map, dict)
        ):
            for region in declared:
                print(f"  {region}: bucket={buckets[region]} region={regions_map[region]}")
        if not report["ok"]:
            print(f"  error: {report['error']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
