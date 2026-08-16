"""AuthZ enforcement contract tests (BUILD_PLAN D3-M2).

Covers: the full ACL matrix (CATEGORY_OWNERS), cross-deal precedence over
workstream-boundary denial, resource path parsing (both grammars), the
dispatcher authorize/authorized_read flow with denial-event emission via
InMemoryPublisher, and AuthzDenied exception attribute access.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from identity.authz import (
    CATEGORY_OWNERS,
    Action,
    AuthzDenied,
    DenialReason,
    Resource,
    can,
    denial_envelope,
    parse_resource,
)
from identity.principals import principal_for
from registry.models import Workstream
from runtime.dispatcher import authorize, authorized_read
from runtime.events import EventType, InMemoryPublisher

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)

# ── ACL matrix: workstream → owned categories ──────────────────────────────

OWNS: dict[str, list[str]] = {
    "legal": ["contracts", "litigation"],
    "finance": ["financials", "projections", "valuation"],
    "hr": ["rosters", "payroll", "compensation"],
    "ip_tech": ["patents", "licenses", "tech-inventory"],
    "tax": ["tax-filings"],
    "regulatory": ["regulatory"],
    "esg": ["esg"],
    "real_estate": ["leases"],
}

# Flatten: (workstream_value, category) pairs for OWN-READ parametrization.
_OWN_PAIRS: list[tuple[str, str]] = [(ws, cat) for ws, cats in OWNS.items() for cat in cats]


def _resource_for(
    category: str,
    *,
    deal_id: str = "deal-falcon",
    workstream: Workstream | None = None,
    name: str = "doc.pdf",
) -> Resource:
    return Resource(deal_id=deal_id, workstream=workstream, category=category, name=name)


class TestMatrix:
    """Own-category READ is allowed for every workstream × every owned category."""

    @pytest.mark.parametrize(("ws_value", "category"), _OWN_PAIRS)
    def test_own_read_allowed(self, ws_value: str, category: str) -> None:
        principal = principal_for(ws_value, "deal-falcon")
        resource = _resource_for(category)
        allowed, reason = can(principal, Action.READ, resource)
        assert allowed is True
        assert reason is None

    # Vision §7.4 verbatim: legal must NOT read payroll, valuation, or rosters.
    @pytest.mark.parametrize("category", ["payroll", "valuation", "rosters"])
    def test_legal_denied_for_non_legal_category(self, category: str) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = _resource_for(category)
        allowed, reason = can(principal, Action.READ, resource)
        assert allowed is False
        assert reason is DenialReason.workstream_boundary

    # Cross-category denial samples for other workstreams.
    @pytest.mark.parametrize(
        ("ws_value", "foreign_category"),
        [
            ("finance", "contracts"),  # finance reading legal data
            ("hr", "patents"),  # hr reading ip_tech data
            ("ip_tech", "payroll"),  # ip_tech reading hr data
            ("tax", "leases"),  # tax reading real_estate data
            ("esg", "financials"),  # esg reading finance data
            ("real_estate", "tax-filings"),  # real_estate reading tax data
            ("regulatory", "compensation"),  # regulatory reading hr data
        ],
    )
    def test_cross_category_denied(self, ws_value: str, foreign_category: str) -> None:
        principal = principal_for(ws_value, "deal-falcon")
        resource = _resource_for(foreign_category)
        allowed, reason = can(principal, Action.READ, resource)
        assert allowed is False
        assert reason is DenialReason.workstream_boundary

    def test_unknown_category_raises(self) -> None:
        with pytest.raises(ValueError, match="category"):
            _resource_for("nonexistent-category")


class TestCrossDeal:
    """Cross-deal denial takes precedence even when the category is owned."""

    def test_cross_deal_denied_for_own_category(self) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = _resource_for("contracts", deal_id="deal-osprey")
        allowed, reason = can(principal, Action.READ, resource)
        assert allowed is False
        assert reason is DenialReason.cross_deal

    def test_cross_deal_precedence_over_workstream_boundary(self) -> None:
        # legal@deal-falcon reading payroll in deal-osprey:
        # payroll is hr-owned (workstream_boundary), but cross-deal fires first.
        principal = principal_for("legal", "deal-falcon")
        resource = _resource_for("payroll", deal_id="deal-osprey")
        allowed, reason = can(principal, Action.READ, resource)
        assert allowed is False
        assert reason is DenialReason.cross_deal


class TestParseResource:
    """parse_resource accepts both full and bare grammars."""

    def test_full_grammar(self) -> None:
        raw = "deals/deal-falcon/workstreams/legal/contracts/msa.pdf"
        resource = parse_resource(raw)
        assert resource.deal_id == "deal-falcon"
        assert resource.workstream is Workstream.LEGAL
        assert resource.category == "contracts"
        assert resource.name == "msa.pdf"

    def test_bare_grammar_with_deal_id(self) -> None:
        resource = parse_resource("contracts/msa.pdf", deal_id="deal-falcon")
        assert resource.deal_id == "deal-falcon"
        assert resource.workstream is None
        assert resource.category == "contracts"
        assert resource.name == "msa.pdf"

    def test_bare_grammar_without_deal_raises(self) -> None:
        with pytest.raises(ValueError, match="deal"):
            parse_resource("contracts/msa.pdf")

    def test_unknown_category_raises(self) -> None:
        with pytest.raises(ValueError, match="category"):
            parse_resource("deals/deal-falcon/workstreams/legal/bogus/doc.pdf")


class TestDispatcher:
    """authorize/authorized_read raise on denial, emit events, no-op on allow."""

    def test_authorize_allowed_returns_none(self) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = _resource_for("contracts")
        publisher = InMemoryPublisher()
        authorize(principal, Action.READ, resource, publisher=publisher)
        assert len(publisher.published) == 0

    def test_authorize_denied_raises_and_emits_event(self) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = _resource_for("payroll")
        publisher = InMemoryPublisher()
        with pytest.raises(AuthzDenied):
            authorize(principal, Action.READ, resource, publisher=publisher)
        assert len(publisher.published) == 1
        payload = json.loads(publisher.published[0])
        assert payload["type"] == EventType.SECURITY_EVENT.value
        assert payload["payload"]["decision"] == "deny"
        assert payload["payload"]["identity"] == principal.name
        assert payload["payload"]["reason"] == "workstream_boundary"

    def test_authorize_denied_without_publisher_still_raises(self) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = _resource_for("payroll")
        with pytest.raises(AuthzDenied):
            authorize(principal, Action.READ, resource)

    def test_authorized_read_allowed(self) -> None:
        principal = principal_for("finance", "deal-falcon")
        resource = _resource_for("valuation")
        publisher = InMemoryPublisher()
        authorized_read(principal, resource, publisher=publisher)
        assert len(publisher.published) == 0

    def test_authorized_read_denied_emits_event(self) -> None:
        principal = principal_for("hr", "deal-falcon")
        resource = _resource_for("contracts")
        publisher = InMemoryPublisher()
        with pytest.raises(AuthzDenied):
            authorized_read(principal, resource, publisher=publisher)
        assert len(publisher.published) == 1


class TestDeniedExceptionCarries:
    """AuthzDenied exposes .principal, .action, .resource, .reason."""

    def test_attributes_accessible(self) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = _resource_for("payroll")
        with pytest.raises(AuthzDenied) as exc_info:
            authorize(principal, Action.READ, resource)
        err = exc_info.value
        assert err.principal is principal
        assert err.action is Action.READ
        assert err.resource is resource
        assert err.reason is DenialReason.workstream_boundary


class TestDenialEnvelope:
    """denial_envelope produces a SECURITY_EVENT with the expected payload."""

    def test_payload_shape(self) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = _resource_for("valuation")
        envelope = denial_envelope(
            principal, Action.READ, resource, DenialReason.workstream_boundary, now=NOW
        )
        assert envelope.actor == principal.name
        assert envelope.type is EventType.SECURITY_EVENT
        assert envelope.deal_id == "deal-falcon"
        assert envelope.payload["decision"] == "deny"
        assert envelope.payload["identity"] == principal.name
        assert envelope.payload["action"] == "read"
        assert envelope.payload["reason"] == "workstream_boundary"


class TestCategoryOwnersMapping:
    """CATEGORY_OWNERS is complete and correct per the ACL matrix."""

    @pytest.mark.parametrize(
        ("category", "expected_ws"),
        [
            ("contracts", Workstream.LEGAL),
            ("litigation", Workstream.LEGAL),
            ("financials", Workstream.FINANCE),
            ("projections", Workstream.FINANCE),
            ("valuation", Workstream.FINANCE),
            ("rosters", Workstream.HR),
            ("payroll", Workstream.HR),
            ("compensation", Workstream.HR),
            ("patents", Workstream.IP_TECH),
            ("licenses", Workstream.IP_TECH),
            ("tech-inventory", Workstream.IP_TECH),
            ("tax-filings", Workstream.TAX),
            ("regulatory", Workstream.REGULATORY),
            ("esg", Workstream.ESG),
            ("leases", Workstream.REAL_ESTATE),
        ],
    )
    def test_category_owner(self, category: str, expected_ws: Workstream) -> None:
        assert CATEGORY_OWNERS[category] is expected_ws

    def test_category_owners_count(self) -> None:
        assert len(CATEGORY_OWNERS) == 15
