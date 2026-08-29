"""Memory Bank wiring: scoping, the disabled-by-default gate, and the hook.

All offline. The live client is never constructed here — what matters is that
the flag genuinely gates it, that the fake honours the same deal scoping the
live path uses, and that the coordinator hook is inert when Memory Bank is off,
so the 1107-test battery never reaches the network.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from memory.findings import Evidence, Finding, FindingSeverity, FindingStatus
from memory.memory_bank import (
    APP_NAME,
    EntityMemory,
    FakeMemoryBank,
    LiveMemoryBank,
    memory_bank_from_env,
)
from registry.models import Workstream

_FLAG = "DILIGENCE_MEMORY_BANK_ENABLED"

# Findings are evidence-gated at construction, so a fixture needs a real span.
_EVIDENCE = Evidence(
    verbatim_span="Change of Control of the other Party",
    document_id="contract_meridian_logistics.pdf",
)


def _memory(deal_id: str = "deal-falcon", entity: str = "Meridian Logistics, Inc.") -> EntityMemory:
    return EntityMemory(
        deal_id=deal_id,
        entity=entity,
        summary="change-of-control termination right; 18.3% of FY27 revenue",
        finding_id="f4c993d48cda",
    )


class TestEntityMemory:
    def test_text_leads_with_the_entity(self) -> None:
        """Similarity search is on the stored text, so the name comes first."""
        text = _memory().as_text()
        assert text.startswith("Meridian Logistics, Inc.:")
        assert "f4c993d48cda" in text


class TestFakeMemoryBank:
    def test_recall_finds_the_entity(self) -> None:
        bank = FakeMemoryBank()
        bank.remember_entity(_memory())
        assert bank.recall("deal-falcon", "Meridian")

    def test_recall_is_scoped_per_deal(self) -> None:
        """Scope is (app_name, deal_id); another deal must not see the memory."""
        bank = FakeMemoryBank()
        bank.remember_entity(_memory(deal_id="deal-falcon"))
        assert bank.recall("deal-other", "Meridian") == ()

    def test_recall_misses_are_empty_not_errors(self) -> None:
        assert FakeMemoryBank().recall("deal-falcon", "Meridian") == ()


class TestGate:
    def test_live_client_refuses_without_the_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_FLAG, raising=False)
        with pytest.raises(RuntimeError, match=_FLAG):
            LiveMemoryBank(project="p")

    def test_live_client_refuses_without_a_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_FLAG, "1")
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        with pytest.raises(RuntimeError, match="project"):
            LiveMemoryBank()

    def test_factory_returns_none_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The default answer offline, and every caller treats None as skip."""
        monkeypatch.delenv(_FLAG, raising=False)
        assert memory_bank_from_env() is None

    def test_factory_returns_none_when_misconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Enabled but no project: still None, never an exception into a finding."""
        monkeypatch.setenv(_FLAG, "1")
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        assert memory_bank_from_env() is None

    def test_app_name_is_stable(self) -> None:
        """The scope key is half of the isolation boundary; pin it."""
        assert APP_NAME == "diligence-room"


class TestCoordinatorHook:
    def test_hook_is_inert_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A finding must still be written when Memory Bank is off."""
        from agents.coordinator.synthesize import _remember_entity

        monkeypatch.delenv(_FLAG, raising=False)
        now = datetime.now(UTC)
        finding = Finding(
            finding_id="f4c993d48cda",
            deal_id="deal-falcon",
            workstream=Workstream.LEGAL,
            title="Compound customer-exit exposure",
            summary="four workstreams converge on Meridian Logistics, Inc.",
            severity=FindingSeverity.CRITICAL,
            confidence=0.9,
            status=FindingStatus.OPEN,
            evidence=(_EVIDENCE,),
            owner="coordinator@deal-falcon",
            created_at=now,
            updated_at=now,
        )
        # No exception and no network: the hook simply returns.
        _remember_entity("deal-falcon", "Meridian Logistics, Inc.", finding)

    def test_hook_swallows_write_failures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Memory is additive; a bank outage must not fail a durable finding."""
        import agents.coordinator.synthesize as synth

        class _Exploding:
            def remember_entity(self, memory: EntityMemory) -> None:
                raise RuntimeError("memory bank unavailable")

            def recall(self, deal_id: str, query: str) -> tuple[str, ...]:
                return ()

        monkeypatch.setattr(synth, "memory_bank_from_env", _Exploding)
        now = datetime.now(UTC)
        finding = Finding(
            finding_id="f4c993d48cda",
            deal_id="deal-falcon",
            workstream=Workstream.LEGAL,
            title="Compound customer-exit exposure",
            summary="four workstreams converge on Meridian Logistics, Inc.",
            severity=FindingSeverity.CRITICAL,
            confidence=0.9,
            status=FindingStatus.OPEN,
            evidence=(_EVIDENCE,),
            owner="coordinator@deal-falcon",
            created_at=now,
            updated_at=now,
        )
        synth._remember_entity("deal-falcon", "Meridian Logistics, Inc.", finding)
