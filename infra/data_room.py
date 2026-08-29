"""Diligence Room — data-room bucket provisioning (BUILD_PLAN module D2-M2).

Provisions per-deal regional Cloud Storage buckets (US + EU pair per
vision §7.8 region pinning) with Pub/Sub ``OBJECT_FINALIZE`` notifications
to the shared ``deal-events`` topic.

Pure planners are unit-testable with no subprocess calls. Idempotent
executors wrap :func:`infra.bootstrap_gcp.run_gcloud` with describe/list
checks before create.

Usage:
    # Dry-run: print the full gcloud command plan without executing.
    uv run python infra/data_room.py --deal-id deal-falcon --project-number 910285417505 --dry-run

    # Live: requires explicit --confirm-live write guard.
    uv run python infra/data_room.py --deal-id deal-falcon \\
        --project-number 910285417505 --confirm-live
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence

from infra.bootstrap_gcp import run_gcloud

PROJECT_ID: str = os.environ.get("DILIGENCE_PROJECT_ID", "diligence-room")
TOPIC: str = "deal-events"
SUBSCRIPTION: str = "deal-events-sub"
REGION_MAP: dict[str, str] = {"US": "us-central1", "EU": "europe-west1"}

_DEAL_ID_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9-]*$")


def _validate_deal_id(deal_id: str) -> None:
    if not deal_id or not _DEAL_ID_RE.match(deal_id):
        raise ValueError(f"deal_id must match ^[a-z][a-z0-9-]*$, got {deal_id!r}")


# --------------------------------------------------------------------------
# Pure planning helpers (unit-tested in tests/test_data_room_plan.py)
# --------------------------------------------------------------------------


def plan_bucket_pair(deal_id: str) -> tuple[str, str]:
    """Return the US and EU bucket names for a deal's data room.

    Raises ValueError if *deal_id* is not a valid lowercase identifier.
    """
    _validate_deal_id(deal_id)
    return (
        f"{PROJECT_ID}-dataroom-{deal_id}-us",
        f"{PROJECT_ID}-dataroom-{deal_id}-eu",
    )


def plan_notification_args(bucket: str, topic: str) -> list[str]:
    """Build the gcloud argv for a storage bucket OBJECT_FINALIZE notification."""
    return [
        "storage",
        "buckets",
        "notifications",
        "create",
        f"gs://{bucket}",
        "--event-types=OBJECT_FINALIZE",
        f"--topic=projects/{PROJECT_ID}/topics/{topic}",
    ]


def plan_subscription_args(topic: str, subscription: str) -> list[str]:
    """Build the gcloud argv for a Pub/Sub pull subscription."""
    return [
        "pubsub",
        "subscriptions",
        "create",
        subscription,
        f"--topic={topic}",
        f"--project={PROJECT_ID}",
    ]


def plan_data_room(deal_id: str, project_number: str) -> list[list[str]]:
    """Return the ordered gcloud command plan for a deal's data room.

    Order:
      1. Create the Pub/Sub topic.
      2. Create US bucket.
      3. Create EU bucket.
      4. IAM grant: roles/pubsub.publisher to the GCS service account on the topic.
      5. OBJECT_FINALIZE notification per bucket.
      6. Pull subscription on the topic.
    """
    us_bucket, eu_bucket = plan_bucket_pair(deal_id)
    steps: list[list[str]] = []

    # 1. Topic
    steps.append(
        [
            "pubsub",
            "topics",
            "create",
            TOPIC,
            f"--project={PROJECT_ID}",
        ]
    )

    # 2–3. US + EU buckets
    for suffix, region_key in (("-us", "US"), ("-eu", "EU")):
        bucket = f"{PROJECT_ID}-dataroom-{deal_id}{suffix}"
        steps.append(
            [
                "storage",
                "buckets",
                "create",
                f"gs://{bucket}",
                f"--project={PROJECT_ID}",
                f"--location={REGION_MAP[region_key]}",
                "--uniform-bucket-level-access",
            ]
        )

    # 4. IAM grant — allow GCS service agent to publish to the topic
    iam_member = (
        f"serviceAccount:service-{project_number}@gs-project-accounts.iam.gserviceaccount.com"
    )
    steps.append(
        [
            "pubsub",
            "topics",
            "add-iam-policy-binding",
            TOPIC,
            f"--member={iam_member}",
            "--role=roles/pubsub.publisher",
            f"--project={PROJECT_ID}",
        ]
    )

    # 5. Notifications (one per bucket)
    for bucket in (us_bucket, eu_bucket):
        steps.append(plan_notification_args(bucket, TOPIC))

    # 6. Pull subscription on the topic
    steps.append(plan_subscription_args(TOPIC, SUBSCRIPTION))

    return steps


# --------------------------------------------------------------------------
# Idempotent executors (code only — tests never invoke these)
# --------------------------------------------------------------------------


def ensure_topic(project: str) -> None:
    """Create the Pub/Sub topic if it does not already exist."""
    result = run_gcloud(
        ["pubsub", "topics", "describe", TOPIC, f"--project={project}"],
        check=False,
    )
    if result.returncode == 0:
        print(f"    topic {TOPIC} already exists - ok")
        return
    run_gcloud(["pubsub", "topics", "create", TOPIC, f"--project={project}"])
    print(f"    created topic {TOPIC}")


def ensure_bucket(bucket: str, location: str, project: str) -> None:
    """Create the storage bucket if it does not already exist."""
    result = run_gcloud(
        ["storage", "buckets", "describe", f"gs://{bucket}"],
        check=False,
    )
    if result.returncode == 0:
        print(f"    bucket gs://{bucket} already exists - ok")
        return
    run_gcloud(
        [
            "storage",
            "buckets",
            "create",
            f"gs://{bucket}",
            f"--project={project}",
            f"--location={location}",
            "--uniform-bucket-level-access",
        ]
    )
    print(f"    created bucket gs://{bucket} ({location})")


def ensure_notification(bucket: str, topic: str, project: str) -> None:
    """Create the OBJECT_FINALIZE notification if none exists on the bucket."""
    result = run_gcloud(
        [
            "storage",
            "buckets",
            "notifications",
            "list",
            f"gs://{bucket}",
            f"--project={project}",
        ]
    )
    if result.stdout.strip():
        print(f"    notification already present on gs://{bucket} - ok")
        return
    run_gcloud(plan_notification_args(bucket, topic) + [f"--project={project}"])
    print(f"    created notification on gs://{bucket} -> {topic}")


def ensure_subscription(topic: str, subscription: str, project: str) -> None:
    """Create the Pub/Sub pull subscription if it does not already exist."""
    result = run_gcloud(
        ["pubsub", "subscriptions", "describe", subscription, f"--project={project}"],
        check=False,
    )
    if result.returncode == 0:
        print(f"    subscription {subscription} already exists - ok")
        return
    run_gcloud(plan_subscription_args(topic, subscription))
    print(f"    created subscription {subscription} -> {topic}")


# --------------------------------------------------------------------------
# CLI entry point
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision per-deal data-room buckets with Pub/Sub notifications.",
    )
    parser.add_argument(
        "--deal-id",
        required=True,
        help="Lowercase deal identifier, e.g. deal-falcon.",
    )
    parser.add_argument(
        "--project-number",
        required=True,
        help="GCP project number (needed for the IAM grant step).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the full gcloud command plan and exit without executing.",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        default=False,
        help="Required together with the absence of --dry-run to execute live.",
    )

    args = parser.parse_args(argv)

    steps = plan_data_room(args.deal_id, args.project_number)

    if args.dry_run:
        for step_argv in steps:
            print(" ".join(step_argv))
        sys.exit(0)

    if not args.confirm_live:
        sys.exit(
            "Refusing to execute live gcloud commands without --confirm-live "
            "(pass --dry-run to preview, or add --confirm-live to run for real)."
        )

    # Live execution path — never reached in tests.
    print(f"==> Provisioning data room for {args.deal_id}")
    ensure_topic(PROJECT_ID)
    us_bucket, eu_bucket = plan_bucket_pair(args.deal_id)
    ensure_bucket(us_bucket, REGION_MAP["US"], PROJECT_ID)
    ensure_bucket(eu_bucket, REGION_MAP["EU"], PROJECT_ID)

    # IAM grant
    iam_member = (
        f"serviceAccount:service-{args.project_number}@gs-project-accounts.iam.gserviceaccount.com"
    )
    result = run_gcloud(
        [
            "pubsub",
            "topics",
            "get-iam-policy",
            TOPIC,
            f"--project={PROJECT_ID}",
            "--format=json",
        ]
    )
    if iam_member in result.stdout:
        print(f"    IAM grant for {iam_member} already present - ok")
    else:
        run_gcloud(
            [
                "pubsub",
                "topics",
                "add-iam-policy-binding",
                TOPIC,
                f"--member={iam_member}",
                "--role=roles/pubsub.publisher",
                f"--project={PROJECT_ID}",
            ]
        )
        print(f"    granted roles/pubsub.publisher to {iam_member}")

    ensure_notification(us_bucket, TOPIC, PROJECT_ID)
    ensure_notification(eu_bucket, TOPIC, PROJECT_ID)
    ensure_subscription(TOPIC, SUBSCRIPTION, PROJECT_ID)

    print(f"\nData room ready for {args.deal_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
