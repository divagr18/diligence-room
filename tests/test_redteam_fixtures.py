"""Red-team fixture tests (BUILD_PLAN D6-M6 batch #1, D7-M5 batch #2; scenario S9).

Ten committed, deterministic attack fixtures across two screening layers. Batch
#1 (injection x3, exfiltration x2) trips the sentinel tripwire BEFORE
classification. Batch #2 (authority forgery, cross-workstream state mutation
and privilege escalation, tool poisoning, cross-deal probe) deliberately evades
the sentinel and is caught by the Model Armor project-rules layer AFTER
classification. Every fixture must be quarantined before routing; the ledger in
redteam/expected.yaml declares the layer and reason for each.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from google.cloud import firestore

from armor.quarantine import QuarantineStore
from armor.rules import screen_project_rules
from ingestion.models import ClassHint, RouteDecision
from ingestion.parsing import LocalParser
from ingestion.pipeline import (
    STATUS_QUARANTINED,
    STATUS_TRIPWIRED,
    IngestContext,
    ingest_blob,
)
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


class TestRedteamLedger:
    def test_ledger_has_ten_fixtures_across_four_plus_classes(self) -> None:
        fixtures = _expected_fixtures()
        assert len(fixtures) == 10
        classes = [fx["attack_class"] for fx in fixtures]
        assert classes.count("injection") == 4
        assert classes.count("exfiltration") == 2
        assert classes.count("cross_ws") == 2
        assert classes.count("poisoning") == 1
        assert classes.count("cross_deal") == 1

    def test_every_entry_declares_a_layer(self) -> None:
        layers = {fx["layer"] for fx in _expected_fixtures()}
        assert layers == {"sentinel_tripwire", "model_armor"}

    def test_all_fixtures_committed(self) -> None:
        for fx in _expected_fixtures():
            assert (ATTACKS_ROOT / fx["path"]).is_file(), fx["path"]

    def test_fixtures_regenerate_byte_identical(self, tmp_path: Path) -> None:
        from scripts.author_redteam import _ATTACKS, write_attack

        assert len(_ATTACKS) == 10
        for relative, body in _ATTACKS:
            regenerated = tmp_path / Path(relative).name
            write_attack(regenerated, body)
            committed = ATTACKS_ROOT / relative
            assert regenerated.read_bytes() == committed.read_bytes(), relative


def _by_layer(layer: str) -> list[dict[str, str]]:
    return [fx for fx in _expected_fixtures() if fx["layer"] == layer]


class TestSentinelLayer:
    """Batch #1: caught by the sentinel tripwire before classification."""

    def test_batch_1_fixtures_trip_the_sentinel(self) -> None:
        fixtures = _by_layer("sentinel_tripwire")
        assert len(fixtures) == 5
        for fx in fixtures:
            verdict = FakeSentinel().injection_tripwire(_attack_text(fx["path"]))
            assert verdict.tripped is True, f"{fx['path']} did not trip the sentinel"

    def test_batch_1_injection_reports_instruction_pattern(self) -> None:
        for fx in _by_layer("sentinel_tripwire"):
            if fx["attack_class"] != "injection":
                continue
            verdict = FakeSentinel().injection_tripwire(_attack_text(fx["path"]))
            assert any("instruction" in pattern for pattern in verdict.patterns), fx["path"]

    def test_batch_1_exfiltration_reports_exfiltration_pattern(self) -> None:
        for fx in _by_layer("sentinel_tripwire"):
            if fx["attack_class"] != "exfiltration":
                continue
            verdict = FakeSentinel().injection_tripwire(_attack_text(fx["path"]))
            assert any("exfiltration" in pattern for pattern in verdict.patterns), fx["path"]


class TestArmorLayer:
    """Batch #2: evades the sentinel, caught by the armor project-rules layer."""

    def test_batch_2_fixtures_evade_the_sentinel(self) -> None:
        fixtures = _by_layer("model_armor")
        assert len(fixtures) == 5
        for fx in fixtures:
            verdict = FakeSentinel().injection_tripwire(_attack_text(fx["path"]))
            assert verdict.tripped is False, f"{fx['path']} must evade the sentinel"

    def test_batch_2_fixtures_caught_by_project_rules(self) -> None:
        for fx in _by_layer("model_armor"):
            hits = screen_project_rules(_attack_text(fx["path"]))
            assert hits, f"{fx['path']} was not caught by the project rules"
            reason_codes = {hit.reason_code for hit in hits}
            assert fx["reason"] in reason_codes, f"{fx['path']} reason mismatch: {reason_codes}"


class TestRedteamPipelineQuarantine:
    """Every committed attack fixture, driven through the FULL pipeline, must be
    quarantined before routing — never reaching an agent. Batch #1 stops at the
    sentinel (pre-classify); batch #2 stops at the armor screen (post-classify)."""

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
        store = QuarantineStore(firestore_client)
        for fx in _expected_fixtures():
            relative = fx["path"]
            quarantine_id = relative.replace("/", "_")
            blob = (ATTACKS_ROOT / relative).read_bytes()
            calls_before = classifier.calls
            result = ingest_blob(context, DEAL, quarantine_id, blob)
            assert result.route is None, f"{relative} must not be routed"
            security = [event for event in result.events if event.type is EventType.SECURITY_EVENT]
            assert len(security) == 1, f"{relative} must emit exactly one security event"
            assert security[0].payload["document_id"] == quarantine_id
            assert store.is_quarantined(DEAL, quarantine_id), f"{relative} has no quarantine record"
            if fx["layer"] == "sentinel_tripwire":
                assert result.status == STATUS_TRIPWIRED, relative
                assert classifier.calls == calls_before, f"{relative} reached the classifier"
                assert security[0].payload["reason"] == "injection_tripwire"
                patterns = security[0].payload["patterns"]
                assert isinstance(patterns, list)
                assert fx["reason"] in patterns
            else:
                assert result.status == STATUS_QUARANTINED, relative
                assert classifier.calls == calls_before + 1, f"{relative} skipped classification"
                assert security[0].payload["reason"] == "armor_quarantine"
                reason_codes = security[0].payload["reason_codes"]
                assert isinstance(reason_codes, list)
                assert fx["reason"] in reason_codes
