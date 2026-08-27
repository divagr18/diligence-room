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
    env_vars: Sequence[str] = (),
) -> list[str]:
    """Return the ``gcloud run deploy`` argument list.

    Pins the remote Python runtime (GOOGLE_PYTHON_VERSION) because the repo's
    ``.python-version`` targets local development tooling and is excluded from
    the source upload (see .gcloudignore). ``env_vars`` are runtime KEY=VALUE
    pairs (one ``--set-env-vars`` per entry).
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
    for env_var in env_vars:
        args.append(f"--set-env-vars={env_var}")
    if allow_unauthenticated:
        args.append("--allow-unauthenticated")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Parse *argv* and either refuse or submit a Cloud Run deploy."""
    parser = argparse.ArgumentParser(description="Deploy Agent Gateway to Cloud Run.")
    parser.add_argument("--project", default="diligence-room")
    parser.add_argument("--service", default="gateway")
    parser.add_argument("--region", default="us-central1")
    # Repo root: the buildpack entrypoint is the root main.py (main:app) and
    # the root .gcloudignore bounds the upload.
    parser.add_argument("--source", default=".")
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
        # Wires the Firestore-backed policy edge (POST /gateway/decide) onto
        # the named live database (the (default) record is a post-undelete
        # zombie; see memory/db.py).
        env_vars=("DILIGENCE_GATEWAY_LIVE=1", "DILIGENCE_FIRESTORE_DATABASE=diligence"),
    )
    run_gcloud(deploy_args)
    print(f"Deploy submitted: gcloud {' '.join(deploy_args)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
