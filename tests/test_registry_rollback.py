"""Legal v2.5 upgrade + rollback preserving memory (BUILD_PLAN D12-M4).

The full upgrade/rollback beat against the Firestore emulator: seed the
eight manifests, publish Legal v2.5 (the deliberate CoC-prompt regression),
watch the shadow harness go RED on the missing CoC pin, roll back through
``AgentRegistryStore.rollback``, and verify the restored fleet passes the
harness again while the findings partition (``deals/{id}/findings/{fid}``)
stays untouched — registry versioning never reaches deal memory. The
registry API PATCH contract and the dashboard Registry view both surface
the rollback pointer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.cloud import firestore

from agents.fleet import DEEP_WORKSTREAM_DOCUMENTS
from dashboard.api.app import create_app as create_dashboard_app
from evals.golden_set import golden_doc
from evals.harness import run_harness
from evals.legal_v25 import (
    LEGAL_V25_CHANGELOG,
    LEGAL_V25_VERSION,
    extractor_from_registry,
    publish_legal_v25,
)
from memory.findings import FindingsStore
from registry.api import create_app as create_registry_app
from registry.seed import seed_registry
from registry.store import AgentRegistryStore

NOW = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
# Strictly later than NOW so list_versions (created_at DESC) orders 2.5.0 first.
PUBLISH_NOW = NOW + timedelta(hours=1)
KNOWN_GOOD_VERSION = "2.4.0"
COC_DOC_ID = "contract_meridian_logistics.pdf"
_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def seeded_store(firestore_client: firestore.Client) -> AgentRegistryStore:
    store = AgentRegistryStore(firestore_client)
    seed_registry(store, now=NOW)
    return store


def _finding_counts(client: firestore.Client, deal_id: str) -> dict[str, int]:
    store = FindingsStore(client)
    return {
        workstream.value: len(store.list_for_workstream(deal_id, workstream))
        for workstream in DEEP_WORKSTREAM_DOCUMENTS
    }


class TestPublishLegalV25:
    def test_publish_registers_unapproved_candidate_with_rollback_target(
        self, seeded_store: AgentRegistryStore
    ) -> None:
        manifest = publish_legal_v25(seeded_store, now=PUBLISH_NOW)

        assert manifest.version == LEGAL_V25_VERSION
        assert manifest.approved is False
        assert manifest.rollback_target == KNOWN_GOOD_VERSION

        version = seeded_store.get_version("legal", LEGAL_V25_VERSION)
        assert version.changelog == LEGAL_V25_CHANGELOG
        assert version.approved is False
        assert version.rollback_target == KNOWN_GOOD_VERSION

        # The seeded roster of eight is intact; legal simply gains a version.
        assert len(seeded_store.list_manifests()) == 8
        assert [v.version for v in seeded_store.list_versions("legal")] == [
            LEGAL_V25_VERSION,
            KNOWN_GOOD_VERSION,
        ]


class TestHarnessRedGreen:
    def test_published_legal_v25_drives_the_harness_red(
        self, firestore_client: firestore.Client, seeded_store: AgentRegistryStore
    ) -> None:
        publish_legal_v25(seeded_store, now=PUBLISH_NOW)

        report = run_harness(
            firestore_client, "deal-rollback-red", extractor_from_registry(seeded_store)
        )

        assert report.passed is False
        assert [doc.doc_id for doc in report.missing] == [COC_DOC_ID]
        assert report.downgraded == ()

    def test_rollback_restores_the_fleet_and_preserves_findings(
        self, firestore_client: firestore.Client, seeded_store: AgentRegistryStore
    ) -> None:
        publish_legal_v25(seeded_store, now=PUBLISH_NOW)
        deal_id = "deal-rollback"

        # RED: the published Legal v2.5 candidate fails the shadow eval.
        red = run_harness(firestore_client, deal_id, extractor_from_registry(seeded_store))
        assert red.passed is False
        assert [doc.doc_id for doc in red.missing] == [COC_DOC_ID]
        counts_before = _finding_counts(firestore_client, deal_id)

        rolled_back = seeded_store.rollback("legal", KNOWN_GOOD_VERSION)

        assert rolled_back.version == KNOWN_GOOD_VERSION
        assert rolled_back.approved is True
        assert rolled_back.rollback_target == LEGAL_V25_VERSION
        # Registry versioning never reaches deals/{id}/findings/{fid}.
        assert _finding_counts(firestore_client, deal_id) == counts_before
        legal_findings = FindingsStore(firestore_client).list_for_workstream(deal_id, "legal")
        pinned_title = golden_doc(COC_DOC_ID).expected_finding_titles[0]
        assert len(legal_findings) == 1
        assert all(finding.title != pinned_title for finding in legal_findings)

        # GREEN: the restored fleet, selected by the rolled-back registry, passes.
        green = run_harness(
            firestore_client, "deal-rollback-restored", extractor_from_registry(seeded_store)
        )
        assert green.passed is True
        assert green.missing == ()
        assert green.downgraded == ()


class TestRegistryApiRollbackSurface:
    def test_patch_approval_still_returns_rollback_target_after_rollback(
        self, seeded_store: AgentRegistryStore
    ) -> None:
        publish_legal_v25(seeded_store, now=PUBLISH_NOW)
        seeded_store.rollback("legal", KNOWN_GOOD_VERSION)
        client = TestClient(create_registry_app(seeded_store))

        legal = next(a for a in client.get("/agents").json() if a["agent_id"] == "legal")
        assert legal["version"] == KNOWN_GOOD_VERSION
        assert legal["approved"] is True
        assert legal["rollback_target"] == LEGAL_V25_VERSION

        patch = client.patch(
            "/agents/legal/approval",
            json={"approved": True, "rollback_target": LEGAL_V25_VERSION},
        )
        assert patch.status_code == 200
        assert patch.json()["approved"] is True
        assert patch.json()["rollback_target"] == LEGAL_V25_VERSION


class TestDashboardRollbackBadge:
    def test_registry_api_carries_rollback_target_for_the_badge(
        self, seeded_store: AgentRegistryStore
    ) -> None:
        publish_legal_v25(seeded_store, now=PUBLISH_NOW)
        seeded_store.rollback("legal", KNOWN_GOOD_VERSION)

        client = TestClient(create_dashboard_app(registry_manifests=seeded_store.list_manifests()))
        agents = client.get("/api/registry").json()
        assert len(agents) == 8
        legal = next(a for a in agents if a["agent_id"] == "legal")
        assert legal["version"] == KNOWN_GOOD_VERSION
        assert legal["approved"] is True
        assert legal["rollback_target"] == LEGAL_V25_VERSION

        # The Registry view renders its rollback badge conditional on this field.
        view = (_REPO_ROOT / "dashboard" / "web" / "src" / "views" / "Registry.tsx").read_text(
            encoding="utf-8"
        )
        assert "agent.rollback_target" in view
