"""Firestore-backed Agent Registry store (BUILD_PLAN D2-M3).

Layout: ``agents/{agent_id}`` (manifests),
``agents/{agent_id}/versions/{version}`` (versions) — top-level ``agents``
collection, see docs/firestore_layout.md for the path-parity rationale.
Tuples serialize as lists; datetimes pass through as native Firestore Timestamps.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, cast

from google.cloud import firestore

from registry.models import AgentManifest, AgentVersion

_COLLECTION = "agents"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AgentNotFoundError(KeyError):
    """Raised when a requested agent_id does not exist in the registry."""


class DuplicateAgentError(ValueError):
    """Raised when creating a manifest or version that already exists."""


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def manifest_to_doc(manifest: AgentManifest) -> dict[str, Any]:
    """Convert an AgentManifest to a Firestore-compatible document dict."""
    raw = asdict(manifest)
    return {
        "agent_id": raw["agent_id"],
        "name": raw["name"],
        "version": raw["version"],
        "capabilities": list(raw["capabilities"]),
        "owner": raw["owner"],
        "required_identity": raw["required_identity"],
        "allowed_tools": list(raw["allowed_tools"]),
        "supported_document_types": list(raw["supported_document_types"]),
        "policy_profile": raw["policy_profile"],
        "created_at": raw["created_at"],
        "external_communication": raw["external_communication"],
        "approved": raw["approved"],
        "eval_score": raw["eval_score"],
        "deployment_status": raw["deployment_status"],
        "rollback_target": raw["rollback_target"],
        "known_limitations": raw["known_limitations"],
        "last_security_review": raw["last_security_review"],
    }


def manifest_from_doc(doc: dict[str, Any]) -> AgentManifest:
    """Reconstruct an AgentManifest from a Firestore document dict."""
    return AgentManifest(
        agent_id=doc["agent_id"],
        name=doc["name"],
        version=doc["version"],
        capabilities=tuple(doc["capabilities"]),
        owner=doc["owner"],
        required_identity=doc["required_identity"],
        allowed_tools=tuple(doc["allowed_tools"]),
        supported_document_types=tuple(doc["supported_document_types"]),
        policy_profile=doc["policy_profile"],
        created_at=_as_datetime(doc["created_at"]),
        external_communication=doc["external_communication"],
        approved=doc["approved"],
        eval_score=doc["eval_score"],
        deployment_status=doc["deployment_status"],
        rollback_target=doc["rollback_target"],
        known_limitations=doc["known_limitations"],
        last_security_review=(
            _as_datetime(doc["last_security_review"])
            if doc["last_security_review"] is not None
            else None
        ),
    )


def version_to_doc(version: AgentVersion) -> dict[str, Any]:
    """Convert an AgentVersion to a Firestore-compatible document dict."""
    raw = asdict(version)
    return {
        "version": raw["version"],
        "model_id": raw["model_id"],
        "prompt_ref": raw["prompt_ref"],
        "created_at": raw["created_at"],
        "approved": raw["approved"],
        "eval_score": raw["eval_score"],
        "rollback_target": raw["rollback_target"],
        "changelog": raw["changelog"],
    }


def version_from_doc(doc: dict[str, Any]) -> AgentVersion:
    """Reconstruct an AgentVersion from a Firestore document dict."""
    return AgentVersion(
        version=doc["version"],
        model_id=doc["model_id"],
        prompt_ref=doc["prompt_ref"],
        created_at=_as_datetime(doc["created_at"]),
        approved=doc["approved"],
        eval_score=doc["eval_score"],
        rollback_target=doc["rollback_target"],
        changelog=doc["changelog"],
    )


def _as_datetime(value: Any) -> datetime:
    """Return *value* as a tz-aware datetime.

    Firestore returns ``google.cloud.firestore.DatetimeWithNanoseconds`` on read,
    which IS already a ``datetime`` subclass with ``tzinfo`` set. We pass it
    through unchanged; microsecond equality holds.
    """
    if isinstance(value, datetime):
        return value
    # Fallback for string-encoded timestamps (shouldn't happen via native client).
    return datetime.fromisoformat(str(value))  # pragma: no cover


def _require_dict(snap: Any) -> dict[str, Any]:
    """Extract the dict payload from a snapshot, satisfying the type checker."""
    data = snap.to_dict()
    assert data is not None  # caller guarantees snapshot exists
    return cast("dict[str, Any]", data)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class AgentRegistryStore:
    """Firestore-backed store for agent manifests and versions."""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client
        self._agents = client.collection(_COLLECTION)

    # -- manifests ----------------------------------------------------------

    def create_manifest(self, manifest: AgentManifest) -> None:
        """Persist *manifest*. Raises DuplicateAgentError if agent_id exists."""
        ref = self._agents.document(manifest.agent_id)
        if ref.get().exists:
            raise DuplicateAgentError(f"agent {manifest.agent_id!r} already registered")
        ref.set(manifest_to_doc(manifest))

    def get_manifest(self, agent_id: str) -> AgentManifest:
        """Return the AgentManifest for *agent_id*, or raise AgentNotFoundError."""
        ref = self._agents.document(agent_id)
        snap = ref.get()
        if not snap.exists:
            raise AgentNotFoundError(f"agent {agent_id!r} not found")
        return manifest_from_doc(_require_dict(snap))

    def list_manifests(self) -> list[AgentManifest]:
        """Return every registered manifest."""
        return [manifest_from_doc(_require_dict(snap)) for snap in self._agents.stream()]

    def update_approval(
        self,
        agent_id: str,
        *,
        approved: bool,
        rollback_target: str | None = None,
        eval_score: float | None = None,
    ) -> AgentManifest:
        """Update approval state; returns the updated manifest."""
        ref = self._agents.document(agent_id)
        if not ref.get().exists:
            raise AgentNotFoundError(f"agent {agent_id!r} not found")
        ref.update(
            {
                "approved": approved,
                "rollback_target": rollback_target,
                "eval_score": eval_score,
            }
        )
        snap = ref.get()
        return manifest_from_doc(_require_dict(snap))

    def publish_version(self, agent_id: str, version: AgentVersion) -> AgentManifest:
        """Register *version* and point the manifest at it, unapproved.

        Publishing a candidate never auto-approves it — shadow evaluation
        gates promotion (doctrine §1). The manifest's ``rollback_target``
        pre-declares the version the fleet returns to if the candidate
        fails. Raises AgentNotFoundError for an unknown agent and
        DuplicateAgentError if the version is already registered.
        """
        current = self.get_manifest(agent_id)
        self.add_version(agent_id, version)
        ref = self._agents.document(agent_id)
        ref.update(
            {
                "version": version.version,
                "approved": False,
                "rollback_target": current.version,
            }
        )
        snap = ref.get()
        return manifest_from_doc(_require_dict(snap))

    def rollback(self, agent_id: str, target_version: str) -> AgentManifest:
        """Roll *agent_id* back to *target_version*; returns the updated manifest.

        Restores the manifest's version to the known-good *target_version*,
        re-approves it, and records the failed version it replaces in
        ``rollback_target``. Deal memory is untouched: findings live in
        ``deals/{id}/findings/{fid}``, outside registry versioning. Raises
        AgentNotFoundError for an unknown agent or an unregistered target.
        """
        current = self.get_manifest(agent_id)
        self.get_version(agent_id, target_version)
        ref = self._agents.document(agent_id)
        ref.update(
            {
                "version": target_version,
                "approved": True,
                "rollback_target": current.version,
            }
        )
        snap = ref.get()
        return manifest_from_doc(_require_dict(snap))

    # -- versions -----------------------------------------------------------

    def add_version(self, agent_id: str, version: AgentVersion) -> None:
        """Persist *version* under *agent_id*. Raises DuplicateAgentError
        if the version already exists; raises AgentNotFoundError if agent_id does not."""
        agent_ref = self._agents.document(agent_id)
        if not agent_ref.get().exists:
            raise AgentNotFoundError(f"agent {agent_id!r} not found")
        versions_col = agent_ref.collection("versions")
        ref = versions_col.document(version.version)
        if ref.get().exists:
            raise DuplicateAgentError(
                f"version {version.version!r} already registered for {agent_id!r}"
            )
        ref.set(version_to_doc(version))

    def get_version(self, agent_id: str, version_id: str) -> AgentVersion:
        """Return a specific version, or raise AgentNotFoundError."""
        ref = self._agents.document(agent_id).collection("versions").document(version_id)
        snap = ref.get()
        if not snap.exists:
            raise AgentNotFoundError(f"version {version_id!r} not found for {agent_id!r}")
        return version_from_doc(_require_dict(snap))

    def list_versions(self, agent_id: str) -> list[AgentVersion]:
        """Return all versions for *agent_id* in created_at DESC order.

        Raises AgentNotFoundError if the agent does not exist.
        """
        agent_ref = self._agents.document(agent_id)
        if not agent_ref.get().exists:
            raise AgentNotFoundError(f"agent {agent_id!r} not found")
        snapshots = (
            agent_ref.collection("versions")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [version_from_doc(_require_dict(snap)) for snap in snapshots]
