"""Dashboard Cloud Run deploy planner tests (BUILD_PLAN D11-M1)."""

from __future__ import annotations

import pytest

from infra.deploy.dashboard import build_dashboard_deploy_args, main


class TestPlanner:
    def test_build_args_contain_required_flags(self) -> None:
        args = build_dashboard_deploy_args(
            project="diligence-room",
            service="diligence-room-dashboard",
            source="dashboard/",
            region="us-central1",
            allow_unauthenticated=True,
        )
        assert "run" in args
        assert "diligence-room-dashboard" in args
        assert "--region" in args
        assert "us-central1" in args
        assert "--project" in args
        assert "diligence-room" in args
        assert "--allow-unauthenticated" in args

    def test_build_args_respect_region(self) -> None:
        args = build_dashboard_deploy_args(
            project="proj", service="svc", source="dashboard/", region="europe-west1"
        )
        assert "europe-west1" in args


class TestGate:
    def test_refuses_without_confirm_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
        with pytest.raises(SystemExit):
            main([])
