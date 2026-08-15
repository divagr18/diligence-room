"""Tests for registry.store — AgentRegistryStore backed by the Firestore emulator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from registry.models import AgentManifest, AgentVersion
from registry.store import (
    AgentNotFoundError,
    AgentRegistryStore,
    DuplicateAgentError,
)


def _manifest(agent_id: str = "legal", version: str = "1.0.0") -> AgentManifest:
    return AgentManifest(
        agent_id=agent_id,
        name="Legal Agent",
        version=version,
        capabilities=("contract_review",),
        owner="legal-agent@deal-falcon",
        required_identity="agent-legal",
        allowed_tools=("firestore_read",),
        supported_document_types=("pdf",),
        policy_profile="strict",
        created_at=datetime(2026, 1, 15, 12, 0, 0, 123456, tzinfo=UTC),
    )


def _version(version: str = "1.0.0") -> AgentVersion:
    return AgentVersion(
        version=version,
        model_id="gemini-3.5-flash",
        prompt_ref="prompts/legal/v1",
        created_at=datetime(2026, 1, 15, 12, 0, 0, 123456, tzinfo=UTC),
    )


def test_create_then_get_returns_equal_manifest(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)
    manifest = _manifest()

    store.create_manifest(manifest)
    fetched = store.get_manifest("legal")

    assert fetched == manifest
    assert isinstance(fetched.capabilities, tuple)
    assert isinstance(fetched.allowed_tools, tuple)
    assert isinstance(fetched.supported_document_types, tuple)
    assert fetched.created_at.tzinfo is not None
    assert fetched.created_at.microsecond == manifest.created_at.microsecond


def test_duplicate_create_raises(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)
    store.create_manifest(_manifest())

    with pytest.raises(DuplicateAgentError, match="legal"):
        store.create_manifest(_manifest())


def test_get_unknown_raises(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)

    with pytest.raises(AgentNotFoundError, match="finance"):
        store.get_manifest("finance")


def test_list_versions_unknown_raises(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)

    with pytest.raises(AgentNotFoundError, match="finance"):
        store.list_versions("finance")


def test_add_version_unknown_agent_raises(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)

    with pytest.raises(AgentNotFoundError, match="hr"):
        store.add_version("hr", _version())


def test_update_approval_persists_all_fields(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)
    store.create_manifest(_manifest())

    updated = store.update_approval(
        "legal", approved=True, rollback_target="2.3.0", eval_score=0.92
    )

    assert updated.approved is True
    assert updated.rollback_target == "2.3.0"
    assert updated.eval_score == pytest.approx(0.92)

    refetched = store.get_manifest("legal")
    assert refetched.approved is True
    assert refetched.rollback_target == "2.3.0"
    assert refetched.eval_score == pytest.approx(0.92)


def test_update_approval_unknown_raises(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)

    with pytest.raises(AgentNotFoundError, match="tax"):
        store.update_approval("tax", approved=True)


def test_add_version_duplicate_raises(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)
    store.create_manifest(_manifest())
    store.add_version("legal", _version("1.0.0"))

    with pytest.raises(DuplicateAgentError, match="1.0.0"):
        store.add_version("legal", _version("1.0.0"))


def test_list_versions_descending_order(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)
    store.create_manifest(_manifest())

    v1 = AgentVersion(
        version="1.0.0",
        model_id="gemini-3.5-flash",
        prompt_ref="prompts/legal/v1",
        created_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
    )
    v2 = AgentVersion(
        version="2.0.0",
        model_id="gemini-3.5-flash",
        prompt_ref="prompts/legal/v2",
        created_at=datetime(2026, 2, 15, 12, 0, 0, tzinfo=UTC),
    )
    store.add_version("legal", v1)
    store.add_version("legal", v2)

    versions = store.list_versions("legal")
    assert [v.version for v in versions] == ["2.0.0", "1.0.0"]


def test_list_manifests_returns_all(firestore_client: firestore.Client) -> None:
    store = AgentRegistryStore(firestore_client)
    store.create_manifest(_manifest("legal"))
    store.create_manifest(_manifest("finance", version="1.0.0"))

    manifests = store.list_manifests()
    assert len(manifests) == 2
    ids = {m.agent_id for m in manifests}
    assert ids == {"legal", "finance"}
