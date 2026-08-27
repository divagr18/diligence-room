"""Dashboard Cloud Run deploy planner (BUILD_PLAN D11-M1).

Pure argument builder + write-only gate: refuses to touch gcloud
unless --confirm-live is passed. Mirrors infra/deploy/cloud_run.py.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from infra.bootstrap_gcp import run_gcloud


def build_dashboard_deploy_args(
    project: str,
    service: str,
    source: str,
    region: str,
    allow_unauthenticated: bool = True,
    env_vars: Sequence[str] = (),
) -> list[str]:
    """Return the gcloud run deploy argument list for the dashboard.

    The buildpack entrypoint is ``dashboard.main:app`` (GOOGLE_ENTRYPOINT)
    because the repo-root main.py belongs to the gateway service.
    """
    args: list[str] = [
        "run",
        "deploy",
        service,
        "--source",
        source,
        "--region",
        region,
        "--project",
        project,
        # Separate flags: gcloud merges comma-joined pairs into one variable.
        # GOOGLE_ENTRYPOINT runs through bash, so it is a full command, not a
        # module spec ($PORT expands at container start).
        "--set-build-env-vars=GOOGLE_PYTHON_VERSION=3.13",
        "--set-build-env-vars=GOOGLE_ENTRYPOINT=python -m uvicorn dashboard.main:app"
        " --host 0.0.0.0 --port $PORT",
    ]
    for env_var in env_vars:
        args.append(f"--set-env-vars={env_var}")
    if allow_unauthenticated:
        args.append("--allow-unauthenticated")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Parse argv and either refuse or submit the dashboard deploy."""
    parser = argparse.ArgumentParser(description="Deploy dashboard to Cloud Run.")
    parser.add_argument("--project", default="diligence-room")
    parser.add_argument("--service", default="diligence-room-dashboard")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--source", default=".")
    parser.add_argument("--allow-unauthenticated", action="store_true", default=True)
    parser.add_argument(
        "--no-allow-unauthenticated", dest="allow_unauthenticated", action="store_false"
    )
    parser.add_argument("--confirm-live", action="store_true")
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("WRITE-ONLY: this script refuses to deploy without --confirm-live.")
        sys.exit("Refused: pass --confirm-live to acknowledge a live deploy.")

    deploy_args = build_dashboard_deploy_args(
        project=args.project,
        service=args.service,
        source=args.source,
        region=args.region,
        allow_unauthenticated=args.allow_unauthenticated,
        # Live Firestore (negotiation + security tallies) onto the named live
        # database (the (default) record is a post-undelete zombie; see
        # memory/db.py).
        env_vars=("DILIGENCE_DASHBOARD_LIVE=1", "DILIGENCE_FIRESTORE_DATABASE=diligence"),
    )
    run_gcloud(deploy_args)
    print(f"Deploy submitted: gcloud {' '.join(deploy_args)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
