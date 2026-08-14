"""Domain schema contract tests (BUILD_PLAN D1-M4, vision §4.1/§7.1/§9)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from memory.findings import Evidence, Finding, FindingSeverity, FindingStatus
from registry.models import AgentManifest, AgentVersion, Workstream
from runtime.deal import Deal

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


class TestAgentVersion:
    def test_construct_with_defaults(self) -> None:
        version = AgentVersion(
            version="2.4.0",
            model_id="gemini-3.5-flash",
            prompt_ref="agents.legal.prompts",
            created_at=NOW,
        )
        assert version.approved is False
        assert version.eval_score is None
        assert version.rollback_target is None


class TestAgentManifest:
    def test_legal_agent_manifest_contract(self) -> None:
        manifest = AgentManifest(
            agent_id="legal",
            name="Legal Agent",
            version="2.4.0",
            capabilities=("contract analysis", "change-of-control detection"),
            owner="team-b",
            required_identity="legal-data-reader",
            allowed_tools=("data-room-read", "finding-create", "gateway-query"),
            supported_document_types=("contract", "litigation"),
            policy_profile="standard",
            approved=True,
            created_at=NOW,
        )
        assert manifest.external_communication == "prohibited"
        assert manifest.workstream is Workstream.LEGAL
        assert manifest.rollback_target is None

    def test_rejects_unknown_agent_id(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            AgentManifest(
                agent_id="marketing",
                name="Marketing Agent",
                version="0.1.0",
                capabilities=(),
                owner="team-b",
                required_identity="marketing-data-reader",
                allowed_tools=(),
                supported_document_types=(),
                policy_profile="standard",
                created_at=NOW,
            )


class TestDeal:
    def test_project_falcon_contract(self) -> None:
        deal = Deal(
            deal_id="deal-falcon",
            name="Project Falcon",
            target="Acme Robotics",
            deal_type="Acquisition",
            regions=("US", "EU"),
            expected_window_days=21,
            policy_profile_id="standard",
            created_at=NOW,
        )
        assert deal.status == "active"
        assert deal.regions == ("US", "EU")


class TestFinding:
    def _finding(self, **overrides: object) -> Finding:
        base: dict[str, object] = {
            "finding_id": "LEGAL-001",
            "deal_id": "deal-falcon",
            "workstream": Workstream.LEGAL,
            "title": "Customer X change-of-control termination right",
            "summary": "Top customer agreement contains a CoC termination right.",
            "severity": FindingSeverity.HIGH,
            "confidence": 0.94,
            "status": FindingStatus.CANDIDATE,
            "evidence": (
                Evidence(
                    verbatim_span="may terminate upon a change of control",
                    document_id="contract_customer_x.pdf",
                ),
            ),
            "source_documents": ("contract_customer_x.pdf",),
            "owner": "legal-agent@deal-falcon",
            "created_at": NOW,
            "updated_at": NOW,
        }
        base.update(overrides)
        finding = Finding(**base)  # type: ignore[arg-type]
        return finding

    def test_full_contract_per_vision_section_9(self) -> None:
        finding = self._finding()
        assert finding.severity is FindingSeverity.HIGH
        assert finding.evidence[0].verbatim_span
        assert finding.related_findings == ()
        assert finding.audit_trace_id is None

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            self._finding(confidence=1.2)

    def test_empty_evidence_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="evidence"):
            self._finding(evidence=())

    def test_severity_and_status_enums_complete(self) -> None:
        assert {s.value for s in FindingSeverity} == {
            "informational",
            "low",
            "medium",
            "high",
            "critical",
        }
        assert {s.value for s in FindingStatus} == {
            "candidate",
            "validated",
            "open",
            "resolved",
            "dismissed",
        }
