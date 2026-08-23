"""Shape tests for ``data/scenarios/project_falcon.json`` (BUILD_PLAN D13-M1).

The scenario file is the deterministic 14-day replay timeline mirroring
vision §16: corpus uploads first, the four keystone findings, the 20 attacks
in ``redteam/expected.yaml`` order, the TitanBridge amendment, the Legal
v2.5 upgrade + v2.4.0 rollback, and the negotiation draft/approve/send
lifecycle. These tests pin the JSON shape against committed artifacts only —
never synthetic generation:

- every ``doc_id`` resolves to a committed artifact (``evals.golden_set``
  resolution: ``data/vantage_robotics`` then ``data/scenarios``), and OCR
  flags mirror the golden ``needs_ocr`` pins;
- finding titles / severities / entities / locators are byte-exact
  ``evals/golden_set.py`` pins;
- attack rows are byte-exact ``redteam/expected.yaml`` rows whose fixture
  exists under ``redteam/attacks/``;
- timestamps are strictly monotonic ISO-8601 offsets from the pinned base
  clock, and ``day`` agrees with that clock.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final

import yaml

from agents.negotiation.store import NegotiationArtifactKind, NegotiationState
from evals.golden_set import GOLDEN_SET, golden_doc, golden_path
from ingestion.models import LineageStatus
from registry.seed import SEED_MANIFESTS

_ROOT: Final = Path(__file__).resolve().parent.parent
SCENARIO_PATH: Final = _ROOT / "data" / "scenarios" / "project_falcon.json"
ATTACKS_DIR: Final = _ROOT / "redteam" / "attacks"
EXPECTED_YAML: Final = _ROOT / "redteam" / "expected.yaml"

BASE_DATE: Final = date(2026, 7, 1)
ALLOWED_TYPES: Final = frozenset(
    {"upload", "finding", "attack", "amendment", "upgrade", "rollback", "negotiation"}
)
_TYPE_PHASE: Final[dict[str, int]] = {
    "upload": 0,
    "finding": 1,
    "attack": 2,
    "amendment": 3,
    "upgrade": 4,
    "rollback": 5,
    "negotiation": 6,
}
_KEYSTONE_ORDER: Final[tuple[str, ...]] = (
    "contract_meridian_logistics.pdf",
    "financials_fy27.xlsx",
    "hr_roster_vantage.xlsx",
    "tech_inventory.pdf",
)
_EXPECTED_COMPOSITION: Final[dict[str, int]] = {
    "upload": 19,
    "finding": 4,
    "attack": 20,
    "amendment": 1,
    "upgrade": 1,
    "rollback": 1,
    "negotiation": 3,
}


def _raw_text() -> str:
    return SCENARIO_PATH.read_text(encoding="utf-8")


def _envelope() -> dict[str, Any]:
    parsed = json.loads(_raw_text())
    assert isinstance(parsed, dict)
    return parsed


def _events() -> list[dict[str, Any]]:
    events = _envelope()["events"]
    assert isinstance(events, list)
    typed: list[dict[str, Any]] = []
    for event in events:
        assert isinstance(event, dict)
        typed.append(event)
    return typed


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event["payload"]
    assert isinstance(payload, dict)
    return payload


def _events_of_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event["type"] == event_type]


def _payload_str(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    assert isinstance(value, str)
    return value


def test_scenario_file_parses_with_pinned_envelope() -> None:
    envelope = _envelope()
    assert envelope["scenario_id"] == "project_falcon"
    assert envelope["deal_id"] == "deal-falcon"
    assert envelope["seed"] == 42
    assert envelope["base_ts"] == "2026-07-01T09:00:00Z"
    assert envelope["days"] == 14
    assert isinstance(envelope["events"], list)


def test_event_count_and_type_composition() -> None:
    events = _events()
    assert len(events) >= 30
    assert len(events) == sum(_EXPECTED_COMPOSITION.values())
    composition = Counter(str(event["type"]) for event in events)
    assert dict(composition) == _EXPECTED_COMPOSITION


def test_every_event_shape() -> None:
    for event in _events():
        assert set(event) == {"ts", "day", "type", "payload"}
        day = event["day"]
        assert isinstance(day, int) and not isinstance(day, bool)
        assert 1 <= day <= 14
        event_type = event["type"]
        assert isinstance(event_type, str) and event_type in ALLOWED_TYPES
        assert len(_payload(event)) > 0


def test_timestamps_are_iso8601_and_strictly_monotonic() -> None:
    previous: datetime | None = None
    for event in _events():
        raw_ts = event["ts"]
        assert isinstance(raw_ts, str)
        ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        assert ts.tzinfo is not None
        assert previous is None or ts > previous, f"non-monotonic ts at {raw_ts}"
        previous = ts


def test_day_agrees_with_base_clock() -> None:
    for event in _events():
        raw_ts = event["ts"]
        assert isinstance(raw_ts, str)
        ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        assert event["day"] == (ts.date() - BASE_DATE).days + 1


def test_vision_16_event_order_preserved() -> None:
    phases = [_TYPE_PHASE[str(event["type"])] for event in _events()]
    assert phases == sorted(phases)


def test_every_referenced_doc_id_is_a_committed_artifact() -> None:
    for event in _events():
        payload = _payload(event)
        for key in ("doc_id", "supersedes"):
            if key not in payload:
                continue
            doc_id = payload[key]
            assert isinstance(doc_id, str)
            artifact = golden_path(doc_id)
            assert artifact.is_file() and artifact.stat().st_size > 0

    referenced = {
        str(_payload(event)["doc_id"]) for event in _events() if "doc_id" in _payload(event)
    }
    assert referenced == {doc.doc_id for doc in GOLDEN_SET}


def test_upload_batch_is_golden_corpus_minus_amendment() -> None:
    uploads = _events_of_type(_events(), "upload")
    doc_ids = [_payload_str(_payload(upload), "doc_id") for upload in uploads]
    assert len(doc_ids) == len(set(doc_ids))
    assert set(doc_ids) == {doc.doc_id for doc in GOLDEN_SET} - {"amendment_2030.pdf"}

    amendments = _events_of_type(_events(), "amendment")
    assert len(amendments) == 1
    assert _payload_str(_payload(amendments[0]), "doc_id") == "amendment_2030.pdf"


def test_needs_ocr_flags_match_golden_pins() -> None:
    for upload in _events_of_type(_events(), "upload"):
        payload = _payload(upload)
        doc_id = _payload_str(payload, "doc_id")
        if golden_doc(doc_id).needs_ocr:
            assert payload.get("needs_ocr") is True
        else:
            assert "needs_ocr" not in payload


def test_findings_pin_to_golden_set() -> None:
    findings = _events_of_type(_events(), "finding")
    assert [_payload_str(_payload(f), "doc_id") for f in findings] == list(_KEYSTONE_ORDER)
    for finding in findings:
        payload = _payload(finding)
        doc = golden_doc(_payload_str(payload, "doc_id"))
        assert _payload_str(payload, "title") == doc.expected_finding_titles[0]
        assert doc.expected_severity is not None
        assert payload["severity"] == doc.expected_severity.value
        assert payload["entities"] == list(doc.expected_entities)
        assert _payload_str(payload, "locator") == doc.locators[0]


def test_attacks_mirror_expected_yaml_exactly() -> None:
    ledger = yaml.safe_load(EXPECTED_YAML.read_text(encoding="utf-8"))
    assert isinstance(ledger, dict)
    rows = ledger["fixtures"]
    assert isinstance(rows, list)

    attacks = _events_of_type(_events(), "attack")
    assert len(attacks) == len(rows) == 20
    for attack, row in zip(attacks, rows, strict=True):
        assert isinstance(row, dict)
        payload = _payload(attack)
        for key in ("attack_class", "expect", "layer", "reason"):
            assert payload[key] == row[key]
        fixture = _payload_str(payload, "fixture")
        assert fixture == row["path"]
        assert (ATTACKS_DIR / fixture).is_file()


def test_amendment_beat_links_lineage_and_finding() -> None:
    amendments = _events_of_type(_events(), "amendment")
    assert len(amendments) == 1
    payload = _payload(amendments[0])
    assert _payload_str(payload, "supersedes") == "vendor_agreement_2027.pdf"
    assert payload["lineage_status"] == LineageStatus.NEW_VERSION.value
    assert payload["update_not_duplicate"] is True
    finding_ids = {
        _payload_str(_payload(finding), "finding_id")
        for finding in _events_of_type(_events(), "finding")
    }
    assert _payload_str(payload, "finding_id") in finding_ids


def test_upgrade_rollback_beat() -> None:
    legal_seed = next(manifest for manifest in SEED_MANIFESTS if manifest.agent_id == "legal")
    upgrades = _events_of_type(_events(), "upgrade")
    rollbacks = _events_of_type(_events(), "rollback")
    assert len(upgrades) == len(rollbacks) == 1
    upgrade = _payload(upgrades[0])
    rollback = _payload(rollbacks[0])
    assert upgrade["agent_id"] == rollback["agent_id"] == "legal"
    assert upgrade["from_version"] == legal_seed.version
    assert upgrade["to_version"] == "2.5.0"
    assert rollback["from_version"] == "2.5.0"
    assert rollback["to_version"] == legal_seed.version
    assert rollback["memory_preserved"] is True


def test_negotiation_lifecycle() -> None:
    envelope = _envelope()
    negotiations = _events_of_type(_events(), "negotiation")
    assert [str(_payload(n)["state"]) for n in negotiations] == [
        NegotiationState.DRAFT.value,
        NegotiationState.APPROVED.value,
        NegotiationState.SEND_LOGGED.value,
    ]
    first = _payload(negotiations[0])
    kind = _payload_str(first, "kind")
    assert kind == NegotiationArtifactKind.SELLER_REQUEST.value
    finding_id = _payload_str(first, "finding_id")
    expected_draft_id = hashlib.sha256(
        f"{envelope['deal_id']}|{finding_id}|{kind}".encode()
    ).hexdigest()[:12]
    for negotiation in negotiations:
        payload = _payload(negotiation)
        assert _payload_str(payload, "draft_id") == expected_draft_id
        assert _payload_str(payload, "finding_id") == finding_id
    assert _payload_str(_payload(negotiations[1]), "approved_by") == "deal-lead"


def test_no_lorem() -> None:
    assert "lorem" not in _raw_text().lower()
