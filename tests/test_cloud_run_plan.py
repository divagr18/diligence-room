"""Tests for the Cloud Run deploy planning script (BUILD_PLAN D2-M7).

Pure planning tests: argv shape, refusal gate. No gcloud execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infra.deploy.cloud_run import build_deploy_args, main

if TYPE_CHECKING:
    pass


def test_build_deploy_args_includes_service_source_region_project() -> None:
    args = build_deploy_args(
        project="my-project",
        service="gateway",
        source="gateway/",
        region="us-central1",
        allow_unauthenticated=False,
    )
    assert args == [
        "run",
        "deploy",
        "gateway",
        "--source",
        "gateway/",
        "--region",
        "us-central1",
        "--project",
        "my-project",
        "--set-build-env-vars=GOOGLE_PYTHON_VERSION=3.13",
    ]


def test_build_deploy_args_pins_remote_python_version() -> None:
    args = build_deploy_args(
        project="my-project",
        service="gateway",
        source=".",
        region="us-central1",
        allow_unauthenticated=False,
    )
    assert "--set-build-env-vars=GOOGLE_PYTHON_VERSION=3.13" in args


def test_build_deploy_args_allow_unauthenticated_present() -> None:
    args = build_deploy_args(
        project="my-project",
        service="gateway",
        source="gateway/",
        region="us-central1",
        allow_unauthenticated=True,
    )
    assert "--allow-unauthenticated" in args


def test_build_deploy_args_allow_unauthenticated_absent_by_default() -> None:
    args = build_deploy_args(
        project="my-project",
        service="gateway",
        source="gateway/",
        region="us-central1",
        allow_unauthenticated=False,
    )
    assert "--allow-unauthenticated" not in args


def test_main_refuses_without_confirm_live(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="confirm"):
        main([])
    captured = capsys.readouterr()
    assert "WRITE-ONLY" in captured.out
