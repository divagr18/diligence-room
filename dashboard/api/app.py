"""Dashboard HTTP API (BUILD_PLAN D8-M4, pulled early; vision §15).

Read-only endpoints over the demo data plane (``dashboard.api.data``) that
back the Executive Deal Room frontend:

- GET /api/health                  liveness probe
- GET /api/deal                    deal summary + workstreams + inbox
- GET /api/findings                finding list (sortable/filterable client-side)
- GET /api/findings/{finding_id}   finding detail (evidence + trace)
- GET /api/security                quarantined docs + feed + scorecard
- GET /api/registry                agent roster (manifests)

CORS is open for local dev (Vite at 5173); Cloud Run deploy front-door auth is
Day 11 work.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from dashboard.api import data, documents
from dashboard.api.models import (
    AgentOut,
    DealBundle,
    FindingDetail,
    FindingListItem,
    SecurityBundle,
)
from identity.human_authz import Role, can_view
from memory.findings import FindingStatus
from registry.models import Workstream


@dataclass(frozen=True, slots=True)
class _ViewableRow:
    workstream: Workstream
    status: FindingStatus


def _visible(role: Role, workstream: str, status: str) -> bool:
    return can_view(role, _ViewableRow(Workstream(workstream), FindingStatus(status)))


def create_app() -> FastAPI:
    app = FastAPI(title="Diligence Room Dashboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "deal": data.DEAL_ID}

    @app.get("/api/deal", response_model=DealBundle)
    def deal(role: Role = Role.DEAL_LEAD) -> DealBundle:
        bundle = data.build_deal_bundle()
        return DealBundle(
            summary=bundle.summary,
            workstreams=bundle.workstreams,
            inbox=[
                entry for entry in bundle.inbox if _visible(role, entry.workstream, entry.status)
            ],
        )

    @app.get("/api/findings", response_model=list[FindingListItem])
    def findings(role: Role = Role.DEAL_LEAD) -> list[FindingListItem]:
        items = data.build_findings()
        return [item for item in items if _visible(role, item.workstream, item.status)]

    @app.get("/api/findings/{finding_id}", response_model=FindingDetail)
    def finding_detail(finding_id: str, role: Role = Role.DEAL_LEAD) -> FindingDetail:
        detail = data.build_finding_detail(finding_id)
        if detail is None or not _visible(role, detail.workstream, detail.status):
            raise HTTPException(status_code=404, detail=f"finding {finding_id!r} not found")
        return detail

    @app.get("/api/security", response_model=SecurityBundle)
    def security() -> SecurityBundle:
        return data.build_security_bundle()

    @app.get("/api/registry", response_model=list[AgentOut])
    def registry() -> list[AgentOut]:
        return data.build_agents()

    @app.get("/api/documents/{document_id}")
    def document_file(document_id: str) -> FileResponse:
        path = documents.resolve_document_path(document_id)
        if path is None:
            raise HTTPException(status_code=404, detail=f"document {document_id!r} not found")
        return FileResponse(path)

    @app.get("/api/documents/{document_id}/locate")
    def document_locate(document_id: str, span: str = Query(default="")) -> dict[str, object]:
        locator = documents.locate_evidence(document_id, span)
        if locator is None:
            raise HTTPException(status_code=404, detail=f"document {document_id!r} not found")
        return locator

    return app


app: FastAPI = create_app()
