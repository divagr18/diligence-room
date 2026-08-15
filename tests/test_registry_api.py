"""Registry seed + API contract tests (BUILD_PLAN D2-M5, scenarios S3/S4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from google.cloud import firestore

from registry.api import create_app
from registry.seed import SEED_MANIFESTS, seed_registry
from registry.store import AgentRegistryStore

EXPECTED_SEED_VERSIONS: dict[str, str] = {
    "legal": "2.4.0",
    "finance": "3.1.0",
    "hr": "1.8.0",
    "ip_tech": "2.2.0",
    "tax": "1.5.0",
    "regulatory": "2.0.0",
    "esg": "1.3.0",
    "real_estate": "1.1.0",
}

NOW = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)


@pytest.fixture()
def store(firestore_client: firestore.Client) -> AgentRegistryStore:
    return AgentRegistryStore(firestore_client)


@pytest.fixture()
def seeded_store(store: AgentRegistryStore) -> AgentRegistryStore:
    seed_registry(store, now=NOW)
    return store


class TestSeed:
    def test_seed_has_all_eight_workstream_manifests(self) -> None:
        assert len(SEED_MANIFESTS) == 8
        assert {manifest.agent_id for manifest in SEED_MANIFESTS} == set(EXPECTED_SEED_VERSIONS)

    def test_seed_versions_match_vision_registry(self) -> None:
        versions = {m.agent_id: m.version for m in SEED_MANIFESTS}
        assert versions == EXPECTED_SEED_VERSIONS

    def test_seed_populates_store(self, store: AgentRegistryStore) -> None:
        created = seed_registry(store, now=NOW)
        assert created == 8
        manifests = store.list_manifests()
        assert len(manifests) == 8

    def test_seed_is_idempotent(self, store: AgentRegistryStore) -> None:
        seed_registry(store, now=NOW)
        created_again = seed_registry(store, now=NOW)
        assert created_again == 0
        assert len(store.list_manifests()) == 8

    def test_seed_adds_current_version_record(self, seeded_store: AgentRegistryStore) -> None:
        version = seeded_store.get_version("legal", "2.4.0")
        assert version.model_id == "gemini-3.5-flash"
        assert version.approved is True


class TestRegistryApi:
    def test_get_agents_lists_all_eight_seeded(self, seeded_store: AgentRegistryStore) -> None:
        client = TestClient(create_app(seeded_store))
        response = client.get("/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 8
        assert {a["agent_id"]: a["version"] for a in agents} == EXPECTED_SEED_VERSIONS

    def test_post_agent_creates_manifest(self, store: AgentRegistryStore) -> None:
        client = TestClient(create_app(store))
        payload = {
            "agent_id": "legal",
            "name": "Legal Agent",
            "version": "2.4.0",
            "capabilities": ["contract analysis"],
            "owner": "team-b",
            "required_identity": "legal-agent@deal",
            "allowed_tools": ["data-room-read", "finding-create", "gateway-query"],
            "supported_document_types": ["contract"],
            "policy_profile": "falcon-standard-v1",
        }
        response = client.post("/agents", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["agent_id"] == "legal"
        assert body["approved"] is False
        listed = client.get("/agents").json()
        assert [a["agent_id"] for a in listed] == ["legal"]

    def test_post_duplicate_agent_returns_409(self, seeded_store: AgentRegistryStore) -> None:
        client = TestClient(create_app(seeded_store))
        payload = {
            "agent_id": "legal",
            "name": "Legal Agent",
            "version": "9.9.9",
            "capabilities": [],
            "owner": "team-b",
            "required_identity": "legal-agent@deal",
            "allowed_tools": [],
            "supported_document_types": [],
            "policy_profile": "falcon-standard-v1",
        }
        response = client.post("/agents", json=payload)
        assert response.status_code == 409

    def test_get_versions_of_seeded_agent(self, seeded_store: AgentRegistryStore) -> None:
        client = TestClient(create_app(seeded_store))
        response = client.get("/agents/legal/versions")
        assert response.status_code == 200
        versions = response.json()
        assert [v["version"] for v in versions] == ["2.4.0"]

    def test_get_versions_of_unknown_agent_returns_404(
        self, seeded_store: AgentRegistryStore
    ) -> None:
        client = TestClient(create_app(seeded_store))
        assert client.get("/agents/ghost/versions").status_code == 404

    def test_approval_roundtrip(self, seeded_store: AgentRegistryStore) -> None:
        client = TestClient(create_app(seeded_store))
        patch = client.patch(
            "/agents/legal/approval",
            json={"approved": False, "rollback_target": "2.3.0", "eval_score": 0.92},
        )
        assert patch.status_code == 200
        updated = patch.json()
        assert updated["approved"] is False
        assert updated["rollback_target"] == "2.3.0"
        assert updated["eval_score"] == 0.92
        legal = next(a for a in client.get("/agents").json() if a["agent_id"] == "legal")
        assert legal["approved"] is False
        assert legal["rollback_target"] == "2.3.0"
        assert legal["eval_score"] == 0.92

    def test_patch_approval_unknown_agent_returns_404(
        self, seeded_store: AgentRegistryStore
    ) -> None:
        client = TestClient(create_app(seeded_store))
        response = client.patch("/agents/ghost/approval", json={"approved": True})
        assert response.status_code == 404


class TestManifestValidation:
    def test_post_invalid_agent_id_returns_422_via_store_error(
        self, store: AgentRegistryStore
    ) -> None:
        client = TestClient(create_app(store))
        payload = {
            "agent_id": "marketing",
            "name": "Marketing Agent",
            "version": "0.1.0",
            "capabilities": [],
            "owner": "team-b",
            "required_identity": "marketing-agent@deal",
            "allowed_tools": [],
            "supported_document_types": [],
            "policy_profile": "falcon-standard-v1",
        }
        response = client.post("/agents", json=payload)
        assert response.status_code == 422
        assert client.get("/agents").json() == []
