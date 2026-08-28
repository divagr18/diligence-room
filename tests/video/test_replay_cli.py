"""Pins the replay CLI shim used by video beat 3 (unedited execution take).

The shim must refuse to run against live Firestore (video beats are
emulator-backed by design), and its report lines must carry the locked
replay invariants: 49 events, 5 findings, run_id derived from seed 42.
"""

from __future__ import annotations

import pytest

from runtime.replay import ReplayReport, derive_run_id


def test_derive_run_id_pinned_for_seed_42() -> None:
    assert derive_run_id(42) == "replay-bdd640fb0667"


def test_build_config_defaults() -> None:
    from scripts.video.replay_cli import build_config

    cfg = build_config(speed=34000.0, seed=42, deal_id="deal-falcon")
    assert cfg.speed == 34000.0
    assert cfg.seed == 42
    assert cfg.deal_id == "deal-falcon"
    assert cfg.scenario_path.name == "project_falcon.json"


def test_format_report_lines() -> None:
    from scripts.video.replay_cli import format_report

    report = ReplayReport(
        run_id="replay-bdd640fb0667",
        events_injected=49,
        findings_created=5,
        duration_s=1.48,
        deterministic=True,
    )
    out = format_report(report)
    assert "run_id=replay-bdd640fb0667" in out
    assert "events_injected=49" in out
    assert "findings_created=5" in out
    assert "duration_s=1.48" in out
    assert "deterministic=True" in out


def test_refuses_without_emulator(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.video.replay_cli import main

    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    with pytest.raises(SystemExit):
        main(["--speed", "1000"])


def test_main_full_scenario_against_emulator(
    firestore_emulator: str,
    unique_project: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.video.replay_cli import main

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", unique_project)
    rc = main(["--speed", "1000000", "--seed", "42", "--deal-id", "deal-falcon"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "run_id=replay-bdd640fb0667" in out
    assert "events_injected=49" in out
    assert "findings_created=5" in out
    assert "deterministic=True" in out
