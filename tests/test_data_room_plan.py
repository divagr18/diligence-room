"""Tests for the pure planning helpers in infra/data_room.py.

Day-2 module M2 (data-room bucket provisioning). Only deterministic,
side-effect-free planning logic is tested here; the imperative executors
(ensure_topic, ensure_bucket, ensure_notification) are code-only and
never invoked in tests.
"""

from __future__ import annotations

import pytest

from infra.data_room import (
    PROJECT_ID,
    REGION_MAP,
    TOPIC,
    main,
    plan_bucket_pair,
    plan_data_room,
    plan_notification_args,
)


class TestPlanBucketPair:
    """plan_bucket_pair: deterministic US+EU bucket names for a deal."""

    def test_returns_exact_names(self) -> None:
        us, eu = plan_bucket_pair("deal-falcon")
        assert us == "diligence-room-dataroom-deal-falcon-us"
        assert eu == "diligence-room-dataroom-deal-falcon-eu"

    def test_rejects_uppercase(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            plan_bucket_pair("UPPER")

    def test_rejects_space(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            plan_bucket_pair("has space")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            plan_bucket_pair("")


class TestPlanNotificationArgs:
    """plan_notification_args: gcloud storage buckets notifications create argv."""

    def test_contains_event_type_and_topic(self) -> None:
        args = plan_notification_args("my-bucket", "my-topic")
        assert "--event-types=OBJECT_FINALIZE" in args
        assert f"--topic=projects/{PROJECT_ID}/topics/my-topic" in args

    def test_starts_with_subcommand(self) -> None:
        args = plan_notification_args("my-bucket", "my-topic")
        assert args[:3] == ["storage", "buckets", "notifications", "create"][:3]

    def test_includes_bucket_gs_url(self) -> None:
        args = plan_notification_args("my-bucket", "my-topic")
        assert "gs://my-bucket" in args


class TestPlanDataRoom:
    """plan_data_room: ordered full plan for topic, buckets, IAM, notifications."""

    def test_topic_is_first(self) -> None:
        steps = plan_data_room("deal-falcon", "910285417505")
        # First step must be topic creation.
        assert steps[0] == [
            "pubsub",
            "topics",
            "create",
            TOPIC,
            f"--project={PROJECT_ID}",
        ]

    def test_both_buckets_before_notifications(self) -> None:
        steps = plan_data_room("deal-falcon", "910285417505")
        bucket_create_indices = [
            i
            for i, s in enumerate(steps)
            if len(s) >= 3 and s[:3] == ["storage", "buckets", "create"]
        ]
        notification_indices = [
            i
            for i, s in enumerate(steps)
            if len(s) >= 4 and s[:4] == ["storage", "buckets", "notifications", "create"]
        ]
        assert len(bucket_create_indices) == 2
        assert len(notification_indices) == 2
        assert max(bucket_create_indices) < min(notification_indices)

    def test_iam_grant_present_with_project_number(self) -> None:
        steps = plan_data_room("deal-falcon", "910285417505")
        iam_steps = [
            s
            for s in steps
            if any("gs-project-accounts.iam.gserviceaccount.com" in arg for arg in s)
        ]
        assert len(iam_steps) == 1
        iam_argv = iam_steps[0]
        assert "service-910285417505" in " ".join(iam_argv)

    def test_buckets_use_correct_locations(self) -> None:
        steps = plan_data_room("deal-falcon", "123")
        bucket_creates = [
            s for s in steps if len(s) >= 3 and s[:3] == ["storage", "buckets", "create"]
        ]
        locations = set()
        for argv in bucket_creates:
            for arg in argv:
                if arg.startswith("--location="):
                    locations.add(arg)
        assert f"--location={REGION_MAP['US']}" in locations
        assert f"--location={REGION_MAP['EU']}" in locations


class TestMainDryRun:
    """main --dry-run: prints the plan, exits 0, no subprocess."""

    def test_dry_run_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--deal-id", "deal-falcon", "--project-number", "1", "--dry-run"])
        assert exc_info.value.code == 0

    def test_dry_run_prints_bucket_creates(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            main(["--deal-id", "deal-falcon", "--project-number", "1", "--dry-run"])
        captured = capsys.readouterr().out
        assert "storage" in captured
        assert "buckets" in captured
        assert "create" in captured
        # Both US and EU buckets present.
        assert "us-central1" in captured
        assert "europe-west1" in captured

    def test_dry_run_prints_notifications(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            main(["--deal-id", "deal-falcon", "--project-number", "1", "--dry-run"])
        captured = capsys.readouterr().out
        assert captured.count("notifications") >= 2


class TestMainLiveGuard:
    """main without --dry-run refuses unless --confirm-live is passed."""

    def test_refuses_without_confirm(self) -> None:
        with pytest.raises(SystemExit, match="confirm"):
            main(["--deal-id", "deal-falcon", "--project-number", "1"])
