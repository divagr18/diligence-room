"""Day-4 live gate runner guard tests (BUILD_PLAN D4-M8 live window, S7)."""

from __future__ import annotations

import pytest

from scripts.run_d4_live_gate import main, required_env, validate_live_env


class TestLiveGateGuards:
    def test_refuses_without_confirm_live_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            main(["--deal-id", "deal-falcon"])
        captured = capsys.readouterr()
        assert "--confirm-live" in captured.err + captured.out

    def test_refuses_confirm_live_under_emulator(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:1")
        with pytest.raises(SystemExit):
            main(["--deal-id", "deal-falcon", "--confirm-live"])
        captured = capsys.readouterr()
        assert "emulator" in (captured.err + captured.out).lower()

    def test_validate_reports_missing_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in required_env():
            monkeypatch.delenv(name, raising=False)
        assert set(required_env()) <= set(validate_live_env())

    def test_validate_passes_when_all_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in required_env():
            monkeypatch.setenv(name, "set")
        assert validate_live_env() == ()

    def test_offline_sentinel_mode_drops_key_requirements(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = required_env(offline_sentinel=True)
        assert "GOOGLE_API_KEY" not in names
        assert "DILIGENCE_GEMMA_ENABLED" not in names
        assert "DILIGENCE_FLASH_CLASSIFIER_ENABLED" in names
        for name in names:
            monkeypatch.setenv(name, "set")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("DILIGENCE_GEMMA_ENABLED", raising=False)
        assert validate_live_env(offline_sentinel=True) == ()
