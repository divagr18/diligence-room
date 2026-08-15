"""Agent Registry HTTP API (BUILD_PLAN D2-M5).

Endpoints backed by an injected AgentRegistryStore:

- POST   /agents                    201 create / 409 duplicate / 422 invalid
- GET    /agents                    list all manifests
- GET    /agents/{agent_id}/versions
- PATCH  /agents/{agent_id}/approval (approved, rollback_target, eval_score)
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from registry.models import AgentManifest
from registry.store import AgentNotFoundError, AgentRegistryStore, DuplicateAgentError


class ManifestIn(BaseModel):
    agent_id: str
    name: str
    version: str
    capabilities: list[str]
    owner: str
    required_identity: str
    allowed_tools: list[str]
    supported_document_types: list[str]
    policy_profile: str


class ManifestOut(BaseModel):
    agent_id: str
    name: str
    version: str
    capabilities: list[str]
    owner: str
    required_identity: str
    allowed_tools: list[str]
    supported_document_types: list[str]
    policy_profile: str
    created_at: datetime
    external_communication: str
    approved: bool
    eval_score: float | None
    deployment_status: str
    rollback_target: str | None
    known_limitations: str
    last_security_review: datetime | None


class VersionOut(BaseModel):
    version: str
    model_id: str
    prompt_ref: str
    created_at: datetime
    approved: bool
    eval_score: float | None
    rollback_target: str | None
    changelog: str


class ApprovalPatch(BaseModel):
    approved: bool
    rollback_target: str | None = None
    eval_score: float | None = None


def _manifest_out(manifest: AgentManifest) -> ManifestOut:
    return ManifestOut(**asdict(manifest))


def create_app(store: AgentRegistryStore) -> FastAPI:
    app = FastAPI(title="Diligence Room - Agent Registry")

    @app.post("/agents", status_code=201, response_model=ManifestOut)
    def create_agent(payload: ManifestIn) -> ManifestOut:
        try:
            manifest = AgentManifest(
                agent_id=payload.agent_id,
                name=payload.name,
                version=payload.version,
                capabilities=tuple(payload.capabilities),
                owner=payload.owner,
                required_identity=payload.required_identity,
                allowed_tools=tuple(payload.allowed_tools),
                supported_document_types=tuple(payload.supported_document_types),
                policy_profile=payload.policy_profile,
                created_at=datetime.now(UTC),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            store.create_manifest(manifest)
        except DuplicateAgentError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _manifest_out(manifest)

    @app.get("/agents", response_model=list[ManifestOut])
    def list_agents() -> list[ManifestOut]:
        return [_manifest_out(manifest) for manifest in store.list_manifests()]

    @app.get("/agents/{agent_id}/versions", response_model=list[VersionOut])
    def list_versions(agent_id: str) -> list[VersionOut]:
        try:
            versions = store.list_versions(agent_id)
        except AgentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [VersionOut(**asdict(version)) for version in versions]

    @app.patch("/agents/{agent_id}/approval", response_model=ManifestOut)
    def patch_approval(agent_id: str, patch: ApprovalPatch) -> ManifestOut:
        try:
            updated = store.update_approval(
                agent_id,
                approved=patch.approved,
                rollback_target=patch.rollback_target,
                eval_score=patch.eval_score,
            )
        except AgentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _manifest_out(updated)

    return app
