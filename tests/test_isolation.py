"""Negative isolation suite — cross-workstream & cross-deal denial audit (BUILD_PLAN D3-M5).

Proves:
  Legal ⊬ Finance, Finance ⊬ HR, HR ⊬ valuation  (workstream boundary)
  cross-deal read                                  (cross-deal precedence)
Each denial asserts AuthzDenied AND a security.event record in the Firestore
audit log via EventLog.
"""

from __future__ import annotations

import json

import pytest
from google.cloud import firestore

from identity.authz import (
    CATEGORY_OWNERS,
    Action,
    AuthzDenied,
    DenialReason,
    Resource,
    parse_resource,
)
from identity.principals import principal_for
from memory.event_log import EventLog, EventRecord
from registry.models import Workstream
from runtime.dispatcher import authorize
from runtime.events import EventEnvelope, EventType

# ── Publisher adapter ───────────────────────────────────────────────────────


class _EventLogPublisher:
    """Adapter: routes denial envelopes into the emulator-backed EventLog.

    Satisfies the dispatcher's ``_Publisher`` Protocol
    (``publish(event) -> str``).
    """

    def __init__(self, client: firestore.Client) -> None:
        self._log = EventLog(client)

    def publish(self, event: EventEnvelope) -> str:
        seq = self._log.append(event)
        return str(seq)


# ── Assertion helpers ────────────────────────────────────────────────────────


def _assert_denial_event(
    records: list[EventRecord],
    *,
    expected_identity: str,
    expected_reason: str,
) -> None:
    """Assert exactly one security.event denial record with matching payload."""
    assert len(records) == 1, f"expected 1 audit record, got {len(records)}"
    rec = records[0]
    assert rec.type == EventType.SECURITY_EVENT.value
    payload = json.loads(rec.payload_json)
    assert payload["decision"] == "deny"
    assert payload["identity"] == expected_identity
    assert payload["reason"] == expected_reason


# ── Workstream isolation (emulator) ──────────────────────────────────────────


class TestWorkstreamIsolation:
    """Legal ⊬ Finance, Finance ⊬ HR, HR ⊬ valuation — denied + audited."""

    def test_legal_denied_reading_finance(
        self,
        firestore_client: firestore.Client,
    ) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = parse_resource(
            "deals/deal-falcon/workstreams/finance/financials/q3-projections.xlsx",
        )
        pub = _EventLogPublisher(firestore_client)
        with pytest.raises(AuthzDenied) as exc_info:
            authorize(principal, Action.READ, resource, publisher=pub)
        assert exc_info.value.reason is DenialReason.workstream_boundary

        log = EventLog(firestore_client)
        _assert_denial_event(
            log.events("deal-falcon"),
            expected_identity="legal-agent@deal-falcon",
            expected_reason="workstream_boundary",
        )

    def test_finance_denied_reading_hr(
        self,
        firestore_client: firestore.Client,
    ) -> None:
        principal = principal_for("finance", "deal-falcon")
        resource = parse_resource(
            "deals/deal-falcon/workstreams/hr/payroll/roster-2026.xlsx",
        )
        pub = _EventLogPublisher(firestore_client)
        with pytest.raises(AuthzDenied) as exc_info:
            authorize(principal, Action.READ, resource, publisher=pub)
        assert exc_info.value.reason is DenialReason.workstream_boundary

        log = EventLog(firestore_client)
        _assert_denial_event(
            log.events("deal-falcon"),
            expected_identity="finance-agent@deal-falcon",
            expected_reason="workstream_boundary",
        )

    def test_hr_denied_reading_finance_valuation(
        self,
        firestore_client: firestore.Client,
    ) -> None:
        principal = principal_for("hr", "deal-falcon")
        resource = parse_resource(
            "deals/deal-falcon/workstreams/finance/valuation/vantage-model.xlsx",
        )
        pub = _EventLogPublisher(firestore_client)
        with pytest.raises(AuthzDenied) as exc_info:
            authorize(principal, Action.READ, resource, publisher=pub)
        assert exc_info.value.reason is DenialReason.workstream_boundary

        log = EventLog(firestore_client)
        _assert_denial_event(
            log.events("deal-falcon"),
            expected_identity="hr-agent@deal-falcon",
            expected_reason="workstream_boundary",
        )

    def test_positive_control_legal_reads_own_contract(
        self,
        firestore_client: firestore.Client,
    ) -> None:
        """Allowed read emits NO event."""
        principal = principal_for("legal", "deal-falcon")
        resource = parse_resource(
            "deals/deal-falcon/workstreams/legal/contracts/contract_meridian_logistics.pdf",
        )
        pub = _EventLogPublisher(firestore_client)
        authorize(principal, Action.READ, resource, publisher=pub)

        log = EventLog(firestore_client)
        assert log.events("deal-falcon") == []


# ── Cross-deal isolation (emulator) ─────────────────────────────────────────


class TestCrossDealIsolation:
    """Cross-deal denial takes precedence over workstream boundary; audited."""

    def test_cross_deal_denied_with_precedence(
        self,
        firestore_client: firestore.Client,
    ) -> None:
        principal = principal_for("legal", "deal-falcon")
        resource = parse_resource(
            "deals/deal-osprey/workstreams/legal/contracts/msa.pdf",
        )
        pub = _EventLogPublisher(firestore_client)
        with pytest.raises(AuthzDenied) as exc_info:
            authorize(principal, Action.READ, resource, publisher=pub)
        assert exc_info.value.reason is DenialReason.cross_deal

        log = EventLog(firestore_client)
        # denial_envelope uses resource.deal_id (= "deal-osprey")
        _assert_denial_event(
            log.events("deal-osprey"),
            expected_identity="legal-agent@deal-falcon",
            expected_reason="cross_deal",
        )
        assert log.events("deal-falcon") == []


# ── Full matrix sweep (pure, no emulator) ───────────────────────────────────

_ALL_WORKSTREAMS: list[Workstream] = list(Workstream)
_ALL_CATEGORIES: list[str] = list(CATEGORY_OWNERS)
_SWEEP_PAIRS: list[tuple[str, str]] = [
    (ws.value, cat) for ws in _ALL_WORKSTREAMS for cat in _ALL_CATEGORIES
]


class TestFullMatrixSweep:
    """8 workstreams × 15 categories = 120 pairs; 15 allowed, 105 denied."""

    @pytest.mark.parametrize(("ws_value", "category"), _SWEEP_PAIRS)
    def test_pair(self, ws_value: str, category: str) -> None:
        principal = principal_for(ws_value, "deal-falcon")
        resource = Resource(
            deal_id="deal-falcon",
            workstream=None,
            category=category,
            name="doc.pdf",
        )
        if CATEGORY_OWNERS[category] is Workstream(ws_value):
            authorize(principal, Action.READ, resource)
        else:
            with pytest.raises(AuthzDenied):
                authorize(principal, Action.READ, resource)

    def test_count_allowed_and_denied(self) -> None:
        allowed = 0
        denied = 0
        for ws in _ALL_WORKSTREAMS:
            for cat in _ALL_CATEGORIES:
                principal = principal_for(ws.value, "deal-falcon")
                resource = Resource(
                    deal_id="deal-falcon",
                    workstream=None,
                    category=cat,
                    name="doc.pdf",
                )
                try:
                    authorize(principal, Action.READ, resource)
                    allowed += 1
                except AuthzDenied:
                    denied += 1
        assert allowed == 15
        assert denied == 105
        assert allowed + denied == 120
