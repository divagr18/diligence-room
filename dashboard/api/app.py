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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from dashboard.api import data
from dashboard.api.models import (
    AgentOut,
    DealBundle,
    FindingDetail,
    FindingListItem,
    SecurityBundle,
)


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
    def deal() -> DealBundle:
        return data.build_deal_bundle()

    @app.get("/api/findings", response_model=list[FindingListItem])
    def findings() -> list[FindingListItem]:
        return data.build_findings()

    @app.get("/api/findings/{finding_id}", response_model=FindingDetail)
    def finding_detail(finding_id: str) -> FindingDetail:
        detail = data.build_finding_detail(finding_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"finding {finding_id!r} not found")
        return detail

    @app.get("/api/security", response_model=SecurityBundle)
    def security() -> SecurityBundle:
        return data.build_security_bundle()

    @app.get("/api/registry", response_model=list[AgentOut])
    def registry() -> list[AgentOut]:
        return data.build_agents()

    return app


app: FastAPI = create_app()
