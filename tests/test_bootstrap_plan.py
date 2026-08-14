"""Tests for the pure planning helpers in infra/bootstrap_gcp.py.

Day-1 module M1 (GCP bootstrap). Only the deterministic, side-effect-free
logic lives here; the gcloud side effects are exercised end-to-end in the
manual gate (see README runbook).
"""

from __future__ import annotations

import pytest

from infra.bootstrap_gcp import (
    build_budget_args,
    plan_service_enables,
)

BILLING_ACCOUNT = "012D4F-261885-E006CE"


class TestPlanServiceEnables:
    """plan_service_enables: diff target APIs against currently enabled ones."""

    def test_returns_missing_services_in_target_order(self) -> None:
        enabled = {"aiplatform.googleapis.com", "pubsub.googleapis.com"}
        target = [
            "aiplatform.googleapis.com",
            "firestore.googleapis.com",
            "pubsub.googleapis.com",
            "run.googleapis.com",
        ]
        assert plan_service_enables(enabled, target) == [
            "firestore.googleapis.com",
            "run.googleapis.com",
        ]

    def test_all_enabled_returns_empty(self) -> None:
        target = ["a.googleapis.com", "b.googleapis.com"]
        assert plan_service_enables(set(target), target) == []

    def test_extra_enabled_services_are_ignored(self) -> None:
        enabled = {"unrelated.googleapis.com"}
        assert plan_service_enables(enabled, ["x.googleapis.com"]) == ["x.googleapis.com"]


class TestBuildBudgetArgs:
    """build_budget_args: gcloud billing budgets create argument list."""

    def test_builds_expected_gcloud_args(self) -> None:
        args = build_budget_args(
            billing_account=BILLING_ACCOUNT,
            display_name="diligence-room-hard-cap",
            amount_units=15980,
            thresholds=(0.5, 0.8, 1.0),
        )
        assert args[:3] == ["billing", "budgets", "create"]
        assert "--billing-account=012D4F-261885-E006CE" in args
        assert "--display-name=diligence-room-hard-cap" in args
        assert "--budget-amount=15980" in args
        assert "--threshold-rule=percent=0.5" in args
        assert "--threshold-rule=percent=0.8" in args
        assert "--threshold-rule=percent=1.0" in args
        # exactly one threshold rule per threshold
        assert sum(1 for a in args if a.startswith("--threshold-rule=")) == 3

    def test_rejects_zero_threshold(self) -> None:
        with pytest.raises(ValueError, match="threshold"):
            build_budget_args(
                billing_account=BILLING_ACCOUNT,
                display_name="x",
                amount_units=15980,
                thresholds=(0.0, 0.5),
            )

    def test_rejects_threshold_above_one(self) -> None:
        with pytest.raises(ValueError, match="threshold"):
            build_budget_args(
                billing_account=BILLING_ACCOUNT,
                display_name="x",
                amount_units=15980,
                thresholds=(1.5,),
            )

    def test_rejects_non_positive_amount(self) -> None:
        with pytest.raises(ValueError, match="amount"):
            build_budget_args(
                billing_account=BILLING_ACCOUNT,
                display_name="x",
                amount_units=0,
                thresholds=(0.5,),
            )
