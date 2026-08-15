"""Identity principal contract tests (BUILD_PLAN D3-M1).

Covers: Principal naming for all 8 workstreams, deal_id validation,
parse_identity malformed inputs, bind_manifest success/failure, and the
round-trip invariant parse_identity(principal.name) == principal.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from identity.principals import (
    DEAL_PLACEHOLDER,
    Principal,
    bind_manifest,
    parse_identity,
    principal_for,
)
from registry.models import AgentManifest, Workstream

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

ALL_WORKSTREAMS = [param.value for param in Workstream]


def _manifest(*, agent_id: str, required_identity: str) -> AgentManifest:
    return AgentManifest(
        agent_id=agent_id,
        name=f"{agent_id.title()} Agent",
        version="0.1.0",
        capabilities=(),
        owner="team-b",
        required_identity=required_identity,
        allowed_tools=(),
        supported_document_types=(),
        policy_profile="standard",
        created_at=NOW,
    )


class TestPrincipalName:
    @pytest.mark.parametrize("workstream_value", ALL_WORKSTREAMS)
    def test_name_format_for_every_workstream(self, workstream_value: str) -> None:
        principal = Principal(workstream=Workstream(workstream_value), deal_id="deal-falcon")
        assert principal.name == f"{workstream_value}-agent@deal-falcon"

    def test_dataclass_is_frozen_and_slotted(self) -> None:
        principal = Principal(workstream=Workstream.LEGAL, deal_id="deal-falcon")
        with pytest.raises(AttributeError):
            principal.deal_id = "deal-hawk"  # type: ignore[misc]


class TestPrincipalFor:
    def test_accepts_workstream_enum(self) -> None:
        principal = principal_for(Workstream.FINANCE, "deal-falcon")
        assert principal.name == "finance-agent@deal-falcon"

    def test_accepts_workstream_string_value(self) -> None:
        principal = principal_for("hr", "deal-hawk")
        assert principal.name == "hr-agent@deal-hawk"

    def test_rejects_uppercase_deal_id(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            principal_for(Workstream.LEGAL, "DEAL-FALCON")

    def test_rejects_deal_id_starting_with_digit(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            principal_for(Workstream.LEGAL, "1deal")

    def test_rejects_deal_id_with_underscore(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            principal_for(Workstream.LEGAL, "deal_falcon")

    def test_rejects_empty_deal_id(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            principal_for(Workstream.LEGAL, "")

    def test_rejects_unknown_workstream_string(self) -> None:
        with pytest.raises(ValueError):
            principal_for("marketing", "deal-falcon")


class TestParseIdentity:
    def test_round_trip_for_every_workstream(self) -> None:
        for ws_value in ALL_WORKSTREAMS:
            original = Principal(workstream=Workstream(ws_value), deal_id="deal-falcon")
            parsed = parse_identity(original.name)
            assert parsed == original

    def test_rejects_missing_agent_suffix(self) -> None:
        with pytest.raises(ValueError, match="agent"):
            parse_identity("legal@deal-falcon")

    def test_rejects_at_sign_missing(self) -> None:
        with pytest.raises(ValueError, match="@"):
            parse_identity("legal-agent-deal-falcon")

    def test_rejects_unknown_workstream_in_name(self) -> None:
        with pytest.raises(ValueError, match="workstream"):
            parse_identity("marketing-agent@deal-falcon")

    def test_rejects_empty_deal_id(self) -> None:
        with pytest.raises(ValueError, match="deal_id"):
            parse_identity("legal-agent@")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError):
            parse_identity("")


class TestBindManifest:
    def test_bind_legal_manifest_returns_deal_principal(self) -> None:
        manifest = _manifest(
            agent_id="legal",
            required_identity="legal-agent@deal",
        )
        principal = bind_manifest(manifest, "deal-falcon")
        assert principal == Principal(workstream=Workstream.LEGAL, deal_id="deal-falcon")

    def test_bind_finance_manifest(self) -> None:
        manifest = _manifest(
            agent_id="finance",
            required_identity="finance-agent@deal",
        )
        principal = bind_manifest(manifest, "deal-hawk")
        assert principal.name == "finance-agent@deal-hawk"

    def test_rejects_manifest_with_deviating_identity(self) -> None:
        manifest = _manifest(agent_id="legal", required_identity="bogus")
        with pytest.raises(ValueError, match="required_identity"):
            bind_manifest(manifest, "deal-falcon")

    def test_rejects_manifest_bound_to_wrong_deal(self) -> None:
        manifest = _manifest(
            agent_id="legal",
            required_identity="legal-agent@deal-falcon",
        )
        with pytest.raises(ValueError, match="required_identity"):
            bind_manifest(manifest, "deal-falcon")

    def test_rejects_mismatched_agent_id_in_identity(self) -> None:
        manifest = _manifest(
            agent_id="legal",
            required_identity="finance-agent@deal",
        )
        with pytest.raises(ValueError, match="required_identity"):
            bind_manifest(manifest, "deal-falcon")


class TestDealPlaceholder:
    def test_placeholder_value(self) -> None:
        assert DEAL_PLACEHOLDER == "deal"


class TestRoundTrip:
    @pytest.mark.parametrize(
        ("workstream_value", "deal_id"),
        [
            ("legal", "deal-falcon"),
            ("finance", "deal-hawk"),
            ("hr", "deal-orion"),
            ("ip_tech", "deal-nexus"),
            ("tax", "deal-pulse"),
            ("regulatory", "deal-summit"),
            ("esg", "deal-aurora"),
            ("real_estate", "deal-atlas"),
        ],
    )
    def test_parse_identity_of_principal_name_is_identity(
        self, workstream_value: str, deal_id: str
    ) -> None:
        principal = Principal(workstream=Workstream(workstream_value), deal_id=deal_id)
        assert parse_identity(principal.name) == principal
