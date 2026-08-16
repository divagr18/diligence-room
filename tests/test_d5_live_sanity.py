"""Day-5 live sanity runner guards (small live window, Flash via Vertex ADC)."""

from __future__ import annotations

import pytest

from scripts.run_d5_live_sanity import main, required_env, validate_live_env


class TestLiveSanityGuards:
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
