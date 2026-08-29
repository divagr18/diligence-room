"""Shape tests for Agent Registry publication (A2A cards + gcloud argv plan).

Pure tests: the card builder and the argv planner touch neither gcloud nor
Firestore, mirroring how `tests/test_data_room_plan.py` covers
`infra.data_room.plan_data_room`.

Each assertion here pins a constraint the platform rejected us for, so a
regression fails locally instead of at `services create`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

from infra.agent_registry import plan_registration, write_cards
from registry.agent_card import (
    A2A_PROTOCOL_VERSION,
    agent_url,
    build_agent_card,
    display_name,
    service_id,
)
from registry.models import AgentManifest

_NOW: Final = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
_GATEWAY: Final = "https://gateway.example.run.app"
# The platform's documented service_id pattern.
_ID_PATTERN: Final = r"^[a-z][a-z0-9-]{2,61}[a-z0-9]$"


def _manifest(agent_id: str, name: str) -> AgentManifest:
    return AgentManifest(
        agent_id=agent_id,
        name=name,
        version="2.4.0",
        capabilities=("contract analysis", "change-of-control detection"),
        owner="team-b",
        required_identity=f"{agent_id}-agent@deal",
        allowed_tools=("finding_create",),
        supported_document_types=("contract",),
        policy_profile="standard",
        created_at=_NOW,
        approved=True,
        eval_score=0.87,
    )


@pytest.mark.parametrize(
    ("agent_id", "expected"),
    [
        ("legal", "diligence-legal"),
        # Underscores are illegal in a service id.
        ("ip_tech", "diligence-ip-tech"),
        # Bare ids under four characters are rejected; the prefix rescues them.
        ("esg", "diligence-esg"),
        ("hr", "diligence-hr"),
        ("tax", "diligence-tax"),
    ],
)
def test_service_id_is_legal(agent_id: str, expected: str) -> None:
    import re

    sid = service_id(_manifest(agent_id, "Agent"))
    assert sid == expected
    assert re.match(_ID_PATTERN, sid), f"{sid!r} violates the platform id pattern"


def test_display_name_drops_the_ampersand() -> None:
    """cmd.exe splits an unescaped ``&``, truncating the gcloud command."""
    assert display_name(_manifest("ip_tech", "IP & Technology Agent")) == (
        "IP and Technology Agent"
    )


def test_card_carries_protocol_version() -> None:
    """The registry rejects a card without protocolVersion."""
    card = build_agent_card(_manifest("legal", "Legal Agent"), _GATEWAY)
    assert card["protocolVersion"] == A2A_PROTOCOL_VERSION


def test_card_url_is_per_agent() -> None:
    """Each service needs a distinct interface URL, so agents cannot share one."""
    legal = build_agent_card(_manifest("legal", "Legal Agent"), _GATEWAY)
    finance = build_agent_card(_manifest("finance", "Finance Agent"), _GATEWAY)
    assert legal["url"] != finance["url"]
    assert legal["url"] == f"{_GATEWAY}/agents/legal"
    assert agent_url(_manifest("hr", "HR Agent"), _GATEWAY) == f"{_GATEWAY}/agents/hr"


def test_card_is_projected_from_the_manifest() -> None:
    """Nothing in the card is invented: capabilities become skills verbatim."""
    manifest = _manifest("legal", "Legal Agent")
    card = build_agent_card(manifest, _GATEWAY)
    assert card["version"] == manifest.version
    skill_names = [skill["name"] for skill in card["skills"]]
    assert skill_names == list(manifest.capabilities)


def test_card_stays_under_the_ten_kb_cap() -> None:
    card = build_agent_card(_manifest("legal", "Legal Agent"), _GATEWAY)
    assert len(json.dumps(card)) < 10_000


def test_plan_registration_shape(tmp_path: Path) -> None:
    manifests = [_manifest("legal", "Legal Agent"), _manifest("ip_tech", "IP & Technology Agent")]
    paths = write_cards(manifests, tmp_path, _GATEWAY)
    steps = plan_registration(manifests, paths, "proj", "us-central1")

    assert len(steps) == 2
    first = steps[0]
    assert first[:4] == ["agent-registry", "services", "create", "diligence-legal"]
    assert "--location=us-central1" in first
    assert "--project=proj" in first
    assert "--agent-spec-type=a2a-agent-card" in first
    # The card goes by file path: inline JSON is mangled by the Windows shim.
    spec = next(a for a in first if a.startswith("--agent-spec-content="))
    written = Path(spec.split("=", 1)[1])
    assert written.is_file()
    assert json.loads(written.read_text(encoding="utf-8"))["name"] == "Legal Agent"


def test_write_cards_names_files_by_service_id(tmp_path: Path) -> None:
    manifests = [_manifest("ip_tech", "IP & Technology Agent")]
    paths = write_cards(manifests, tmp_path, _GATEWAY)
    assert paths["ip_tech"].name == "diligence-ip-tech.json"
