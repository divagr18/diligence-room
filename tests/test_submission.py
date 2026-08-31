"""Shape tests for the public submission document."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_ROOT: Final = Path(__file__).resolve().parent.parent
SUBMISSION_PATH: Final = _ROOT / "docs" / "submission.md"


def _submission_text() -> str:
    assert SUBMISSION_PATH.is_file(), "docs/submission.md must exist"
    return SUBMISSION_PATH.read_text(encoding="utf-8")


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_submission_has_project_story() -> None:
    body = _squash(_submission_text()).lower()
    for marker in (
        "project falcon",
        "vantage robotics",
        "zero-trust",
        "agent gateway",
        "human approval",
    ):
        assert marker in body


def test_submission_explains_verification_systems() -> None:
    body = _squash(_submission_text()).lower()
    for marker in (
        "shadow evaluations",
        "golden set",
        "red-team testing",
        "observability and auditability",
        "audit_trace_id",
        "failure and boundary testing",
    ):
        assert marker in body


def test_submission_keeps_public_project_links() -> None:
    text = _submission_text()
    assert "https://github.com/divagr18/diligence-room" in text
    assert "https://youtu.be/oCu2HfN85Ec" in text
    assert "https://gateway-378831539922.asia-south1.run.app/docs" in text
    assert "docs/diagram/architecture.png" in text


def test_hackathon_language_present() -> None:
    body = _squash(_submission_text()).lower()
    assert "created for" in body
    assert "allthingsagentic hackathon" in body
    assert "fortified enterprise fleet" in body


def test_no_placeholder_copy() -> None:
    body = _submission_text().lower()
    assert "lorem" not in body
    assert "video link" not in body
