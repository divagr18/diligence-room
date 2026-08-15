"""Cloud Run deploy planner (BUILD_PLAN D2-M7).

Pure argument builder + **write-only gate**: refuses to touch gcloud
unless ``--confirm-live`` is passed on the command line.  Tests exercise
the planning surface only — the live path is never taken in CI.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from infra.bootstrap_gcp import run_gcloud


def build_deploy_args(
    project: str,
    service: str,
    source: str,
    region: str,
    allow_unauthenticated: bool,
) -> list[str]:
    """Return the ``gcloud run deploy`` argument list.

    Pins the remote Python runtime (GOOGLE_PYTHON_VERSION) because the repo's
    ``.python-version`` targets local development tooling and is excluded from
    the source upload (see .gcloudignore).
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
        "--set-build-env-vars=GOOGLE_PYTHON_VERSION=3.13",
    ]
    if allow_unauthenticated:
        args.append("--allow-unauthenticated")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Parse *argv* and either refuse or submit a Cloud Run deploy."""
    parser = argparse.ArgumentParser(description="Deploy Agent Gateway to Cloud Run.")
    parser.add_argument("--project", default="diligence-room")
    parser.add_argument("--service", default="gateway")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--source", default="gateway/")
    parser.add_argument("--allow-unauthenticated", action="store_true")
    parser.add_argument("--confirm-live", action="store_true")
    args = parser.parse_args(argv)

    if not args.confirm_live:
        print("WRITE-ONLY: this script refuses to deploy without --confirm-live.")
        sys.exit("Refused: pass --confirm-live to acknowledge a live deploy.")

    deploy_args = build_deploy_args(
        project=args.project,
        service=args.service,
        source=args.source,
        region=args.region,
        allow_unauthenticated=args.allow_unauthenticated,
    )
    run_gcloud(deploy_args)
    print(f"Deploy submitted: gcloud {' '.join(deploy_args)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
