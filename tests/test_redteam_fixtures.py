"""Red-team batch #1 fixture tests (BUILD_PLAN D6-M6, scenario S9).

Every hostile fixture must be committed, deterministic, and trip the sentinel
tripwire layer with the reason declared in redteam/expected.yaml. Offline this
is the regex sentinel (production adds the Gemma layer, Day 7).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from google.cloud import firestore

from ingestion.models import ClassHint, RouteDecision
from ingestion.parsing import LocalParser
from ingestion.pipeline import IngestContext, ingest_blob
from ingestion.sentinel import FakeSentinel
from runtime.events import EventType, InMemoryPublisher

REPO_ROOT = Path(__file__).resolve().parent.parent
ATTACKS_ROOT = REPO_ROOT / "redteam" / "attacks"
EXPECTED_YAML = REPO_ROOT / "redteam" / "expected.yaml"

DEAL = "deal-falcon"


class _CountingClassifier:
    """Counts classify calls so we can prove tripwired docs never reach routing."""

    def __init__(self) -> None:
        self.calls = 0

    def classify(self, document_id: str, text: str, hint: ClassHint | None) -> RouteDecision:
        self.calls += 1
        return RouteDecision(document_id, "other", None, 0.0, ("counting",))


def _expected_fixtures() -> list[dict[str, str]]:
    data = yaml.safe_load(EXPECTED_YAML.read_text(encoding="utf-8"))
    fixtures = data["fixtures"]
    assert isinstance(fixtures, list)
    return fixtures


def _attack_text(relative: str) -> str:
    path = ATTACKS_ROOT / relative
    assert path.is_file(), f"fixture {relative} not committed"
    parsed = LocalParser().parse(path.read_bytes(), path.name, DEAL)
    assert parsed.text is not None, f"fixture {relative} has no parseable text layer"
    return parsed.text


class TestRedteamBatch1:
    def test_expected_manifest_has_five_fixtures(self) -> None:
        fixtures = _expected_fixtures()
        assert len(fixtures) == 5
        classes = [fx["attack_class"] for fx in fixtures]
        assert classes.count("injection") == 3
        assert classes.count("exfiltration") == 2

    def test_all_fixtures_committed(self) -> None:
        for fx in _expected_fixtures():
            assert (ATTACKS_ROOT / fx["path"]).is_file(), fx["path"]

    def test_fixtures_regenerate_byte_identical(self, tmp_path: Path) -> None:
        from scripts.author_redteam import _ATTACKS, write_attack

        for relative, body in _ATTACKS:
            regenerated = tmp_path / Path(relative).name
            write_attack(regenerated, body)
            committed = ATTACKS_ROOT / relative
            assert regenerated.read_bytes() == committed.read_bytes(), relative

    @pytest.mark.parametrize(
        "relative",
        [
            "injection/direct_a.pdf",
            "injection/direct_b.pdf",
            "injection/obfuscated/a.pdf",
            "exfiltration/a.pdf",
            "exfiltration/b.pdf",
        ],
    )
    def test_every_fixture_trips_the_sentinel(self, relative: str) -> None:
        text = _attack_text(relative)
        verdict = FakeSentinel().injection_tripwire(text)
        assert verdict.tripped is True, f"{relative} did not trip the sentinel"

    def test_injection_fixtures_report_injection_pattern(self) -> None:
        for fx in _expected_fixtures():
            if fx["attack_class"] != "injection":
                continue
            verdict = FakeSentinel().injection_tripwire(_attack_text(fx["path"]))
            assert any("instruction" in pattern for pattern in verdict.patterns), fx["path"]

    def test_exfiltration_fixtures_report_exfiltration_pattern(self) -> None:
        for fx in _expected_fixtures():
            if fx["attack_class"] != "exfiltration":
                continue
            verdict = FakeSentinel().injection_tripwire(_attack_text(fx["path"]))
            assert any("exfiltration" in pattern for pattern in verdict.patterns), fx["path"]


class TestRedteamPipelineQuarantine:
    """The committed attack fixtures, driven through the FULL pipeline, must be
    quarantined before routing — never reaching the classifier or any agent."""

    def test_every_attack_fixture_quarantined_end_to_end(
        self, firestore_client: firestore.Client
    ) -> None:
        classifier = _CountingClassifier()
        context = IngestContext(
            client=firestore_client,
            publisher=InMemoryPublisher(),
            sentinel=FakeSentinel(),
            classifier=classifier,
        )
        for fx in _expected_fixtures():
            relative = fx["path"]
            blob = (ATTACKS_ROOT / relative).read_bytes()
            calls_before = classifier.calls
            result = ingest_blob(context, DEAL, relative.replace("/", "_"), blob)
            assert result.status == "tripwired", f"{relative} must be quarantined"
            assert result.route is None, f"{relative} must not be routed"
            assert classifier.calls == calls_before, f"{relative} reached the classifier"
            security = [event for event in result.events if event.type is EventType.SECURITY_EVENT]
            assert len(security) == 1, f"{relative} must emit exactly one security event"
            assert security[0].payload["reason"] == "injection_tripwire"
            assert security[0].payload["document_id"] == relative.replace("/", "_")
